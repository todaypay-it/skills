# TDayPay callback validation

Verified on 2026-09-10 from the [TDayPay Webhook contract](https://documenter.getpostman.com/view/10814992/2s93XyTNoA#api-webhook-callback) and the [COP TRANSFIYA payout item](https://documenter.getpostman.com/view/10814992/2s93XyTNoA#fb2ecd91-ea25-489b-a8fb-3c95a35ab230).

The TRANSFIYA request accepts `callbackUrl`, but the callback transport and signature are defined by the common Webhook section. Do not invent a TRANSFIYA-only signature or response format.

## Verified contract

- TDayPay sends HTTPS `POST` callbacks with a JSON request body when a create request contains `callbackUrl`.
- The request header `sign` is required.
- The signature is hexadecimal `SHA512(raw JSON body + merchantKey)` with no separator. Examples are lowercase, but the document does not explicitly require a particular hex letter case.
- The callback JSON requires `mchOrderId`, `orderId`, `orderStatus`, `amount`, `orderType`, and `createTime`.
- `bankId`, `failMessage`, `transIds`, and `payMethod` are marked optional. `realAmount` has no required/optional marker; validate it when present but do not reject solely because it is absent.
- `amount` and `realAmount` are strings shown with two decimal places. This callback representation is separate from country request rules such as COP's prohibition on decimal request amounts; a valid COP callback can contain `"5000.00"`.
- `orderType` is `PAYMENT` or `PAYOUT`.
- Documented callback statuses are `SUCCESS`, `FAILED`, `REVERSED`, `PAYING`, and `REFUND`. The main state table omits `REFUND`, so preserve unknown authenticated states and query rather than coercing them.
- `createTime` is UTC in `yyyyMMddHHmmss` format.
- TDayPay considers `success` or HTTP `200` an accepted callback. Return both HTTP 200 and the exact plain-text body `success` to avoid the documentation ambiguity.
- A non-accepted response triggers retries. The stated schedule increases by `5 minutes × callback attempt number`, with seven attempts.
- TDayPay can send the same order callback more than once. Statuses are not immutable: `SUCCESS` can become `REVERSED`, and `FAILED` can later become `SUCCESS`, including payout.

The document does not define a callback timestamp header, nonce, event ID, response signature, or replay-expiry window. Do not invent these as provider requirements.

## Safe processing order

1. Capture the untouched HTTP request bytes before the framework JSON parser consumes or normalizes them.
2. Read the `sign` header case-insensitively. Require a 128-character hexadecimal SHA512 value; examples are lowercase, but the document does not specify hex letter case.
3. Compute SHA512 over the raw request bytes followed by the UTF-8 merchant key and compare in constant time.
4. Reject unauthenticated data without parsing it into business commands or exposing the calculated signature.
5. Parse UTF-8 JSON and validate the documented field types and formats.
6. Resolve the local order by both `orderId` and the stored `mchOrderId` association; a mismatch is a security/integrity error.
7. In one transaction, durably record an event fingerprint and the provider status history before applying ledger effects. Deduplicate an identical event fingerprint, not every callback sharing an `orderId`.
8. Apply each financial side effect idempotently. Preserve distinct transitions and compensating behavior, including `SUCCESS -> REVERSED` and `FAILED -> SUCCESS`.
9. Return HTTP 200 with `Content-Type: text/plain` and body `success` only after the event and processing outcome are durable. An authenticated duplicate already processed successfully should receive the same acknowledgement.

If the authenticated payload contains an unknown status, durably record it, quarantine ledger effects, query TDayPay, and acknowledge only after the quarantine record is durable. This avoids both silent coercion and an uncontrolled retry storm.

## Source-IP defense in depth

The environment section currently lists these callback IPs:

- Latin America: `18.228.164.232`, `18.228.73.43`, `54.233.252.236`, `54.94.8.45`
- Asia: `13.200.70.4`, `15.207.47.92`, `3.108.48.106`, `43.205.72.188`

No Africa callback IP list is documented there. Treat the IP list as defense in depth, not a replacement for the signature. Resolve the actual peer IP only through explicitly trusted proxies; do not trust an arbitrary `X-Forwarded-For` value. Recheck the list before changing production firewall rules.

## Logging and test requirements

- Never log the merchant key, supplied/calculated signature, or complete raw callback body.
- Mask order identifiers and avoid logging bank IDs, account data, payer/beneficiary identity, email, or phone.
- Test exact raw-body signing, reordered JSON failure, tampering, missing/uppercase signature, malformed UTF-8/JSON, missing fields, amount scale, UTC time, all documented statuses, unknown status quarantine, duplicate delivery, concurrent duplicates, reversible state transitions, persistence failure before acknowledgement, and the seven-retry contract.
- Use OMS `mock success` and `mock fail` only for callback transport verification; the document says these mock transactions do not post real ledger entries.

Run the bundled verifier without sending a transaction:

```bash
TDAYPAY_MERCHANT_KEY='<secret>' python3 scripts/tdaypay_callback.py verify \
  --body-file callback.raw.json --sign '<sign-header>' \
  --region latin --source-ip 18.228.164.232
```

Generate the minimum code-comment plan:

```bash
python3 scripts/tdaypay_callback.py comments --language typescript --format comments
```
