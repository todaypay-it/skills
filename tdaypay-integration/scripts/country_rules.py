#!/usr/bin/env python3
"""Inspect and conservatively validate TDayPay country/channel rules."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "rules.json"
EVAL_CASES_PATH = Path(__file__).resolve().parent.parent / "references" / "eval-cases.json"
ACTIONS = ("payment", "payout")
VALID_COVERAGE = {"detailed", "partial", "routing-only", "unmapped"}
VALID_SOURCE_TYPES = {"tdaypay-api", "network", "network-regulation", "institution", "merchant-contract"}
QUICK_REQUIRED_FIELDS = {
    "paymentType", "bankCode", "beneficiaryBankCode", "beneficiaryBankName",
    "beneficiaryAccountNumber", "beneficiaryAccountType", "docType", "docNumber",
}


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("rules.json must contain a JSON object")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List currencies and coverage")
    list_parser.add_argument("--gateway", choices=("latin", "asia", "africa"))
    list_parser.add_argument("--coverage", choices=tuple(sorted(VALID_COVERAGE)))
    show_parser = subparsers.add_parser("show", help="Show one currency rule")
    show_parser.add_argument("--currency", required=True)
    explain_parser = subparsers.add_parser("explain", help="Explain provider and network evidence for one channel")
    explain_parser.add_argument("action", choices=ACTIONS)
    explain_parser.add_argument("--currency", required=True)
    explain_parser.add_argument("--payment-type", "--channel", dest="payment_type", required=True)
    validate_parser = subparsers.add_parser("validate", help="Validate a complete transaction body")
    validate_parser.add_argument("action", choices=ACTIONS)
    source = validate_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--body-file", type=Path)
    source.add_argument("--body-json", help="Avoid for sensitive data because shell history may retain it")
    check_parser = subparsers.add_parser("check", help="Preflight selected fields without preparing a complete body")
    check_parser.add_argument("action", choices=ACTIONS)
    check_parser.add_argument("--currency", required=True)
    check_parser.add_argument("--payment-type", "--channel", dest="payment_type")
    check_parser.add_argument("--amount", required=True)
    check_parser.add_argument("--phone")
    check_parser.add_argument("--email")
    check_parser.add_argument("--purpose")
    check_parser.add_argument("--beneficiary-name")
    check_parser.add_argument("--beneficiary-email")
    check_parser.add_argument("--dynamic")
    check_parser.add_argument("--mch-order-id")
    check_parser.add_argument("--bank-code")
    check_parser.add_argument("--beneficiary-mobile")
    check_parser.add_argument("--beneficiary-account-number")
    check_parser.add_argument("--beneficiary-bank-code")
    check_parser.add_argument("--beneficiary-bank-name")
    check_parser.add_argument("--beneficiary-account-type")
    check_parser.add_argument("--beneficiary-type")
    check_parser.add_argument("--beneficiary-id")
    check_parser.add_argument("--ip-address")
    check_parser.add_argument("--product-url")
    check_parser.add_argument("--payment-method")
    check_parser.add_argument("--doc-type")
    check_parser.add_argument("--doc-number")
    check_parser.add_argument("--callback-url")
    check_parser.add_argument("--key-type", help="Validator-only BRE_B key metadata; never add it to a TDayPay request")
    audit_parser = subparsers.add_parser("audit", help="Check catalog structure, evidence references, and source freshness")
    audit_parser.add_argument("--max-source-age-days", type=int, default=365)
    subparsers.add_parser("selftest", help="Run deterministic representative validation cases")
    return parser.parse_args()


def normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def rule_for(catalog: dict[str, Any], currency: str) -> dict[str, Any] | None:
    return catalog.get("countries", {}).get(normalize_code(currency))


def load_body(args: argparse.Namespace) -> dict[str, Any]:
    raw = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body_json
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


def clabe_checksum_valid(value: str) -> bool:
    if not re.fullmatch(r"\d{18}", value):
        return False
    total = sum(((int(digit) * (3, 7, 1)[index % 3]) % 10) for index, digit in enumerate(value[:17]))
    return (10 - total % 10) % 10 == int(value[17])


def unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def resolve_channel(rule: dict[str, Any], action: str, input_channel: str) -> tuple[str, list[str]]:
    aliases = rule.get(action, {}).get("channelAliases", {})
    channel = aliases.get(input_channel, input_channel)
    return channel, [f"{input_channel} -> {channel}"] if input_channel and channel != input_channel else []


def network_fact_for(rule: dict[str, Any], action: str, input_channel: str, channel: str) -> tuple[str | None, dict[str, Any] | None]:
    facts = rule.get("networkFacts", {})
    if action == "payment" and input_channel == "PSE":
        return "PSE", facts.get("PSE")
    if action == "payment" and channel == "NET_BANKING" and "PSE" in facts:
        return "PSE", facts.get("PSE")
    return (channel, facts.get(channel)) if channel in facts else (None, None)


def resolve_sources(catalog: dict[str, Any], source_ids: Iterable[str]) -> list[dict[str, Any]]:
    sources = catalog.get("sources", {})
    return [{"id": source_id, **sources[source_id]} for source_id in unique(source_ids) if source_id in sources]


def evidence_for(catalog: dict[str, Any], rule: dict[str, Any], action: str, input_channel: str, channel: str) -> dict[str, Any]:
    common_rule = catalog.get("commonRules", {}).get(action, {})
    action_rule = rule.get(action, {})
    channel_rule = action_rule.get("channelRules", {}).get(channel, {})
    network_name, network_fact = network_fact_for(rule, action, input_channel, channel)
    ids = [catalog.get("defaultSourceId"), *common_rule.get("sourceIds", []), *action_rule.get("sourceIds", []), *channel_rule.get("sourceIds", [])]
    if network_fact:
        ids.extend(network_fact.get("sourceIds", []))
    return {
        "commonRule": common_rule or None,
        "providerRule": channel_rule or None,
        "networkName": network_name,
        "networkContext": network_fact,
        "sources": resolve_sources(catalog, ids),
    }


def required_field_errors(body: dict[str, Any], fields: Iterable[str], strict_required: bool) -> list[str]:
    errors = []
    for field in fields:
        if strict_required or field in QUICK_REQUIRED_FIELDS:
            if body.get(field) in (None, ""):
                errors.append(f"REQUIRED_FIELD: {field} is required")
    return errors


def validate(
    action: str,
    body: dict[str, Any],
    catalog: dict[str, Any],
    *,
    strict_required: bool = True,
    key_type: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    confirmations: list[str] = []
    conflict_codes: list[str] = []
    currency = normalize_code(body.get("currency"))
    input_channel = normalize_code(body.get("paymentType"))
    channel = input_channel
    normalizations: list[str] = []
    rule: dict[str, Any] | None
    if not re.fullmatch(r"[A-Z]{3}", currency):
        errors.append("INVALID_CURRENCY: currency must be a three-letter code")
        rule = None
    else:
        rule = rule_for(catalog, currency)
        if rule is None:
            errors.append(f"UNKNOWN_CURRENCY: currency {currency} is not present in the catalog")
        else:
            channel, normalizations = resolve_channel(rule, action, input_channel)

    amount: Decimal | None = None
    if body.get("amount") in (None, ""):
        errors.append("REQUIRED_FIELD: amount is required")
    else:
        try:
            amount = Decimal(str(body["amount"]))
            if not amount.is_finite():
                errors.append("INVALID_AMOUNT: amount must be finite")
            elif amount <= 0:
                errors.append("INVALID_AMOUNT: amount must be greater than zero")
        except InvalidOperation:
            errors.append("INVALID_AMOUNT: amount must be numeric")

    common_rule = catalog.get("commonRules", {}).get(action, {})
    common_body_fields = [field for field in common_rule.get("requiredBodyFields", []) if field not in {"amount", "currency"}]
    errors.extend(required_field_errors(body, common_body_fields, strict_required))
    for field, constraint in common_rule.get("fieldConstraints", {}).items():
        value = str(body.get(field, ""))
        minimum = constraint.get("minLength")
        maximum = constraint.get("maxLength")
        if value and minimum is not None and len(value) < minimum:
            errors.append(f"INVALID_LENGTH: {field} must be at least {minimum} characters")
        if value and maximum is not None and len(value) > maximum:
            errors.append(f"INVALID_LENGTH: {field} must be at most {maximum} characters")
    confirmations.extend(common_rule.get("manualConfirmations", []))
    beneficiary_email = str(body.get("beneficiaryEmail", "")).strip()
    if beneficiary_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", beneficiary_email):
        errors.append("INVALID_EMAIL: beneficiaryEmail has an invalid format")

    evidence: dict[str, Any] = {"commonRule": common_rule or None, "providerRule": None, "networkName": None, "networkContext": None, "sources": []}
    if rule is not None:
        coverage = rule.get("coverage")
        if coverage == "unmapped":
            errors.append(f"UNMAPPED_GATEWAY: currency {currency} has no reviewed gateway mapping")
        elif coverage == "routing-only":
            warnings.append(f"ROUTING_ONLY: {currency} has routing-only coverage; channel and field rules are unknown")
        elif coverage == "partial":
            warnings.append(f"PARTIAL_COVERAGE: {currency} has partial coverage; recorded channels are not exhaustive")

        action_rule = rule.get(action, {})
        if channel:
            if not action_rule:
                warnings.append(f"UNKNOWN_ACTION_CHANNELS: no {action} channel catalog is recorded for {currency}; cannot verify {channel}")
            elif channel not in action_rule.get("channels", []):
                opposite = "payout" if action == "payment" else "payment"
                opposite_channels = rule.get(opposite, {}).get("channels", [])
                if input_channel == "PSE" and action == "payout" and currency == "COP":
                    errors.append("ACTION_SCOPED_ALIAS: PSE is a COP payment alias only; it must not be normalized for payout")
                elif channel in opposite_channels:
                    errors.append(f"WRONG_ACTION: {channel} is documented only for {opposite} in {currency}, not {action}")
                else:
                    warnings.append(f"UNDOCUMENTED_CHANNEL: {channel} is not in the recorded {currency} {action} channel list")
        elif action_rule.get("channels"):
            errors.append("REQUIRED_FIELD: paymentType is required")

        channel_rule = action_rule.get("channelRules", {}).get(channel, {})
        evidence = evidence_for(catalog, rule, action, input_channel, channel)
        errors.extend(required_field_errors(body, action_rule.get("requiredFields", []), strict_required))
        errors.extend(required_field_errors(body, channel_rule.get("requiredFields", []), strict_required))

        for field, expected in action_rule.get("requiredValues", {}).items():
            if strict_required and body.get(field) in (None, ""):
                errors.append(f"REQUIRED_VALUE: {field} must be {expected}")
            elif body.get(field) not in (None, "") and str(body[field]) != str(expected):
                errors.append(f"INVALID_FIXED_VALUE: {field} must be {expected}")
        for field, expected in action_rule.get("optionalFixedValues", {}).items():
            if body.get(field) not in (None, "") and str(body[field]) != str(expected):
                errors.append(f"INVALID_FIXED_VALUE: when supplied, {field} must be {expected}")
        for field, expected in channel_rule.get("requiredValues", {}).items():
            if body.get(field) in (None, "") or str(body[field]) != str(expected):
                errors.append(f"INVALID_FIXED_VALUE: {field} must be {expected} for {channel}")
        forbidden = channel_rule.get("mchOrderIdForbids")
        if forbidden and forbidden in str(body.get("mchOrderId", "")):
            errors.append(f"INVALID_ORDER_ID: mchOrderId must not contain {forbidden!r} for {currency} {channel}")

        amount_rule = action_rule.get("amount", rule.get("amount", {}))
        if amount is not None and amount.is_finite():
            if amount_rule.get("decimalsAllowed", rule.get("amount", {}).get("decimalsAllowed")) is False and amount != amount.to_integral_value():
                errors.append(f"DECIMAL_NOT_ALLOWED: {currency} does not support decimal amounts in the recorded contract")
            minimum = amount_rule.get("min")
            maximum = amount_rule.get("max")
            outside = (minimum is not None and amount < Decimal(minimum)) or (maximum is not None and amount > Decimal(maximum))
            if outside:
                if amount_rule.get("limitsConflictWithExamples", rule.get("amount", {}).get("limitsConflictWithExamples")):
                    warnings.append(f"DOCUMENT_CONFLICT: amount is outside the documented {currency} range {minimum}-{maximum}, but public examples conflict")
                    conflict_codes.append("CONTRACT_CONFIRMATION_REQUIRED")
                else:
                    errors.append(f"AMOUNT_OUT_OF_RANGE: amount must be between {minimum} and {maximum} {currency}")

        for field, allowed in action_rule.get("allowedValues", {}).items():
            if body.get(field) not in (None, "") and normalize_code(body[field]) not in allowed:
                errors.append(f"INVALID_ENUM: {field} must be one of {', '.join(allowed)}")
        for field, allowed in channel_rule.get("allowedValues", {}).items():
            if body.get(field) not in (None, "") and normalize_code(body[field]) not in allowed:
                errors.append(f"INVALID_ENUM: {field} must be one of {', '.join(allowed)}")
        for field, conditional in action_rule.get("conditionalPatterns", {}).items():
            selector = conditional.get("selector")
            selector_value = normalize_code(body.get(selector))
            value = str(body.get(field, "")).strip()
            pattern = conditional.get("patterns", {}).get(selector_value)
            if value and pattern and not re.fullmatch(pattern, value):
                description = conditional.get("descriptions", {}).get(selector_value, f"match {pattern}")
                errors.append(f"INVALID_FORMAT: {field} must be {description} when {selector}={selector_value}")
        for field, format_rule in action_rule.get("formatRules", {}).items():
            value = str(body.get(field, "")).strip()
            if not value:
                continue
            kind = format_rule.get("kind")
            if kind == "ip":
                try:
                    address = ipaddress.ip_address(value)
                    if format_rule.get("runtimeValueRequired") and (address.is_loopback or address.is_unspecified or address.is_multicast or address.is_reserved):
                        warnings.append(f"NON_RUNTIME_IP: {field} must be the payer device IP captured at request time, not a loopback, unspecified, multicast, or reserved example address")
                except ValueError:
                    errors.append(f"INVALID_FORMAT: {field} must be a valid IPv4 or IPv6 address")
            elif kind == "httpUrl":
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    errors.append(f"INVALID_FORMAT: {field} must be an absolute HTTP or HTTPS URL")
        for field, constraint in action_rule.get("fieldConstraints", {}).items():
            value = str(body.get(field, ""))
            minimum = constraint.get("minLength")
            maximum = constraint.get("maxLength")
            if value and minimum is not None and len(value) < minimum:
                errors.append(f"INVALID_LENGTH: {field} must be at least {minimum} characters")
            if value and maximum is not None and len(value) > maximum:
                errors.append(f"INVALID_LENGTH: {field} must be at most {maximum} characters")

        phone = str(body.get("phone" if action == "payment" else "beneficiaryMobile", "")).strip()
        if phone and currency == "COP" and not (re.fullmatch(r"\d{10}", phone) or re.fullmatch(r"\+57\d{10}", phone)):
            errors.append("INVALID_PHONE: Colombian phone must be 10 local digits or +57 followed by 10 digits")
        email = str(body.get("email", "")).strip()
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            errors.append("INVALID_EMAIL: email has an invalid format")

        if currency == "COP" and action == "payment":
            if action_rule.get("realIdentityRequired"):
                confirmations.append("Confirm payer identity, email, phone and device IP are real and belong to the actual payer.")
            if channel == "NEQUI" and body.get("bankCode") not in (None, ""):
                warnings.append("CHANNEL_SEPARATION: NEQUI direct payment does not require automatic bankCode=507; do not conflate it with PSE")

        account = str(body.get("beneficiaryAccountNumber", "")).strip()
        account_kind = channel_rule.get("beneficiaryAccountNumberKind")
        if account_kind and not account:
            errors.append(f"REQUIRED_FIELD: {channel} requires beneficiaryAccountNumber")
        elif account_kind == "clabe":
            if not re.fullmatch(r"\d{18}", account):
                errors.append("INVALID_CLABE: TDayPay SPEI payout requires an 18-digit CLABE")
            elif not clabe_checksum_valid(account):
                errors.append("INVALID_CLABE_CHECKSUM: CLABE check digit is invalid")
        elif account_kind == "bank-card" and not re.fullmatch(r"\d{16}", account):
            warnings.append("ACCOUNT_FORMAT_UNCONFIRMED: NET_BANKING is described as a bank-card number; confirm the current merchant contract if it is not 16 digits")
        elif account_kind == "mx-mobile-10" and not re.fullmatch(r"\d{10}", account):
            errors.append("INVALID_MOBILE: DIMO beneficiaryAccountNumber must be exactly 10 digits")
        elif account_kind == "co-mobile-10" and not re.fullmatch(r"\d{10}", account):
            errors.append("INVALID_MOBILE: TRANSFIYA beneficiaryAccountNumber must be 10 local digits without +57")

        normalized_key_type = normalize_code(key_type)
        if account_kind == "bre-b-key":
            allowed_key_types = channel_rule.get("validatorKeyTypes", [])
            if not normalized_key_type:
                warnings.append("AMBIGUOUS_BRE_B_KEY: declare --key-type in preflight; numeric keys can be phone or document identifiers")
            elif normalized_key_type not in allowed_key_types:
                errors.append(f"INVALID_BRE_B_KEY_TYPE: key type must be one of {', '.join(allowed_key_types)}")
            elif normalized_key_type == "PHONE" and not re.fullmatch(r"\d{10}", account):
                errors.append("INVALID_BRE_B_KEY: PHONE key must be 10 local digits")
            elif normalized_key_type == "EMAIL" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account):
                errors.append("INVALID_BRE_B_KEY: EMAIL key has an invalid format")
            elif normalized_key_type == "ALPHANUMERIC" and not re.fullmatch(r"@[A-Za-z0-9]+", account):
                errors.append("INVALID_BRE_B_KEY: ALPHANUMERIC key must start with @ and contain letters or digits")
            elif normalized_key_type == "MERCHANT_CODE":
                warnings.append("CONTRACT_CONFIRMATION_REQUIRED: TDayPay public documentation does not explicitly confirm merchant-code Bre-B keys")
                conflict_codes.append("CONTRACT_CONFIRMATION_REQUIRED")

        if channel_rule.get("beneficiaryActivationRequired"):
            confirmations.append(f"Confirm the beneficiary has activated or registered {channel}.")
        bank = normalize_code(body.get("beneficiaryBankName") or body.get("beneficiaryBankCode"))
        allowed_bank_codes = channel_rule.get("allowedBankCodes", [])
        if allowed_bank_codes and bank.isdigit() and bank not in allowed_bank_codes:
            errors.append(f"UNSUPPORTED_CHANNEL_BANK: {bank} is not in the recorded {channel} institution table")
        if currency == "COP" and action == "payout" and channel == "TRANSFIYA" and bank in {"507", "NEQUI"}:
            warnings.append("STALE_CHANNEL_CONFLICT: Nequi says Transfiya in its app ended on 2025-10-05; obtain current TDayPay/merchant confirmation")
            conflict_codes.append("CONTRACT_CONFIRMATION_REQUIRED")

        confirmations.extend(action_rule.get("manualConfirmations", []))
        confirmations.extend(channel_rule.get("manualConfirmations", []))
        warnings.extend(note for note in [*rule.get("notes", []), *action_rule.get("notes", []), *channel_rule.get("notes", [])] if note not in warnings)

    contract_confirmation_required = "CONTRACT_CONFIRMATION_REQUIRED" in conflict_codes
    if errors:
        decision = "BLOCKED"
    elif contract_confirmation_required:
        decision = "CONTRACT_CONFIRMATION_REQUIRED"
    elif confirmations and action != "payout":
        decision = "MANUAL_CONFIRMATION_REQUIRED"
    elif confirmations or warnings:
        decision = "VALIDATED_WITH_WARNINGS"
    else:
        decision = "VALIDATED"
    gateway_key = rule.get("gateway") if rule else None
    return {
        "valid": not errors,
        "productionDecision": decision,
        "contractConfirmationRequired": contract_confirmation_required,
        "manualReviewRequired": action != "payout" and bool(confirmations),
        "currency": currency or None,
        "country": rule.get("country") if rule else None,
        "action": action,
        "inputPaymentType": input_channel or None,
        "paymentType": channel or None,
        "validationKeyType": normalize_code(key_type) or None,
        "normalizations": normalizations,
        "coverage": rule.get("coverage") if rule else None,
        "gateway": catalog.get("gateways", {}).get(gateway_key) if gateway_key else None,
        "errors": unique(errors),
        "warnings": unique(warnings),
        "manualConfirmations": unique(confirmations),
        "commonRule": evidence.get("commonRule"),
        "networkContext": evidence.get("networkContext"),
        "sources": evidence.get("sources", []),
        "catalogVerifiedAt": catalog.get("verifiedAt"),
    }


def all_source_references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "sourceIds" and isinstance(child, list):
                yield from child
            else:
                yield from all_source_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_source_references(child)


def audit(catalog: dict[str, Any], max_source_age_days: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    gateways = catalog.get("gateways", {})
    countries = catalog.get("countries", {})
    sources = catalog.get("sources", {})
    if catalog.get("schemaVersion") != 3:
        errors.append("schemaVersion must be 3")
    if not countries:
        errors.append("countries must not be empty")
    if not sources:
        errors.append("sources must not be empty")
    for source_id, source in sources.items():
        if source.get("sourceType") not in VALID_SOURCE_TYPES:
            errors.append(f"{source_id}: invalid sourceType")
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{source_id}: source URL must use https")
        try:
            checked = date.fromisoformat(source.get("checkedAt", ""))
            age = (date.today() - checked).days
            if age > max_source_age_days:
                warnings.append(f"{source_id}: source is {age} days old (limit {max_source_age_days})")
        except ValueError:
            errors.append(f"{source_id}: checkedAt must be YYYY-MM-DD")
    for source_id in all_source_references({"callbackRules": catalog.get("callbackRules", {}), "commonRules": catalog.get("commonRules", {}), "countries": catalog.get("countries", {})}):
        if source_id not in sources:
            errors.append(f"unknown source reference: {source_id}")
    for currency, rule in countries.items():
        if not re.fullmatch(r"[A-Z]{3}", currency):
            errors.append(f"invalid currency key: {currency}")
        if rule.get("coverage") not in VALID_COVERAGE:
            errors.append(f"{currency}: invalid coverage")
        gateway = rule.get("gateway")
        if gateway is not None and gateway not in gateways:
            errors.append(f"{currency}: unknown gateway {gateway}")
        if rule.get("coverage") == "unmapped" and gateway is not None:
            errors.append(f"{currency}: unmapped rules must not have a gateway")
        for name, fact in rule.get("networkFacts", {}).items():
            if fact.get("providerCapabilityInferred") is not False:
                errors.append(f"{currency}/{name}: network facts must not infer provider capability")
        for action in ACTIONS:
            action_rule = rule.get(action, {})
            channels = action_rule.get("channels", [])
            if len(channels) != len(set(channels)):
                errors.append(f"{currency}: duplicate {action} channel")
            if any(channel != normalize_code(channel) for channel in channels):
                errors.append(f"{currency}: {action} channels must be uppercase")
            for alias, target in action_rule.get("channelAliases", {}).items():
                if alias != normalize_code(alias) or target != normalize_code(target):
                    errors.append(f"{currency}/{action}: channel alias must be uppercase: {alias} -> {target}")
                if alias == target or target not in channels:
                    errors.append(f"{currency}/{action}: invalid channel alias: {alias} -> {target}")
            for channel in action_rule.get("channelRules", {}):
                if channel not in channels:
                    errors.append(f"{currency}/{action}: rule for undocumented channel {channel}")
    return unique(errors), unique(warnings)


def run_selftest(catalog: dict[str, Any]) -> dict[str, Any]:
    with EVAL_CASES_PATH.open(encoding="utf-8") as handle:
        cases = json.load(handle)
    if not isinstance(cases, list) or not cases:
        raise ValueError("eval-cases.json must contain a non-empty JSON array")
    failures: list[dict[str, Any]] = []
    for case in cases:
        result = validate(
            case["action"], case["body"], catalog,
            strict_required=case.get("strict", False), key_type=case.get("keyType"),
        )
        expected = case.get("expect", {})
        reasons: list[str] = []
        for field in ("valid", "paymentType", "coverage", "productionDecision", "contractConfirmationRequired", "manualReviewRequired"):
            if field in expected and result.get(field) != expected[field]:
                reasons.append(f"{field}: expected {expected[field]!r}, got {result.get(field)!r}")
        for expected_field, result_field in (("normalization", "normalizations"), ("errorContains", "errors"), ("warningContains", "warnings")):
            needle = expected.get(expected_field)
            if needle and not any(needle in message for message in result.get(result_field, [])):
                reasons.append(f"{result_field} substring not found: {needle}")
        if expected.get("networkContext") and not result.get("networkContext"):
            reasons.append("expected networkContext")
        if expected.get("sourceId") and expected["sourceId"] not in {source["id"] for source in result.get("sources", [])}:
            reasons.append(f"source id not found: {expected['sourceId']}")
        if reasons:
            failures.append({"name": case.get("name", "unnamed case"), "reasons": reasons, "result": result})
    return {"valid": not failures, "cases": len(cases), "passed": len(cases) - len(failures), "failures": failures}


def main() -> int:
    try:
        args = parse_args()
        catalog = load_catalog()
        if args.command == "list":
            rows = []
            for currency, rule in sorted(catalog["countries"].items()):
                if args.gateway and rule.get("gateway") != args.gateway:
                    continue
                if args.coverage and rule.get("coverage") != args.coverage:
                    continue
                rows.append({"currency": currency, "country": rule.get("country"), "gateway": rule.get("gateway"), "coverage": rule.get("coverage")})
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        if args.command == "show":
            currency = normalize_code(args.currency)
            rule = rule_for(catalog, currency)
            if rule is None:
                raise ValueError(f"currency {currency} is not present in the catalog")
            gateway_key = rule.get("gateway")
            print(json.dumps({"currency": currency, **rule, "endpoint": catalog["gateways"].get(gateway_key), "commonRules": catalog.get("commonRules", {}), "catalogVerifiedAt": catalog.get("verifiedAt"), "sources": resolve_sources(catalog, rule.get("sourceIds", []))}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "explain":
            currency = normalize_code(args.currency)
            rule = rule_for(catalog, currency)
            if rule is None:
                raise ValueError(f"currency {currency} is not present in the catalog")
            input_channel = normalize_code(args.payment_type)
            channel, normalizations = resolve_channel(rule, args.action, input_channel)
            evidence = evidence_for(catalog, rule, args.action, input_channel, channel)
            print(json.dumps({"currency": currency, "action": args.action, "inputPaymentType": input_channel, "paymentType": channel, "normalizations": normalizations, **evidence, "countryNotes": rule.get("notes", [])}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "validate":
            result = validate(args.action, load_body(args), catalog, strict_required=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["valid"] else 2
        if args.command == "check":
            field_map = {
                "paymentType": args.payment_type, "amount": args.amount, "phone": args.phone,
                "email": args.email, "dynamic": args.dynamic, "mchOrderId": args.mch_order_id,
                "purpose": args.purpose, "beneficiaryName": args.beneficiary_name,
                "beneficiaryEmail": args.beneficiary_email,
                "bankCode": args.bank_code, "beneficiaryMobile": args.beneficiary_mobile,
                "beneficiaryAccountNumber": args.beneficiary_account_number,
                "beneficiaryBankCode": args.beneficiary_bank_code,
                "beneficiaryBankName": args.beneficiary_bank_name,
                "beneficiaryAccountType": args.beneficiary_account_type,
                "beneficiaryType": args.beneficiary_type, "beneficiaryId": args.beneficiary_id,
                "ipAddress": args.ip_address, "productUrl": args.product_url,
                "paymentMethod": args.payment_method,
                "docType": args.doc_type, "docNumber": args.doc_number,
                "callbackUrl": args.callback_url,
            }
            body = {"currency": args.currency, **{key: value for key, value in field_map.items() if value is not None}}
            result = validate(args.action, body, catalog, strict_required=False, key_type=args.key_type)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["valid"] else 2
        if args.command == "selftest":
            result = run_selftest(catalog)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["valid"] else 2
        errors, warnings = audit(catalog, args.max_source_age_days)
        print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings, "maxSourceAgeDays": args.max_source_age_days}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
