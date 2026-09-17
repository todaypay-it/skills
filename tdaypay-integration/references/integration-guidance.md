# Integration guidance

Use this reference during Stage 1 and when adapting generated rule comments to a project language.

## Project discovery

Confirm findings from `inspect_project.py` with nearby production code. Prefer a repository's established choice over the table below.

| Signal | Inspect for |
|---|---|
| Stack | `package.json`, `pyproject.toml`, `requirements*.txt`, `go.mod`, `pom.xml`, Gradle files, `.csproj`, `composer.json`, `Gemfile`, `Cargo.toml` |
| HTTP | Existing third-party client wrappers, timeout/retry policy, proxy/TLS configuration |
| Configuration | Environment binding, secret manager, typed settings, per-environment validation |
| Validation | Existing schema/DTO/annotation library and error-envelope conventions |
| Persistence | Order aggregate/repository, idempotency keys, append-only state history |
| Async flow | Webhook routes, queue consumers, scheduled status queries, signature verification |
| Observability | Structured logger, trace/correlation ID, metrics, sensitive-field redaction |
| Tests | Framework, fixtures, HTTP mocks/fakes, golden serialization tests, integration-test boundaries |

Typical library signals are evidence, not prescriptions:

- TypeScript/JavaScript: `fetch`, Axios, Undici; Zod, Joi, class-validator; Jest, Vitest.
- Python: HTTPX, Requests, aiohttp; Pydantic, Marshmallow; pytest.
- Java/Kotlin: Spring `RestClient`/`WebClient`, OkHttp; Bean Validation; JUnit.
- Go: `net/http` or an existing wrapper; validator packages; standard testing/testify.
- C#/.NET: `HttpClient`, options binding, data annotations/FluentValidation, xUnit/NUnit.
- PHP: Guzzle/Symfony HTTP client, framework validators, PHPUnit/Pest.

Reuse a detected library when it satisfies exact-body signing and timeout requirements. Introduce a new dependency only when the integration decision explains why the existing stack cannot meet a required invariant.

## Integration decision template

Present this before editing code:

```text
Detected stack and conventions:
- Language/framework/package manager:
- Existing HTTP/config/validation/logging/test choices:
- Closest existing external-provider module:

Business flow:
- Actions, countries/currencies, channels:
- Synchronous caller and response expectation:
- Callback/query/status-history behavior:
- Idempotency and persistence owner:

Proposed module:
- Seam and small interface:
- Production adapter and test adapter:
- Exact serialization/signing ownership:
- Country-rule validation ownership:
- Error mapping and masking:

Files and tests:
- Files to create/change:
- Tests and commands:
- Generated REQUIRED comment count and unresolved rules:

Decision needed:
- Confirm this integration approach before implementation.
```

## Module shape

Prefer one deep TDayPay module at the project's existing external-payment seam. A representative interface may expose only the operations the business uses, such as `createPayment`, `createPayout`, `getStatus`, and `getBalance`. Keep these behind the interface:

- region routing and headers;
- common plus country/channel validation;
- canonical JSON serialization and SHA512 signing;
- HTTP transport, timeout classification, and response parsing;
- provider error mapping and sensitive-field masking.

Use a production HTTP adapter and an in-memory/mock adapter for tests. Avoid exposing signing primitives or country-rule internals to every caller.

## Business-flow choices

- Payment creation usually returns a checkout URL and begins in `PAYING`; design the redirect and callback path before coding.
- Payout creation needs merchant-order uniqueness, beneficiary validation, balance-failure handling, and an explicit policy for asynchronous completion. Default to straight-through execution after validation and existing authorization; do not introduce a new manual review or approval state unless it already belongs to the business process or the user requests it.
- Status query accepts TDayPay platform order IDs, not merchant order IDs, and supports up to 200 IDs per call.
- An ambiguous timeout is not a safe retry signal. Reconcile or query before creating another order.
- Preserve status history because documented transitions include `SUCCESS -> REVERSED` and `FAILED -> SUCCESS`.

For callback routes, find the framework-specific raw-body hook before choosing middleware. The callback module should own signature verification, schema validation, durable event deduplication, state-history append, ledger dispatch, and acknowledgement. A controller that receives only an already-parsed object cannot reliably reproduce the signed JSON string.

## Rule-comment contract

Generated comments use this semantic form:

```text
TDAYPAY-RULE[<rule-id>] [REQUIRED] <behavior>. Source: <source-id>, checked <date>.
```

Examples:

```typescript
// TDAYPAY-RULE[COP.PAYOUT.AMOUNT.INTEGER] [REQUIRED] COP payout amounts must be integers; reject before signing. Source: tdaypay-public, checked 2026-09-10.
```

```python
# TDAYPAY-RULE[MXN.PAYOUT.SPEI.CLABE] [REQUIRED] SPEI payout requires an 18-digit CLABE with a valid checksum. Source: tdaypay-mxn-payout+banxico-clabe, checked 2026-09-10.
```

```java
// TDAYPAY-RULE[COP.PAYMENT.PSE.ALIAS] [REQUIRED] Normalize PSE to NET_BANKING only for COP payment. Source: tdaypay-cop-payment, checked 2026-09-10.
```

Use `MANUAL_CONFIRMATION` for facts that code cannot prove, such as merchant enablement, account ownership, a registered Bre-B key, or current contract resolution. For payout, surface those facts as non-blocking `INFO` operational advisories; only an unresolved provider/merchant-contract conflict blocks production readiness. Use `INFO` for national-network behavior that does not define the TDayPay request.

## Completion criteria

Integration is ready for review when:

- the user-confirmed module and flow are implemented in project style;
- every generated `REQUIRED` rule is enforced and annotated, or listed as an unresolved gap;
- signing tests prove the exact serialized body is the one sent;
- error, timeout, query, and masking tests pass;
- callback tests cover raw-body signing, tampering/reordered JSON, durable duplicate handling, non-monotonic status changes, and acknowledgement after persistence;
- no merchant key or unmasked personal/bank data appears in code, fixtures, logs, or reports;
- production execution occurs only when the current request explicitly authorizes it.
