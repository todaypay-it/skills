# Reconciliation data contract

## Required inputs

- One user-system order-list file in UTF-8 CSV, XLSX, or XLSM format.
- Currency plus inclusive `start-date` and `end-date`.
- One or more extracted TDayPay merchant-order CSV files covering every business date for the requested currency.
- One or more extracted TDayPay accounting-flow CSV files covering the order start date through the order end date plus three calendar days for the requested currency. When the target flow end date is in the future, cover through the current business date and label the observation window incomplete.

The system file may contain extra columns. The first worksheet is used for Excel unless `--sheet` is supplied.

## Required columns

System orders require:

- `平台订单号`
- `商户订单号`
- `订单金额`
- `币种`
- `订单状态`
- `创建日期`

`支付类型` is strongly recommended and is checked when present. TDayPay order exports additionally require `结算状态`. Flow exports require `流水ID`, `订单号`, `资金域`, `账户类型`, and `创建时间`.

Supported English aliases include `platformOrderNo`, `merchantOrderNo`, `amount`, `currency`, `status`, `createDate`, `orderType`, `settlementStatus`, `flowId`, `orderNo`, `fundingDomain`, and `amountType`.

## Normalization

- Strip surrounding whitespace, a UTF-8 BOM, and a leading text apostrophe used by Excel exports.
- Preserve identifiers as strings. Never parse platform order numbers, merchant order numbers, flow IDs, account IDs, or merchant IDs as numbers.
- Normalize dates to `YYYYMMDD` for comparisons while retaining the original exported text in detail rows.
- Parse monetary values with decimal arithmetic after removing grouping commas. Do not use binary floating point for equality or totals.
- Normalize `PAYIN` and `PAYMENT` to `PAYMENT`; normalize `PAYOUT` to `PAYOUT`.
- Use exact uppercase comparisons for `SUCCESS`, `CHECKED`, `UNCHECK`, `UNPAYOUT_AMT`, and `ORDER_AMT` after trimming.

## Population rules

1. Filter the system file to the requested currency, inclusive creation-date range, and `订单状态 == SUCCESS`.
2. Filter TDayPay orders by the same currency, inclusive creation-date range, and success status.
3. Include both `PAYMENT` and `PAYOUT` unless the user explicitly narrows order type.
4. List excluded source rows and reasons in the reconciliation JSON. A file with no in-scope rows is a validation failure.
5. Require unique nonblank platform order numbers in each success population. Duplicate keys are a validation failure.

## Order reconciliation

Join by the complete normalized `平台订单号` with exact string equality.

- System only: present in the system success population and absent from TDayPay success orders.
- TDayPay only: present in TDayPay success orders and absent from the system success population.
- Matched: present in both. Check merchant order number, amount, currency, and normalized payment type.
- Confirmed unsettled: TDayPay success order with `结算状态 == UNCHECK`.
- Settlement status unknown: `结算状态` is blank or is neither `CHECKED` nor `UNCHECK`. Keep these rows on a separate sheet in the unsettled workbook and do not count them as confirmed unsettled.

Record counts and decimal totals for each relevant population. Filter to the user-supplied currency and never combine monetary totals across currencies.

## Accounting-flow reconciliation

For the default scope, locally retain only rows with `资金域 == UNPAYOUT_AMT` and `账户类型 == ORDER_AMT`. Join `订单号` to the full TDayPay `平台订单号`.

- A success order is covered when at least one retained flow has the exact order number and a `创建时间` date from the order's `创建日期` through three calendar days later, inclusive.
- More than one flow per order is valid and all matching rows are exported.
- A missing-flow order has no in-window retained flow and its full three-day observation window has ended.
- If the flow export currently ends before `订单创建日期 + 3 days`, keep an uncovered order in `观察期未结束`; do not report it as missing.
- If a retained flow has the exact order number but its creation date lies outside the order-specific window, export it as out-of-window evidence and do not treat it as coverage.
- Export both all retained flow rows and the subset linked to in-period TDayPay success orders.

## Output contract

Use filenames containing currency and inclusive period. Every populated workbook cell must be a string with text number format. Use an explicit text marker for date/time-looking values and long numeric identifiers when the workbook engine would otherwise coerce them. Verify with the saved XLSX package, not only with the in-memory workbook.

Every workbook states:

- currency and included order types;
- inclusive business dates and business time zone;
- query completion time;
- whether the last date is complete or a current-day snapshot;
- matching key and success filter;
- accounting-flow enum scope;
- target and actual accounting-flow dates, plus whether every order has a complete three-day observation window;
- source file name and TDayPay export job IDs where applicable.
