#!/usr/bin/env python3
"""Generate code-comment coverage for TDayPay mandatory validation rules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "rules.json"
LEVELS = ("REQUIRED", "MANUAL_CONFIRMATION", "INFO")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("payment", "payout"))
    parser.add_argument("--currency", required=True)
    parser.add_argument("--payment-type", "--channel", dest="payment_type", required=True)
    parser.add_argument("--language", default="generic")
    parser.add_argument("--format", choices=("json", "comments", "markdown"), default="json")
    return parser.parse_args()


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalize(value: Any) -> str:
    return str(value or "").strip().upper()


def unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def rule_id(*parts: str) -> str:
    return ".".join(re.sub(r"[^A-Z0-9]+", "_", normalize(part)).strip("_") for part in parts if part)


def provider_sources(catalog: dict[str, Any], *nodes: dict[str, Any]) -> list[str]:
    registry = catalog.get("sources", {})
    for node in nodes:
        provider_ids = [source_id for source_id in unique(node.get("sourceIds", [])) if registry.get(source_id, {}).get("sourceType") == "tdaypay-api"]
        if provider_ids:
            return provider_ids
    return [catalog.get("defaultSourceId")]


def source_meta(catalog: dict[str, Any], ids: Iterable[str]) -> tuple[list[str], str | None]:
    registry = catalog.get("sources", {})
    resolved = [source_id for source_id in unique(ids) if source_id in registry]
    dates = [registry[source_id].get("checkedAt") for source_id in resolved if registry[source_id].get("checkedAt")]
    return resolved, max(dates) if dates else None


def add_rule(
    target: list[dict[str, Any]],
    catalog: dict[str, Any],
    identifier: str,
    level: str,
    behavior: str,
    source_ids: Iterable[str],
) -> None:
    resolved, checked_at = source_meta(catalog, source_ids)
    target.append({
        "id": identifier,
        "level": level,
        "behavior": behavior,
        "sourceIds": resolved,
        "checkedAt": checked_at,
    })


def account_rule(kind: str) -> str | None:
    return {
        "clabe": "beneficiaryAccountNumber must be an 18-digit CLABE with a valid 3/7/1 checksum.",
        "bank-card": "beneficiaryAccountNumber is a bank-card identifier; warn and require contract confirmation when it is not 16 digits.",
        "mx-mobile-10": "beneficiaryAccountNumber must be exactly 10 local mobile digits for DIMO.",
        "co-mobile-10": "beneficiaryAccountNumber must be exactly 10 Colombian local mobile digits without +57 for TRANSFIYA.",
        "bre-b-key": "beneficiaryAccountNumber must match the explicitly declared validator key type; do not infer an ambiguous numeric Bre-B key.",
    }.get(kind)


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


def render_comment(rule: dict[str, Any], language: str) -> str:
    prefix, suffix = comment_prefix(language)
    sources = "+".join(rule["sourceIds"]) or "unresolved-source"
    checked = rule.get("checkedAt") or "unverified"
    return f"{prefix}TDAYPAY-RULE[{rule['id']}] [{rule['level']}] {rule['behavior']} Source: {sources}, checked {checked}.{suffix}"


def build_plan(catalog: dict[str, Any], action: str, currency: str, input_channel: str) -> dict[str, Any]:
    errors: list[str] = []
    required: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    info: list[dict[str, Any]] = []
    country = catalog.get("countries", {}).get(currency)
    if country is None:
        return {"valid": False, "errors": [f"currency {currency} is not present in the catalog"]}
    action_rule = country.get(action, {})
    aliases = action_rule.get("channelAliases", {})
    channel = aliases.get(input_channel, input_channel)
    channels = action_rule.get("channels", [])
    if input_channel == "PSE" and action == "payout" and currency == "COP":
        errors.append("PSE is a COP payment alias only and cannot be used for payout")
    elif channel not in channels:
        errors.append(f"{channel} is not a documented {currency} {action} channel")
    channel_rule = action_rule.get("channelRules", {}).get(channel, {})

    common_rule = catalog.get("commonRules", {}).get(action, {})
    common_sources = common_rule.get("sourceIds", [catalog.get("defaultSourceId")])
    if common_rule.get("requiredBodyFields"):
        fields = ", ".join(common_rule["requiredBodyFields"])
        add_rule(required, catalog, rule_id("COMMON", action, "REQUIRED_FIELDS"), "REQUIRED", f"Reject before signing when any common {action} body field is missing: {fields}.", common_sources)
    if "amount" in common_rule.get("requiredBodyFields", []):
        add_rule(required, catalog, rule_id("COMMON", action, "AMOUNT_POSITIVE"), "REQUIRED", "amount must be finite and greater than zero.", common_sources)
    if "currency" in common_rule.get("requiredBodyFields", []):
        add_rule(required, catalog, rule_id("COMMON", action, "CURRENCY"), "REQUIRED", "currency must be a three-letter code and must resolve to the reviewed regional gateway.", common_sources)
    if "beneficiaryEmail" in common_rule.get("requiredBodyFields", []):
        add_rule(required, catalog, rule_id("COMMON", action, "BENEFICIARY_EMAIL"), "REQUIRED", "beneficiaryEmail must be syntactically valid.", common_sources)
    if "beneficiaryMobile" in common_rule.get("requiredBodyFields", []):
        add_rule(required, catalog, rule_id("COMMON", action, "BENEFICIARY_MOBILE"), "REQUIRED", "beneficiaryMobile must satisfy the common phone format before stricter country validation.", common_sources)
    if "email" in common_rule.get("requiredBodyFields", []):
        add_rule(required, catalog, rule_id("COMMON", action, "EMAIL"), "REQUIRED", "email must be syntactically valid.", common_sources)
    for field, constraint in common_rule.get("fieldConstraints", {}).items():
        minimum = constraint.get("minLength")
        maximum = constraint.get("maxLength")
        if minimum is not None and maximum is not None:
            behavior = f"{field} length must be between {minimum} and {maximum} characters."
        elif minimum is not None:
            behavior = f"{field} must be at least {minimum} characters."
        elif maximum is not None:
            behavior = f"{field} must be at most {maximum} characters."
        else:
            continue
        add_rule(required, catalog, rule_id("COMMON", action, field, "LENGTH"), "REQUIRED", behavior, common_sources)
    headers = common_rule.get("headers", {})
    if headers:
        constants = ", ".join(f"{name}={value}" for name, value in headers.items() if value not in {"required", "Unix timestamp in seconds", "lowercase SHA512 signature over the exact JSON body"})
        add_rule(required, catalog, rule_id("COMMON", action, "HEADERS"), "REQUIRED", f"Build the required TDayPay headers with the action constants: {constants}; mchId, timestamp, and sign are required.", common_sources)
        add_rule(required, catalog, rule_id("COMMON", action, "SIGN_EXACT_BODY"), "REQUIRED", "Sign and send the same exact UTF-8 JSON bytes; reject any flow that serializes the body again after signing.", common_sources)

    selected_provider_sources = provider_sources(catalog, channel_rule, action_rule, country)
    if channel in channels:
        add_rule(required, catalog, rule_id(currency, action, channel, "PAYMENT_TYPE"), "REQUIRED", f"paymentType must equal the canonical channel {channel} for this integration path.", selected_provider_sources)
    if input_channel != channel:
        add_rule(required, catalog, rule_id(currency, action, input_channel, "ALIAS"), "REQUIRED", f"Normalize {input_channel} to {channel} only for {currency} {action}; preserve the original term for audit output.", selected_provider_sources)
    if action_rule.get("requiredFields"):
        fields = ", ".join(action_rule["requiredFields"])
        add_rule(required, catalog, rule_id(currency, action, "REQUIRED_FIELDS"), "REQUIRED", f"Reject when any {currency} {action} field is missing: {fields}.", selected_provider_sources)
    for field, expected in action_rule.get("requiredValues", {}).items():
        add_rule(required, catalog, rule_id(currency, action, field, "FIXED"), "REQUIRED", f"{field} must equal {expected}.", selected_provider_sources)
    for field, expected in action_rule.get("optionalFixedValues", {}).items():
        add_rule(required, catalog, rule_id(currency, action, field, "IF_PRESENT"), "REQUIRED", f"If {field} is supplied, it must equal {expected}; omission selects the provider's aggregate checkout.", selected_provider_sources)
    for field, allowed in action_rule.get("allowedValues", {}).items():
        add_rule(required, catalog, rule_id(currency, action, field, "ENUM"), "REQUIRED", f"{field} must be one of: {', '.join(allowed)}.", selected_provider_sources)
    for field, conditional in action_rule.get("conditionalPatterns", {}).items():
        selector = conditional.get("selector", "selector")
        descriptions = conditional.get("descriptions", {})
        variants = "; ".join(f"{selector}={value}: {description}" for value, description in descriptions.items())
        add_rule(required, catalog, rule_id(currency, action, field, "CONDITIONAL"), "REQUIRED", f"Validate {field} according to {selector}: {variants}.", selected_provider_sources)
    for field, format_rule in action_rule.get("formatRules", {}).items():
        if format_rule.get("kind") == "ip":
            behavior = f"{field} must be a syntactically valid IPv4 or IPv6 address; verify separately that production code captures the actual payer-device IP."
        elif format_rule.get("kind") == "httpUrl":
            behavior = f"{field} must be an absolute HTTP or HTTPS URL with a host."
        else:
            continue
        add_rule(required, catalog, rule_id(currency, action, field, "FORMAT"), "REQUIRED", behavior, selected_provider_sources)
    if channel_rule.get("requiredFields"):
        fields = ", ".join(channel_rule["requiredFields"])
        add_rule(required, catalog, rule_id(currency, action, channel, "REQUIRED_FIELDS"), "REQUIRED", f"Reject when any {currency} {action} {channel} field is missing: {fields}.", selected_provider_sources)
    for field, expected in channel_rule.get("requiredValues", {}).items():
        add_rule(required, catalog, rule_id(currency, action, channel, field, "FIXED"), "REQUIRED", f"{field} must equal {expected} for {currency} {action} {channel}.", selected_provider_sources)
    for field, allowed in channel_rule.get("allowedValues", {}).items():
        add_rule(required, catalog, rule_id(currency, action, channel, field, "ENUM"), "REQUIRED", f"{field} must be one of: {', '.join(allowed)}.", selected_provider_sources)
    for field, constraint in action_rule.get("fieldConstraints", {}).items():
        maximum = constraint.get("maxLength")
        if maximum is not None:
            add_rule(required, catalog, rule_id(currency, action, field, "MAX_LENGTH"), "REQUIRED", f"{field} must be at most {maximum} characters.", selected_provider_sources)
    forbidden = channel_rule.get("mchOrderIdForbids")
    if forbidden:
        add_rule(required, catalog, rule_id(currency, action, channel, "ORDER_ID"), "REQUIRED", f"mchOrderId must not contain {forbidden!r}.", selected_provider_sources)
    kind_message = account_rule(channel_rule.get("beneficiaryAccountNumberKind", ""))
    if kind_message:
        add_rule(required, catalog, rule_id(currency, action, channel, "ACCOUNT_IDENTIFIER"), "REQUIRED", kind_message, channel_rule.get("sourceIds", selected_provider_sources))

    amount_rule = action_rule.get("amount", country.get("amount", {}))
    if amount_rule.get("decimalsAllowed", country.get("amount", {}).get("decimalsAllowed")) is False:
        add_rule(required, catalog, rule_id(currency, action, "AMOUNT_INTEGER"), "REQUIRED", f"{currency} {action} amount must be an integer; reject decimal values before signing.", selected_provider_sources)
    phone_rule = country.get("phone", {})
    if phone_rule.get("localDigitsWithoutCountryCode"):
        digits = phone_rule["localDigitsWithoutCountryCode"]
        country_code = phone_rule.get("countryCode")
        field = "phone" if action == "payment" else "beneficiaryMobile"
        add_rule(required, catalog, rule_id(currency, action, field), "REQUIRED", f"{field} must be {digits} local digits or {country_code} followed by {digits} digits.", selected_provider_sources)
    minimum = amount_rule.get("min")
    maximum = amount_rule.get("max")
    if minimum is not None or maximum is not None:
        if amount_rule.get("limitsConflictWithExamples", country.get("amount", {}).get("limitsConflictWithExamples")):
            add_rule(manual, catalog, rule_id(currency, action, "AMOUNT_RANGE_CONFLICT"), "MANUAL_CONFIRMATION", f"The documented range {minimum}-{maximum} {currency} conflicts with public examples; block production outside the range until the current merchant contract is confirmed.", selected_provider_sources)
        else:
            add_rule(required, catalog, rule_id(currency, action, "AMOUNT_RANGE"), "REQUIRED", f"amount must be between {minimum} and {maximum} {currency}.", selected_provider_sources)

    advisory_target = info if action == "payout" else manual
    advisory_level = "INFO" if action == "payout" else "MANUAL_CONFIRMATION"
    for message in [*common_rule.get("manualConfirmations", []), *action_rule.get("manualConfirmations", []), *channel_rule.get("manualConfirmations", [])]:
        add_rule(advisory_target, catalog, rule_id(currency, action, channel, "CONFIRM", str(len(advisory_target) + 1)), advisory_level, message, selected_provider_sources)
    if channel_rule.get("beneficiaryActivationRequired"):
        add_rule(advisory_target, catalog, rule_id(currency, action, channel, "ACTIVATION"), advisory_level, f"Confirm the beneficiary has activated or registered {channel}; local code cannot prove it.", selected_provider_sources)

    network_key = "PSE" if action == "payment" and (input_channel == "PSE" or channel == "NET_BANKING") else channel
    network = country.get("networkFacts", {}).get(network_key)
    if network:
        for index, fact in enumerate(network.get("facts", []), start=1):
            add_rule(info, catalog, rule_id(currency, network_key, "NETWORK", str(index)), "INFO", fact, network.get("sourceIds", []))

    return {
        "valid": not errors,
        "errors": errors,
        "action": action,
        "currency": currency,
        "inputPaymentType": input_channel,
        "paymentType": channel,
        "normalizations": [f"{input_channel} -> {channel}"] if input_channel != channel else [],
        "coverage": country.get("coverage"),
        "requiredRules": required,
        "manualConfirmationRules": manual,
        "informationalRules": info,
        "requiredCommentCount": len(required),
    }


def render_markdown(plan: dict[str, Any], language: str) -> str:
    lines = [f"# TDayPay rule comment plan: {plan.get('currency')} {plan.get('action')} {plan.get('paymentType')}"]
    for key, title in (("requiredRules", "Required"), ("manualConfirmationRules", "Manual confirmation"), ("informationalRules", "Information")):
        lines.extend(["", f"## {title}"])
        rules = plan.get(key, [])
        lines.extend(f"- `{rule['id']}` — {rule['behavior']}" for rule in rules) if rules else lines.append("- None")
    lines.extend(["", "## Rendered comments", "", "```", *[render_comment(rule, language) for rule in plan.get("requiredRules", [])], "```"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        catalog = load_catalog()
        plan = build_plan(catalog, args.action, normalize(args.currency), normalize(args.payment_type))
        all_rules = [*plan.get("requiredRules", []), *plan.get("manualConfirmationRules", []), *plan.get("informationalRules", [])]
        plan["renderedComments"] = [render_comment(rule, args.language) for rule in all_rules]
        if args.format == "comments":
            print("\n".join(render_comment(rule, args.language) for rule in plan.get("requiredRules", [])))
        elif args.format == "markdown":
            print(render_markdown(plan, args.language))
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0 if plan.get("valid") else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
