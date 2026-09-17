# Transaction fields and validation

Use these as generic cross-country rules. Country and channel supplements can add required fields or stricter formats.

## Payment (`method=pay`)

Required body fields:

| Field | Rule |
|---|---|
| `mchOrderId` | Merchant order ID, 5–32 characters. Must be unique in the merchant system. |
| `amount` | Positive decimal amount; country/channel rules determine scale and limits. |
| `currency` | Three-letter currency code. |
| `productinfo` | Product description, 1–100 characters. |
| `firstname` | Payer given name. Some countries require real identity data. |
| `lastname` | Payer family name. Some countries require real identity data. |
| `email` | Syntactically valid payer email. Some channels send verification here. |
| `phone` | 6–20 characters in the common contract; country-specific format may be stricter. |

Optional common fields:

- `callbackUrl`: transaction webhook URL.
- `redirectUrl`: browser redirect after success or failure.
- `noPayPage`: set to string/boolean form accepted by the merchant integration only after confirming desired checkout behavior.
- `paymentType`: country/channel selector.

The create response may contain `orderId`, `currency`, `type`, and `checkoutUrl`. `type=1` indicates status is shown and a link may be sent by SMS; `type=2` indicates the checkout URL is the payment link.

## Payout (`method=payOut`)

Required common body fields:

| Field | Rule |
|---|---|
| `mchOrderId` | Unique merchant order ID. |
| `amount` | Positive decimal amount; country/channel rules determine scale and limits. |
| `currency` | Three-letter currency code. |
| `purpose` | Payout purpose or description. |
| `beneficiaryName` | Beneficiary name; country/channel may require the legal name. |
| `beneficiaryEmail` | Valid email format. |
| `beneficiaryMobile` | Valid phone format for the selected country/channel. |
| `beneficiaryAccountNumber` | Bank, wallet, phone, virtual account, or channel-specific identifier. |

Optional in the common contract but frequently required by a channel:

- `paymentType`
- `beneficiaryBankCode` or `beneficiaryBankName`
- `beneficiaryAccountType`
- `docType` and `docNumber`
- `callbackUrl`

The synchronous create response normally supplies `orderId`; it does not prove funds reached the beneficiary.

## Balance (`method=balance`)

Body:

```json
{"currency":"BRL"}
```

The documentation marks `currency` optional with INR as a default, but provide it explicitly to prevent cross-currency ambiguity. The response data includes `currency` and `balance`.

## Order query (`method=verifyStatus`)

Body:

```json
{"orderId":"platformOrderId1,platformOrderId2"}
```

- `orderId` uses TDayPay platform order IDs, not merchant order IDs.
- Separate multiple IDs with an ASCII comma.
- Maximum 200 IDs per request.
- `queryType` is documented as conditionally required for a Mexico F-order mode.

Response items can include `orderId`, `mchOrderId`, `orderStatus`, `orderType`, `createTime`, `notifyTime`, `failMessage`, `bankId`, `amount`, and `realAmount`.

## Known Colombia supplement

Use only when the request is for COP and re-check current documentation before live execution:

- The documentation states that collection and payout amounts do not support decimals and generally range from 5,000 to 3,000,000 COP, although examples conflict with that minimum.
- Collection requires `paymentType`, `beneficiaryType`, `beneficiaryId`, `ipAddress`, and `productUrl`; identity and contact details must be real.
- Collection uses the common lowercase `firstname` and `lastname`. `paymentMethod` is optional and must be `API` only when supplied.
- `beneficiaryType=CC` requires a 6-10 digit `beneficiaryId`; `beneficiaryType=NIT` requires exactly 9 digits.
- `NET_BANKING` requires a numeric `bankCode` from the provider table; saved examples that omit it or use `ITAU` conflict with the table (`ITAU=006`).
- A Colombian phone without `+57` is documented as 10 digits.
- Collection channels listed include `NET_BANKING`, `BRE_B`, and `NEQUI`.
- Payout channels listed include `NET_BANKING`, `TRANSFIYA`, and `BRE_B`.
- `TRANSFIYA` uses a mobile number as the beneficiary account and requires user activation.
- Bank payout can require bank name/code, account type, and identity fields.

Because the public examples are inconsistent, a live COP request that relies on a boundary amount or ambiguous channel field must be confirmed against the current contract.

COP saved responses can omit fields that the common response table marks required, and `noPayPage=true` can produce an empty `checkoutUrl`. Parse `orderId`, `currency`, `type`, and `checkoutUrl` defensively; do not equate a populated checkout URL or synchronous acceptance with final payment success.
