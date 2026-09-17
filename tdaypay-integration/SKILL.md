---
name: tdaypay-integration
description: Plan and implement TDayPay integrations in an existing codebase. Use when the user wants TDayPay payment, payout, balance, status-query, or callback code adapted to their business flow, project stack, and code conventions, with country-rule-derived validation comments; confirm the integration design before editing code and require explicit current-request authorization for a production transaction.
---

# TDayPay Integration

Use this skill as the single integration entry point. It combines TDayPay transaction preparation/execution with country and channel rules, while keeping provider rules distinct from payment-network facts.

## Stage 1: discover and confirm the integration

Inspect before editing:

1. Run `scripts/inspect_project.py --root <project-root>` and verify its findings against manifests, nearby modules, tests, configuration, and existing HTTP integrations.
2. Identify the business flow: `payment`, `payout`, `balance`, `query`, or callback; countries/currencies; channels; synchronous response handling; asynchronous status updates; idempotency owner; and whether production execution is in scope.
3. Read [references/api-contract.md](references/api-contract.md) and [references/fields.md](references/fields.md). For each country/channel, run `scripts/country_rules.py explain <action> --currency <CODE> --payment-type <CHANNEL>` and read the relevant section of [references/country-catalog.md](references/country-catalog.md). When `callbackUrl`, webhook receipt, or asynchronous status handling is in scope, also read [references/callback-validation.md](references/callback-validation.md).
4. Propose one integration decision that fits the detected stack and conventions. Include the module seam and interface, existing HTTP/config/validation/logging libraries to reuse, request and callback flow, persistence/idempotency approach, files to change, test strategy, and unresolved business choices.
5. Ask the user to confirm that integration decision. Completion of Stage 1 is an explicit confirmation; do not edit the target project before it.

If the project cannot be inspected, report the missing path or files and request them rather than guessing a stack or code style. Read [references/integration-guidance.md](references/integration-guidance.md) when choosing the module shape or adapting comments to a language.

## Stage 2: implement after confirmation

Place one deep TDayPay module at the seam already used for external payment providers. Keep signing, exact serialization, routing, country validation, response interpretation, and retry safety behind a small interface. Inject the HTTP client and time source when the project already uses dependency injection or when a production adapter plus test adapter makes the seam real.

Follow the repository's established:

- language, framework, package manager, naming, formatting, and file layout;
- HTTP client, configuration, secret-loading, logging, error, and result types;
- test framework, fixtures, dependency injection, and mocking style;
- controller, job, domain, persistence, and webhook boundaries.

Store `mchId` and `merchantKey` through the project's existing secret mechanism. Preserve the exact UTF-8 JSON serialized for signing and sending. Use the vendored `scripts/tdaypay_request.py` as an executable contract/reference, not as permission to bypass the project's architecture.

For payout, implement straight-through execution after deterministic validation and the project's existing authorization checks. Do not add a new approval queue, dual control, human review, hold state, or reviewer role merely because the operation is a payout. Reuse an existing approval workflow only when it is already part of the business process, and add a new one only when the user explicitly requests it. Country-rule `manualConfirmations` are non-blocking integration or operational advisories, not per-transaction approval requirements; a documented contract conflict can still block production readiness until it is resolved.

## Implement callback validation

When callbacks are in scope, use the framework's raw-body facility and implement this order:

1. Capture the untouched request bytes before JSON parsing. Verify the `sign` header as hexadecimal `SHA512(rawBody + merchantKey)` with a constant-time comparison. Examples are lowercase, but the provider does not explicitly specify hex letter case.
2. Parse only an authenticated UTF-8 JSON object. Validate the required fields, string types, two-decimal callback amounts, `PAYMENT|PAYOUT`, and UTC `yyyyMMddHHmmss` time. Do not apply request-side COP integer formatting to callback amounts such as `5000.00`.
3. Resolve and cross-check the stored `orderId` and `mchOrderId` relationship. Durably record a raw-body fingerprint and append-only status event before financial side effects.
4. Deduplicate identical callback events, not the whole order. Preserve and handle distinct transitions such as `SUCCESS -> REVERSED` and `FAILED -> SUCCESS`; quarantine `REFUND` and authenticated unknown statuses until their ledger meaning is confirmed, then query TDayPay.
5. Return HTTP 200 with exact plain-text body `success` only after the event and processing outcome are durable. Return the same acknowledgement for an authenticated duplicate already processed successfully.

Use documented regional callback IPs only as defense in depth after trusted-proxy resolution; signature validation remains mandatory. Never log the raw callback, merchant key, supplied/calculated signature, or unmasked financial/identity fields.

Generate callback validation comments with:

```bash
python3 scripts/tdaypay_callback.py comments --language <LANGUAGE> --format comments
```

Put every generated `[REQUIRED]` callback comment next to the validation or transactional idempotency block it governs. Use `scripts/tdaypay_callback.py verify` for offline payload/signature diagnosis; it must receive the untouched body file and reads the key only from `TDAYPAY_MERCHANT_KEY`.

## Generate mandatory validation comments

Before writing validation code, run:

```bash
python3 scripts/rule_comment_plan.py <payment|payout> \
  --currency <CODE> --payment-type <CHANNEL> --language <LANGUAGE>
```

Treat the generated plan as the minimum annotation coverage for deterministic hard rules:

- Put a concise `TDAYPAY-RULE[...] [REQUIRED]` comment immediately above the validation or validation block it explains.
- Include action, currency, canonical channel, behavior, provider `sourceId`, and `checkedAt` date. Preserve alias normalization in the comment plan.
- Comment every country/channel rule whose violation blocks the request, including fixed values, decimal prohibition, required fields, enums, identifier formats, and checksums. A grouped validation block may use one comment when it enforces one coherent rule set.
- Keep payment-network context as `INFO` or `MANUAL_CONFIRMATION`; never present it as proof of TDayPay merchant enablement. For payout, treat these as non-blocking operational notes rather than an approval workflow.
- Regenerate and compare the plan whenever `references/rules.json`, currency, action, or channel changes. Code and comments are complete only when every generated `REQUIRED` rule is implemented or explicitly reported as an unresolved gap.

Use the project's normal comment syntax and tone. Comments explain non-obvious business constraints; ordinary null checks need no separate prose beyond the rule block that owns them.

## Verify the integration

For both `payment` and `payout`, validate the final request body with `scripts/country_rules.py validate` before signing. For `balance` and `query`, apply the corresponding API contract because no country/channel body rules apply. Add project-native tests for:

- exact JSON serialization and a stable signing vector;
- public and channel-required fields, fixed values, enums, amount scale/range conflicts, and identifier format;
- merchant-order idempotency and ambiguous timeout behavior;
- `HTTP 200` versus `resultCode=000000` versus final transaction status;
- callback/query state history, including non-monotonic documented transitions;
- masking of credentials, signatures, accounts, identity, email, phone, and callback data.

Run the repository's formatter, focused tests, and applicable build/type checks. Also run:

```bash
python3 scripts/country_rules.py audit --max-source-age-days 365
python3 scripts/country_rules.py selftest
python3 scripts/tdaypay_callback.py selftest
python3 scripts/integration_selftest.py
```

Report validation coverage, generated-comment coverage, tests run, unresolved rules, and production readiness.

Read [references/integration-eval-cases.md](references/integration-eval-cases.md) when forward-testing material workflow changes.

## Production boundary

All documented gateways are production. Preparation, code generation, and confirmation of the integration design do not authorize a live request. An explicit instruction in the current user request to send to production—such as “生产发送” or “立即发送”—is sufficient action-time authorization: show the masked summary and send without asking for a redundant confirmation. Ask only when live sending was not explicitly authorized, the request is ambiguous, or material transaction details changed after authorization. This execution boundary must not be implemented as an approval step in the user's payout system. Return the safely masked HTTP status and response body even on failure. On timeout or an ambiguous create result, query before retrying.

This skill does not implement OMS administration, 2FA binding, reconciliation, or arbitrary refunds unless the user explicitly expands the scope.
