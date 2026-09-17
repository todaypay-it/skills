#!/usr/bin/env python3
"""Prepare or explicitly send a signed TDayPay transaction request."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ENDPOINTS = {
    "latin": "https://apis.tdaypay.com/gateway/base/biz",
    "asia": "https://api.tdaypay.com/gateway/base/biz",
    "africa": "https://afapi.tdaypay.com/gateway/base/biz",
}

CURRENCY_REGIONS = {
    **{currency: "latin" for currency in ("BRL", "MXN", "PEN", "CLP", "COP", "ARS", "ECS", "VES")},
    **{currency: "asia" for currency in ("INR", "IDR", "RUB", "PHP", "MYR", "BDT", "PKR", "THB", "AED")},
    **{currency: "africa" for currency in ("KES", "NGN", "TZS")},
}

METHODS = {
    "payment": "pay",
    "payout": "payOut",
    "balance": "balance",
    "query": "verifyStatus",
}

PAYMENT_REQUIRED = (
    "mchOrderId",
    "amount",
    "currency",
    "productinfo",
    "firstname",
    "lastname",
    "email",
    "phone",
)

PAYOUT_REQUIRED = (
    "mchOrderId",
    "amount",
    "currency",
    "purpose",
    "beneficiaryName",
    "beneficiaryEmail",
    "beneficiaryMobile",
    "beneficiaryAccountNumber",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=METHODS)
    parser.add_argument("--region", choices=ENDPOINTS)
    parser.add_argument("--endpoint", help="Reviewed HTTPS gateway override")
    parser.add_argument("--body-file", type=Path, help="UTF-8 JSON request body")
    parser.add_argument("--body-json", help="Inline JSON; avoid for sensitive data because shell history may retain it")
    parser.add_argument("--mch-id", help="Defaults to TDAYPAY_MCH_ID")
    parser.add_argument("--timestamp", type=int, help="Unix timestamp in seconds; defaults to current time")
    parser.add_argument("--send", action="store_true", help="Send to the live gateway instead of only preparing")
    parser.add_argument(
        "--confirm-live-send",
        action="store_true",
        help="Required with --send after action-time user authorization",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def load_body(args: argparse.Namespace) -> dict[str, Any]:
    sources = sum(value is not None for value in (args.body_file, args.body_json))
    if sources > 1:
        raise ValueError("Use only one of --body-file or --body-json")
    if args.body_file is not None:
        raw = args.body_file.read_text(encoding="utf-8")
    elif args.body_json is not None:
        raw = args.body_json
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raise ValueError("Provide JSON with --body-file, --body-json, or stdin")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Request body must be a JSON object")
    return value


def require_fields(body: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if body.get(field) in (None, "")]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))


def validate_amount(body: dict[str, Any]) -> None:
    if "amount" not in body:
        return
    try:
        amount = Decimal(str(body["amount"]))
    except InvalidOperation as exc:
        raise ValueError("amount must be numeric") from exc
    if amount <= 0:
        raise ValueError("amount must be greater than zero")


def validate_body(action: str, body: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if action == "payment":
        require_fields(body, PAYMENT_REQUIRED)
        order_id = str(body["mchOrderId"])
        if not 5 <= len(order_id) <= 32:
            raise ValueError("payment mchOrderId must be 5-32 characters")
    elif action == "payout":
        require_fields(body, PAYOUT_REQUIRED)
    elif action == "query":
        require_fields(body, ("orderId",))
        order_ids = [item.strip() for item in str(body["orderId"]).split(",") if item.strip()]
        if not order_ids:
            raise ValueError("orderId must contain at least one platform order ID")
        if len(order_ids) > 200:
            raise ValueError("query supports at most 200 order IDs")
    elif action == "balance" and not body.get("currency"):
        warnings.append("currency omitted; documentation says it defaults to INR, but explicit currency is safer")

    validate_amount(body)

    currency = body.get("currency")
    if currency is not None:
        normalized = str(currency).upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("currency must be a three-letter code")
        body["currency"] = normalized

    for field in ("callbackUrl", "redirectUrl"):
        value = body.get(field)
        if value and not re.match(r"^https?://", str(value), re.IGNORECASE):
            raise ValueError(f"{field} must use http:// or https://")
        if value and str(value).lower().startswith("http://"):
            warnings.append(f"{field} is not HTTPS")

    for field in ("email", "beneficiaryEmail"):
        value = body.get(field)
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value)):
            raise ValueError(f"{field} is not a valid email address")

    for field in ("phone", "beneficiaryMobile"):
        value = body.get(field)
        if value and not 6 <= len(str(value)) <= 20:
            raise ValueError(f"{field} must be 6-20 characters before stricter country validation")

    if body.get("currency") == "COP":
        try:
            amount = Decimal(str(body.get("amount")))
            if amount != amount.to_integral_value():
                raise ValueError("documented COP channels do not support decimal amounts")
            if amount < 5000 or amount > 3000000:
                warnings.append("COP amount is outside the documented 5,000-3,000,000 range; examples conflict")
        except InvalidOperation:
            pass

    return warnings


def resolve_endpoint(args: argparse.Namespace, body: dict[str, Any]) -> tuple[str, str]:
    if args.endpoint:
        parsed = urllib.parse.urlparse(args.endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("--endpoint must use HTTPS")
        if parsed.hostname != "tdaypay.com" and not parsed.hostname.endswith(".tdaypay.com"):
            raise ValueError("--endpoint must be a reviewed tdaypay.com host")
        if parsed.path != "/gateway/base/biz":
            raise ValueError("--endpoint path must be /gateway/base/biz")
        return args.endpoint, "custom"
    region = args.region
    currency = str(body.get("currency", "")).upper()
    inferred = CURRENCY_REGIONS.get(currency)
    if region and inferred and region != inferred:
        raise ValueError(f"currency {currency} is documented for region {inferred}, not {region}")
    region = region or inferred
    if not region:
        raise ValueError("Cannot infer gateway; provide a reviewed --region or --endpoint")
    return ENDPOINTS[region], region


def parse_response_body(response_text: str) -> Any:
    """Parse JSON responses while preserving non-JSON gateway output."""
    if not response_text:
        return None
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return response_text


def print_api_response(http_status: int | None, response_body: Any, transport_error: str | None = None) -> None:
    """Emit one consistent response envelope for successful and failed sends."""
    result = {
        "httpStatus": http_status,
        "response": response_body,
    }
    if transport_error is not None:
        result["transportError"] = transport_error
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    try:
        body = load_body(args)
        warnings = validate_body(args.action, body)
        endpoint, region = resolve_endpoint(args, body)
        mch_id = args.mch_id or os.environ.get("TDAYPAY_MCH_ID")
        merchant_key = os.environ.get("TDAYPAY_MERCHANT_KEY")
        if not mch_id:
            raise ValueError("Set TDAYPAY_MCH_ID or pass --mch-id")
        if not merchant_key:
            raise ValueError("Set TDAYPAY_MERCHANT_KEY; command-line keys are intentionally unsupported")
        if args.send and not args.confirm_live_send:
            raise ValueError("--send requires --confirm-live-send after action-time authorization")

        timestamp = args.timestamp or int(time.time())
        body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        method = METHODS[args.action]
        signature_input = f"{mch_id}api.pay{method}{timestamp}SHA512{body_text}{merchant_key}"
        signature = hashlib.sha512(signature_input.encode("utf-8")).hexdigest()
        headers = {
            "serviceName": "api.pay",
            "method": method,
            "mchId": mch_id,
            "signType": "SHA512",
            "timestamp": str(timestamp),
            "sign": signature,
            "Content-Type": "application/json",
        }

        prepared = {
            "mode": "live-send" if args.send else "prepare-only",
            "action": args.action,
            "region": region,
            "url": endpoint,
            "headers": headers,
            "body": body,
            "warnings": warnings,
        }
        if not args.send:
            print(json.dumps(prepared, ensure_ascii=False, indent=2))
            return 0

        request = urllib.request.Request(
            endpoint,
            data=body_text.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                print_api_response(response.status, parse_response_body(response_text))
                return 0
        except urllib.error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            print_api_response(exc.code, parse_response_body(response_text))
            return 3
        except urllib.error.URLError as exc:
            reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
            print_api_response(None, None, reason)
            return 3
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
