# TDayPay MCP workflow

## Resolve business time

1. Call `mc_list_supported_currencies` and match the exact currency supplied by the user. Confirm the in-scope file rows use that currency.
2. Use its returned `businessTimeZone` for all order-day boundaries. Do not hardcode a UTC offset because daylight-saving rules can change it.
3. Reject an unsupported currency. Reject an end date later than the current date in that currency's business time zone.
4. Record the query-completion time in UTC, the currency business time zone, and the user's local time zone when available.
5. If the end date equals the current business date, mark that date as a partial snapshot. Earlier dates are complete.

## Export merchant orders

`mc_export_merchant_orders` accepts exactly one currency-local calendar day per job. For every inclusive business date:

1. Compute local midnight at the start of the date and local midnight at the start of the next date.
2. Send those offset-aware ISO-8601 instants as inclusive `startTime` and exclusive `endTime`, with the currency.
3. Poll `mc_get_order_export_status` until `COMPLETED` or `FAILED`. Use bounded waits and keep the user updated during long runs.
4. On `COMPLETED`, immediately download the one-time `downloadUrl` into the run directory. Record the export ID, status, exported row count, completion time, and business date in a JSON sidecar.
5. Extract the downloaded archive when necessary and retain every CSV as evidence.

Do not replace a failed or missing export with a list query and then claim complete reconciliation. A bounded list query may diagnose a problem, but the final result must identify the missing export as incomplete.

## Export accounting flows

The default user terms map to the actual TDayPay enums as follows:

| User wording | TDayPay/export value |
| --- | --- |
| `UNPAYOUT_AMOUNT` | `UNPAYOUT_AMT` |
| `ORDER_AMOUNT` | `ORDER_AMT` |

For an order period `[orderStart, orderEnd]`, set the target accounting-flow period to `[orderStart, orderEnd + 3 calendar days]`. This gives every order a search window from its own creation date through creation date plus three days, inclusive. If the target end date is later than today in the currency business time zone, export only through today and mark the observation window incomplete. Do not call an unfinished observation window a missing flow.

`mc_export_merchant_account_flows` uses inclusive date-only `startDate` and `endDate`, permits at most seven calendar dates per job, and does not perform order-time-zone conversion.

1. Split the actual inclusive flow period into consecutive chunks of at most seven dates.
2. Export each chunk with `currency`, `orderStatus: "SUCCESS"`, and `amountType: "ORDER_AMT"` unless the user chose a different scope.
3. Poll `mc_get_account_flow_export_status` until `COMPLETED` or `FAILED`.
4. Download each completed one-time URL immediately and record the job metadata.
5. Post-filter exported CSV rows to both `资金域 == UNPAYOUT_AMT` and `账户类型 == ORDER_AMT`. The export API cannot express the funding-domain predicate by itself.
6. Merge chunks and deduplicate by `流水ID`. A repeated identical row is one row; a repeated ID with conflicting content is a validation failure.
7. After matching the full platform order number, retain a linked flow as coverage only when its `创建时间` date is between that order's `创建日期` and `创建日期 + 3 days`, inclusive. Keep order-number matches outside that window as out-of-window evidence.

## Evidence and failure handling

- Compare the export's reported row count with the downloaded CSV before applying local status/date/scope filters.
- Keep order and flow job metadata in JSON files beside the extracted CSVs so the reconciliation JSON can cite the jobs.
- Stop on `FAILED`, expired one-time downloads, truncated files, missing headers, conflicting duplicate IDs, or a mismatch between reported and downloaded raw row counts. Report the precise affected date or chunk.
- Do not put download URLs, tokens, cookies, authorization headers, phone numbers, email addresses, payout accounts, or user identity payloads into summary prose. Requested raw exports may contain the merchant's source fields inside the delivered workbooks.
