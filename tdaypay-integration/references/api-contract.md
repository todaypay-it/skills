# TDayPay API contract

Source: [TDayPay public Postman documentation](https://documenter.getpostman.com/view/10814992/2s93XyTNoA).

## Regional gateways

| Region | Gateway | Documented currencies |
|---|---|---|
| `latin` | `https://apis.tdaypay.com/gateway/base/biz` | BRL, MXN, PEN, CLP, COP, ARS, ECS, VES |
| `asia` | `https://api.tdaypay.com/gateway/base/biz` | INR, IDR, RUB, PHP, MYR, BDT, PKR, THB, AED |
| `africa` | `https://afapi.tdaypay.com/gateway/base/biz` | KES, NGN, TZS |

The collection navigation also lists ZAR, USD, EUR, TRY, and VND, but the environment section does not assign all of them to a gateway. Require an explicit reviewed region or endpoint for these currencies.

## Methods and headers

All calls use HTTPS POST with JSON. Required headers:

| Header | Value |
|---|---|
| `serviceName` | `api.pay` |
| `method` | `pay`, `payOut`, `balance`, or `verifyStatus` |
| `mchId` | Merchant ID assigned by TDayPay |
| `signType` | `SHA512` |
| `timestamp` | Unix timestamp in seconds |
| `sign` | Lowercase SHA512 hexadecimal signature |
| `Content-Type` | `application/json` |

Signature input, with no separators:

```text
mchId + serviceName + method + timestamp + signType + exactJsonBody + merchantKey
```

Sign and send the same UTF-8 JSON string. Do not reformat it after signing.

## Response envelope

Common fields:

- `resultCode`: `000000` for a successful API request.
- `errorCode`: business or protocol error code.
- `errorMsg`: error description.
- `data`: action-specific object or array.
- `timestamp`: optional response timestamp.

Selected documented errors:

| Code | Meaning / action |
|---|---|
| `999999` | System error; query before retrying a create call. |
| `999998` | Network error; result may be ambiguous, so query first. |
| `999997` / `999993` | Invalid parameters; correct the request. |
| `999996` / `400005` | Merchant balance insufficient. |
| `999992` | Signature verification failed; compare exact body serialization, timestamp, key, and header values. |
| `999991` | Service is not authorized for the merchant. |
| `999989` | Merchant does not exist. |
| `999977` / `999974` | Request IP or merchant IP whitelist is invalid. |
| `999975` | Merchant is disabled. |
| `400000` | Duplicate order submission; do not create another order blindly. |
| `400001` | Order is already completed. |
| `400004` | Order does not exist. |

Channel-specific `errorMsg` values may be more useful than the generic code. Preserve them in diagnostics without exposing personal data.

## Transaction states

| State | Meaning |
|---|---|
| `PAYING` | Initial/processing state. |
| `SUCCESS` | Successful transaction. |
| `FAILED` | Failed transaction; this can later become successful in documented timeout cases. |
| `REVERSED` | Previously successful transaction was reversed. |

Webhook examples also mention `REFUND`, although the main state table does not define it. Treat unknown states as valid external values to record and escalate rather than coercing them.

Do not model terminal states as immutable. Keep the latest state and an append-only history when integrating with a merchant ledger.

## Callback contract

When a create request supplies `callbackUrl`, TDayPay sends JSON by HTTPS POST. The required request-header `sign` is a SHA512 hexadecimal digest over:

```text
exactRawCallbackBody + merchantKey
```

This differs from outbound request signing: callback signing does not include `mchId`, service name, method, timestamp, or sign type. Capture and verify the original request bytes before JSON parsing; reserialization can change the signature input. Examples are lowercase, but the document does not explicitly specify hex letter case.

Required callback fields are `mchOrderId`, `orderId`, `orderStatus`, `amount`, `orderType`, and UTC `createTime` in `yyyyMMddHHmmss` form. `bankId`, `failMessage`, `transIds`, and `payMethod` are marked optional; `realAmount` has no required/optional marker. Callback amounts are strings with two decimal places even where request-side country rules disallow decimal amounts.

Return HTTP 200 with plain-text body `success` only after durable idempotent processing. The document says non-accepted responses are attempted seven times with an interval that grows as five minutes multiplied by the callback count, but does not say whether the initial delivery is included. Read [callback-validation.md](callback-validation.md) before implementing a receiver.

## Known documentation conflicts

- Only production is documented; OMS mock callbacks do not post real ledger entries.
- Some country examples violate their stated minimum amount.
- Response examples sometimes contain a signature although the common response schema does not fully define response verification.
- Timestamps are documented in seconds, while some examples resemble millisecond timestamps.
- OMS hostnames differ between sections.
- The acknowledgement wording `success` or `200` is ambiguous between response body and HTTP status; returning both HTTP 200 and body `success` satisfies both readings.

Do not silently resolve these conflicts in production code. Surface the relevant ambiguity or obtain confirmation from TDayPay.
