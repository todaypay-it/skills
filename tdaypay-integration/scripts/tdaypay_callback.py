#!/usr/bin/env python3
"""Verify TDayPay webhook signatures and validate callback payloads offline."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "rules.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="Verify one raw callback body")
    verify.add_argument("--body-file", type=Path, help="Raw callback bytes; defaults to stdin")
    verify.add_argument("--sign", required=True, help="Exact value of the callback sign header")
    verify.add_argument("--region", choices=("latin", "asia"), help="Expected callback source-IP region")
    verify.add_argument("--source-ip", help="Peer IP resolved after trusted-proxy handling")

    comments = subparsers.add_parser("comments", help="Generate callback-validation comments")
    comments.add_argument("--language", default="generic")
    comments.add_argument("--format", choices=("json", "comments", "markdown"), default="json")

    subparsers.add_parser("selftest", help="Run offline callback verification tests")
    return parser.parse_args()


def load_rules() -> tuple[dict[str, Any], dict[str, Any]]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    rules = catalog.get("callbackRules")
    if not isinstance(rules, dict):
        raise ValueError("rules.json does not contain callbackRules")
    return catalog, rules


def read_raw_body(path: Path | None) -> bytes:
    if path is not None:
        return path.read_bytes()
    if sys.stdin.isatty():
        raise ValueError("Provide the untouched callback body with --body-file or stdin")
    return sys.stdin.buffer.read()


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def mask_identifier(value: Any) -> str | None:
    text = str(value or "")
    if not text:
        return None
    suffix = text[-4:] if len(text) > 4 else text[-1:]
    return f"***{suffix} (len={len(text)})"


def validate_source_ip(source_ip: str | None, region: str | None, rules: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if source_ip is None:
        warnings.append("SOURCE_IP_NOT_CHECKED: verify the peer IP after trusted-proxy resolution when IP filtering is enabled")
        return False, errors, warnings
    if region is None:
        errors.append("SOURCE_IP_REGION_REQUIRED: --region is required when --source-ip is supplied")
        return False, errors, warnings
    try:
        normalized = str(ipaddress.ip_address(source_ip))
    except ValueError:
        errors.append("INVALID_SOURCE_IP: source IP is not a valid IP address")
        return True, errors, warnings
    allowed = rules.get("callbackIps", {}).get(region, [])
    if normalized not in allowed:
        errors.append(f"SOURCE_IP_NOT_ALLOWED: source IP is not in the documented {region} callback allowlist")
    return True, errors, warnings


def validate_payload(payload: Any, rules: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["INVALID_JSON_SHAPE: callback JSON must be an object"], warnings

    required = rules.get("requiredFields", [])
    missing = [field for field in required if payload.get(field) in (None, "")]
    if missing:
        errors.append("REQUIRED_FIELDS_MISSING: " + ", ".join(missing))

    string_fields = [*required, *rules.get("optionalFields", []), *rules.get("unclassifiedFields", [])]
    for field in unique(string_fields):
        if field in payload and payload[field] is not None and not isinstance(payload[field], str):
            errors.append(f"INVALID_FIELD_TYPE: {field} must be a string")

    amount_pattern = rules.get("amountPattern")
    for field in ("amount", "realAmount"):
        value = payload.get(field)
        if value not in (None, "") and amount_pattern and not re.fullmatch(amount_pattern, str(value)):
            errors.append(f"INVALID_AMOUNT_FORMAT: {field} must be a non-negative string with exactly two decimal places")

    order_type = payload.get("orderType")
    if order_type not in (None, "") and order_type not in rules.get("orderTypes", []):
        errors.append("INVALID_ORDER_TYPE: orderType must be PAYMENT or PAYOUT")

    order_status = payload.get("orderStatus")
    if order_status not in (None, "") and order_status not in rules.get("orderStatuses", []):
        warnings.append("UNKNOWN_ORDER_STATUS: durably record the authenticated event, quarantine ledger effects, and query TDayPay")
    elif order_status in rules.get("unresolvedOrderStatuses", []):
        warnings.append(f"UNRESOLVED_ORDER_STATUS: {order_status} is listed in the callback table but its ledger meaning is not defined; quarantine and query TDayPay")

    create_time = payload.get("createTime")
    if create_time not in (None, ""):
        try:
            datetime.strptime(str(create_time), rules.get("createTimeFormat", "%Y%m%d%H%M%S"))
        except ValueError:
            errors.append("INVALID_CREATE_TIME: createTime must be a valid UTC yyyyMMddHHmmss value")
    return unique(errors), unique(warnings)


def verify_callback(
    raw_body: bytes,
    supplied_sign: str,
    merchant_key: str,
    catalog: dict[str, Any],
    rules: dict[str, Any],
    *,
    region: str | None = None,
    source_ip: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    signature_format_valid = bool(re.fullmatch(r"[0-9a-fA-F]{128}", supplied_sign))
    if not signature_format_valid:
        errors.append("INVALID_SIGN_FORMAT: sign must be 128 hexadecimal characters")

    expected_sign = hashlib.sha512(raw_body + merchant_key.encode("utf-8")).hexdigest()
    signature_valid = signature_format_valid and hmac.compare_digest(expected_sign, supplied_sign.lower())
    if not signature_valid:
        errors.append("SIGNATURE_MISMATCH: verify SHA512(raw callback bytes + merchantKey) before parsing")

    source_ip_checked, ip_errors, ip_warnings = validate_source_ip(source_ip, region, rules)
    errors.extend(ip_errors)
    warnings.extend(ip_warnings)

    payload: Any = None
    if signature_valid:
        try:
            body_text = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("INVALID_ENCODING: callback body must be UTF-8 JSON")
        else:
            try:
                payload = json.loads(body_text)
            except json.JSONDecodeError:
                errors.append("INVALID_JSON: callback body is not valid JSON")
            else:
                payload_errors, payload_warnings = validate_payload(payload, rules)
                errors.extend(payload_errors)
                warnings.extend(payload_warnings)

    authenticated = signature_valid and not ip_errors
    schema_valid = payload is not None and not any(
        error.startswith(("INVALID_JSON", "INVALID_ENCODING", "REQUIRED_FIELDS", "INVALID_FIELD", "INVALID_AMOUNT", "INVALID_ORDER_TYPE", "INVALID_CREATE_TIME"))
        for error in errors
    )
    unresolved_status = any(warning.startswith(("UNKNOWN_ORDER_STATUS", "UNRESOLVED_ORDER_STATUS")) for warning in warnings)
    if not authenticated:
        decision = "REJECT_UNAUTHENTICATED"
    elif not schema_valid:
        decision = "REJECT_INVALID_SCHEMA"
    elif unresolved_status:
        decision = "RECORD_AND_QUERY"
    else:
        decision = "RECORD_IDEMPOTENTLY"

    summary = None
    if isinstance(payload, dict):
        summary = {
            "mchOrderId": mask_identifier(payload.get("mchOrderId")),
            "orderId": mask_identifier(payload.get("orderId")),
            "orderStatus": payload.get("orderStatus"),
            "orderType": payload.get("orderType"),
            "amount": payload.get("amount"),
            "realAmount": payload.get("realAmount"),
            "createTime": payload.get("createTime"),
        }

    sources = []
    for source_id in rules.get("sourceIds", []):
        source = catalog.get("sources", {}).get(source_id)
        if source:
            sources.append({"id": source_id, **source})
    return {
        "valid": authenticated and schema_valid,
        "authenticated": authenticated,
        "signatureValid": signature_valid,
        "signatureFormatValid": signature_format_valid,
        "sourceIpChecked": source_ip_checked,
        "schemaValid": schema_valid,
        "decision": decision,
        "eventFingerprint": hashlib.sha256(raw_body).hexdigest(),
        "eventSummary": summary,
        "errors": unique(errors),
        "warnings": unique(warnings),
        "acknowledgeAfterDurableRecord": rules.get("acknowledgement"),
        "sources": sources,
    }


def comment_prefix(language: str) -> tuple[str, str]:
    value = language.lower().lstrip(".")
    if value in {"python", "py", "ruby", "rb", "shell", "bash", "sh", "yaml", "yml"}:
        return "# ", ""
    if value in {"sql", "lua", "haskell", "hs"}:
        return "-- ", ""
    if value in {"html", "xml"}:
        return "<!-- ", " -->"
    if value in {"css", "scss"}:
        return "/* ", " */"
    return "// ", ""


def comment_plan(catalog: dict[str, Any], rules: dict[str, Any], language: str) -> dict[str, Any]:
    source_id = rules.get("sourceIds", [catalog.get("defaultSourceId")])[0]
    checked = catalog.get("sources", {}).get(source_id, {}).get("checkedAt", "unverified")
    definitions = [
        ("CALLBACK.SIGNATURE.RAW_BODY", "REQUIRED", "Integration safety: capture the untouched request bytes and verify sign=SHA512(rawBody+merchantKey) before JSON parsing; examples are lowercase but the provider does not specify hex letter case."),
        ("CALLBACK.SIGNATURE.CONSTANT_TIME", "REQUIRED", "Integration safety: compare the calculated and supplied signatures with a constant-time comparison."),
        ("CALLBACK.REQUIRED_FIELDS", "REQUIRED", "Require mchOrderId, orderId, orderStatus, amount, orderType, and createTime after authentication."),
        ("CALLBACK.AMOUNT.TWO_DECIMALS", "REQUIRED", "Validate amount, and realAmount when present, as non-negative strings with exactly two decimal places; realAmount requiredness is unspecified and callback formatting is independent of request-side COP integer rules."),
        ("CALLBACK.ORDER_TYPE", "REQUIRED", "Require orderType to be PAYMENT or PAYOUT before dispatching ledger behavior."),
        ("CALLBACK.CREATE_TIME.UTC", "REQUIRED", "Validate createTime as UTC yyyyMMddHHmmss; the documentation defines no replay-expiry header."),
        ("CALLBACK.IDEMPOTENCY.DURABLE", "REQUIRED", "Integration safety: durably deduplicate identical callback events while preserving distinct status transitions for the same orderId."),
        ("CALLBACK.ACK.SUCCESS", "REQUIRED", "Integration safety: return HTTP 200 with body success only after the authenticated event and processing outcome are durably recorded."),
        ("CALLBACK.STATUS.NON_MONOTONIC", "INFO", "Preserve append-only status history because SUCCESS can become REVERSED and FAILED can become SUCCESS."),
        ("CALLBACK.SOURCE_IP", "INFO", "When IP filtering is enabled, resolve the peer through trusted proxies and compare it with the current regional callback allowlist; signature verification remains mandatory."),
    ]
    prefix, suffix = comment_prefix(language)
    items = []
    for identifier, level, behavior in definitions:
        rendered = f"{prefix}TDAYPAY-RULE[{identifier}] [{level}] {behavior} Source: {source_id}, checked {checked}.{suffix}"
        items.append({"id": identifier, "level": level, "behavior": behavior, "sourceIds": [source_id], "checkedAt": checked, "comment": rendered})
    return {
        "valid": True,
        "requiredRules": [item for item in items if item["level"] == "REQUIRED"],
        "informationalRules": [item for item in items if item["level"] == "INFO"],
        "requiredCommentCount": sum(item["level"] == "REQUIRED" for item in items),
        "renderedComments": [item["comment"] for item in items],
    }


def run_selftest(catalog: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    merchant_key = "test-merchant-key"
    raw = b'{"mchOrderId":"MCH12345","orderId":"PLATFORM12345","bankId":"BANK1","orderStatus":"SUCCESS","amount":"5000.00","realAmount":"5000.00","orderType":"PAYOUT","failMessage":"","createTime":"20260910091530","transIds":"TRANS1","payMethod":"TRANSFIYA"}'
    sign = hashlib.sha512(raw + merchant_key.encode()).hexdigest()
    valid = verify_callback(raw, sign, merchant_key, catalog, rules, region="latin", source_ip="18.228.164.232")
    assert valid["valid"] is True
    assert valid["decision"] == "RECORD_IDEMPOTENTLY"
    assert valid["eventSummary"]["amount"] == "5000.00"

    tampered = verify_callback(raw.replace(b'"SUCCESS"', b'"FAILED"'), sign, merchant_key, catalog, rules)
    assert tampered["valid"] is False
    assert tampered["decision"] == "REJECT_UNAUTHENTICATED"

    reordered = b'{"orderId":"PLATFORM12345","mchOrderId":"MCH12345","orderStatus":"SUCCESS","amount":"5000.00","orderType":"PAYOUT","createTime":"20260910091530"}'
    reordered_result = verify_callback(reordered, sign, merchant_key, catalog, rules)
    assert reordered_result["signatureValid"] is False

    missing = b'{"mchOrderId":"MCH12345","orderId":"PLATFORM12345","orderStatus":"SUCCESS","amount":"5000.00","orderType":"PAYOUT"}'
    missing_sign = hashlib.sha512(missing + merchant_key.encode()).hexdigest()
    missing_result = verify_callback(missing, missing_sign, merchant_key, catalog, rules)
    assert missing_result["authenticated"] is True
    assert missing_result["schemaValid"] is False

    unknown = raw.replace(b'"SUCCESS"', b'"NEW_PROVIDER_STATE"')
    unknown_sign = hashlib.sha512(unknown + merchant_key.encode()).hexdigest()
    unknown_result = verify_callback(unknown, unknown_sign, merchant_key, catalog, rules)
    assert unknown_result["valid"] is True
    assert unknown_result["decision"] == "RECORD_AND_QUERY"

    uppercase_result = verify_callback(raw, sign.upper(), merchant_key, catalog, rules)
    assert uppercase_result["signatureValid"] is True

    refund = raw.replace(b'"SUCCESS"', b'"REFUND"')
    refund_sign = hashlib.sha512(refund + merchant_key.encode()).hexdigest()
    refund_result = verify_callback(refund, refund_sign, merchant_key, catalog, rules)
    assert refund_result["decision"] == "RECORD_AND_QUERY"

    plan = comment_plan(catalog, rules, "typescript")
    assert plan["requiredCommentCount"] == 8
    assert all(item["comment"].startswith("// TDAYPAY-RULE[") for item in plan["requiredRules"])
    return {"valid": True, "cases": 8, "passed": 8}


def main() -> int:
    try:
        args = parse_args()
        catalog, rules = load_rules()
        if args.command == "selftest":
            print(json.dumps(run_selftest(catalog, rules), ensure_ascii=False, indent=2))
            return 0
        if args.command == "comments":
            plan = comment_plan(catalog, rules, args.language)
            if args.format == "comments":
                print("\n".join(item["comment"] for item in plan["requiredRules"]))
            elif args.format == "markdown":
                lines = ["# TDayPay callback validation comments", ""]
                lines.extend(f"- `{item['id']}` — {item['behavior']}" for item in plan["requiredRules"])
                print("\n".join(lines))
            else:
                print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        merchant_key = os.environ.get("TDAYPAY_MERCHANT_KEY")
        if not merchant_key:
            raise ValueError("Set TDAYPAY_MERCHANT_KEY; command-line keys are intentionally unsupported")
        result = verify_callback(
            read_raw_body(args.body_file), args.sign, merchant_key, catalog, rules,
            region=args.region, source_ip=args.source_ip,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
