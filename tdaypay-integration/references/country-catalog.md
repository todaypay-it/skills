# TDayPay country catalog

Verified on 2026-09-10 from the [TDayPay public Postman document](https://documenter.getpostman.com/view/10814992/2s93XyTNoA) and the official payment-network sources registered in `rules.json`.

This is a conservative rules snapshot, not a promise that a channel, bank, wallet, amount, or identifier is enabled for a particular `mchId`. TDayPay API rules and national payment-network facts are deliberately separate.

## Gateway routing

| Gateway key | Endpoint | Documented currencies |
|---|---|---|
| `latin` | `https://apis.tdaypay.com/gateway/base/biz` | BRL, MXN, PEN, CLP, COP, ARS, ECS, VES |
| `asia` | `https://api.tdaypay.com/gateway/base/biz` | INR, IDR, RUB, PHP, MYR, BDT, PKR, THB, AED |
| `africa` | `https://afapi.tdaypay.com/gateway/base/biz` | KES, NGN, TZS |

ZAR, USD, EUR, TRY, and VND appear in public navigation but lack a reviewed gateway mapping in the available contract. They remain `unmapped`.

## Payment common contract

Apply this layer before country and channel supplements.

Required JSON body fields are `mchOrderId`, `amount`, `currency`, `productinfo`, `firstname`, `lastname`, `email`, and `phone`. `mchOrderId` is unique in the merchant system and 5-32 characters; `productinfo` is 1-100 characters; `email` must be syntactically valid; and `phone` is 6-20 characters before stricter country/channel validation. Common optional fields are `callbackUrl`, `redirectUrl`, `noPayPage`, and `paymentType`, although a country/channel can make `paymentType` mandatory.

Common request headers are `serviceName=api.pay`, `method=pay`, `mchId`, `signType=SHA512`, Unix-seconds `timestamp`, lowercase SHA512 `sign`, and `Content-Type=application/json`. The signature must cover the exact JSON bytes later sent.

A synchronous `orderId` or `resultCode=000000` proves API acceptance only, not final payment completion.

## Payout common contract

Apply this layer before country and channel supplements.

Required JSON body fields:

| Field | Common rule |
|---|---|
| `mchOrderId` | Required and unique in the merchant system. |
| `amount` | Required, finite, and greater than zero; country/channel scale and limits can be stricter. |
| `currency` | Required three-letter currency code. |
| `purpose` | Required payout purpose or description. |
| `beneficiaryName` | Required beneficiary name; use the legal account-holder name when ownership is checked. |
| `beneficiaryEmail` | Required syntactically valid email. |
| `beneficiaryMobile` | Required valid phone; country/channel format can be stricter. |
| `beneficiaryAccountNumber` | Required bank, wallet, phone, key, or channel-specific identifier. |

Optional in the common contract but frequently mandatory for a country/channel: `paymentType`, `beneficiaryBankCode` or `beneficiaryBankName`, `beneficiaryAccountType`, `docType`, `docNumber`, and `callbackUrl`.

Common request headers are `serviceName=api.pay`, `method=payOut`, `mchId`, `signType=SHA512`, Unix-seconds `timestamp`, lowercase SHA512 `sign`, and `Content-Type=application/json`. The signature must cover the exact JSON bytes later sent; the bundled transaction helper prepares or sends that exact body.

A synchronous `orderId` or `resultCode=000000` proves API acceptance only, not that funds reached the beneficiary.

## Coverage summary

| Country / currency | Coverage | Documented collection channels | Documented payout channels |
|---|---|---|---|
| Mexico / MXN | detailed, with conflicts | `SPEI`, `OXXO_PAY`, `CASH` | `SPEI`, `NET_BANKING`, `DIMO` |
| Colombia / COP | detailed, with conflicts | `NET_BANKING` (PSE alias), `BRE_B`, `NEQUI` | `NET_BANKING`, `TRANSFIYA`, `BRE_B` |
| BRL, PEN, CLP, ARS, ECS, VES | routing-only | unknown | unknown |
| INR, IDR, RUB, PHP, MYR, BDT, PKR, THB, AED | routing-only | unknown | unknown |
| KES, NGN, TZS | routing-only | unknown | unknown |
| ZAR, USD, EUR, TRY, VND | unmapped | unknown | unknown |

Channel lists come from the public provider document and remain merchant-dependent and non-exhaustive.

## Mexico / MXN

### Collection

- Explicit `SPEI` requires `dynamic=4`, although the same table labels the field optional. The Skill treats the channel-specific fixed value as required and exposes the documentation conflict.
- `dynamic=4` permits repeated payments against the generated CLABE. Callback processing must deduplicate by `bankId` and book `realAmount`.
- Mexico collection `mchOrderId` must not contain `_`.
- The public payment item has no authoritative MXN collection amount bounds.

### Payout

- `paymentType`, `beneficiaryBankCode`, and `beneficiaryAccountNumber` are required.
- `SPEI` requires an 18-digit CLABE. The Skill validates Banco de México's 3/7/1 checksum but does not claim the account exists or is owned by the beneficiary.
- `NET_BANKING` is described as a bank-card account; a non-16-digit value is a warning until the current contract confirms the exact provider format.
- `DIMO` requires a 10-digit local mobile number.
- The narrative range is 40-15,000 MXN, but a public saved example uses 1.00. Outside-range values return `CONTRACT_CONFIRMATION_REQUIRED` rather than silent approval.
- A payout can move from `SUCCESS` to `REVERSED`; downstream ledgers must not treat the first success as immutable.

## Colombia / COP

### Common rules

- Payment and payout amounts do not support decimals.
- The stated range is 5,000-3,000,000 COP, but official examples use smaller values. Outside-range values therefore require current contract confirmation.
- A Colombian phone is 10 local digits; payment may also present `+57` followed by 10 digits for validation. Channel-specific request format can be stricter.

### Collection

- `PSE` is a user-facing alias for API `NET_BANKING` only when `action=payment`. Payout `PSE` is rejected.
- The COP supplement requires `paymentType`, `beneficiaryType`, `beneficiaryId`, `ipAddress`, and `productUrl` in addition to the common payment fields. Payer names remain the common lowercase `firstname` and `lastname`; do not invent extra `firstName` or `lastName` fields.
- `beneficiaryType` is `CC` or `NIT`; the corresponding `beneficiaryId` is 6-10 digits for `CC` and exactly 9 digits for `NIT`.
- `ipAddress` must be the actual payer-device IP captured at request time, and `productUrl` must be an absolute HTTP(S) product URL. The public example's loopback IP is not a production value.
- `paymentMethod` is optional. If the merchant supplies it for its own checkout or a standalone checkout method, it must be `API`; omitting it selects TDayPay's aggregate checkout.
- `NET_BANKING` requires `bankCode` from the provider's current COP payment bank table, real payer contact/identity data, and runtime confirmation of PSE registration, bank limits, and merchant enablement.
- Saved examples omit `bankCode` or use the bank name `ITAU`, while the field table requires a numeric code; validation follows the table and uses `006` for ITAU.
- Direct `NEQUI` uses the payer's Nequi app approval flow. Do not auto-add `bankCode=507` or conflate it with PSE.
- `BRE_B` collection is documented as QR. Do not require a recipient key or bank code merely because the Bre-B network also supports those concepts.
- `CASH` is described as unsupported and `BRE_KEY` lacks enough public request rules; neither is listed as a validated channel.
- The document's anti-automation recommendations concern checkout security and are not TDayPay request fields. Add browser checks, WAF rules, or CAPTCHA only through a separately reviewed security design.
- COP examples also conflict with the common response table: some return only `orderId` and `checkoutUrl`, and `noPayPage=true` can yield an empty `checkoutUrl`. Treat response fields as nullable/optional unless the current merchant contract proves otherwise, and always gate success on the response envelope plus asynchronous status.

### Payout

- `NET_BANKING` is an ACH account payout, not PSE. It requires bank, account, `CHECKING|SAVINGS`, document type/number, and beneficiary name fields.
- `TRANSFIYA` requires a 10-digit local mobile account, activation, identity/account fields, and its channel-specific institution table. Nequi's official retirement of Transfiya in its app makes `NEQUI/507` a `STALE_CHANNEL_CONFLICT`; never auto-switch to Bre-B.
- `BRE_B` pays to a registered key. Use validator-only `--key-type` to distinguish `PHONE`, `EMAIL`, `DOCUMENT`, `ALPHANUMERIC`, or `MERCHANT_CODE`; do not add this metadata to the TDayPay request. The public provider document does not justify requiring bank name or account type for this channel.

## Shared cautions

- Network rules can support format validation and operational context but cannot establish a TDayPay merchant route.
- A higher national-network ceiling does not override a lower provider limit.
- A syntactically valid account, CLABE, phone, identity, or key does not prove existence, ownership, activation, balance, or reachability.
- Revalidate live-critical decisions against the current provider document and merchant-specific contract.
- Never copy personal data from examples into a real request.
