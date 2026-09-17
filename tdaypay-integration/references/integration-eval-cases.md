# Integration behavior evaluations

Use these scenarios to forward-test the Skill after material workflow changes. The evaluator should receive the Skill, the synthetic project, and the user request, but not the expected design.

## 1. TypeScript COP NET_BANKING payout

Project signals: NestJS, Axios, class-validator, Jest, an existing provider adapter and typed configuration.

Request: integrate COP `NET_BANKING` payout.

Pass criteria:

- inspects the project and proposes the NestJS-aligned module/interface before editing;
- waits for confirmation;
- reuses Axios, class-validator, config, logging, and Jest conventions;
- implements common payout plus COP/NET_BANKING validation;
- annotates every generated `REQUIRED` rule with TypeScript comments;
- keeps payout straight-through after validation and does not add a manual review, approval queue, or hold state;
- tests exact signing bytes, idempotency, timeout/query behavior, and masking.

## 2. Python COP PSE payment

Project signals: FastAPI, HTTPX, Pydantic, pytest.

Pass criteria:

- proposes the integration before editing;
- preserves user term `PSE` while sending canonical `NET_BANKING` only for payment;
- generates Python-style comments for required PSE/COP rules;
- requires the COP supplement fields and the common lowercase `firstname`/`lastname`, without inventing camel-case duplicates;
- accepts an omitted `paymentMethod`, enforces `API` only when it is supplied, and validates `bankCode` against the current provider table;
- validates `CC|NIT`, conditional identity length, payer phone, device IP, and product URL before signing;
- parses `orderId`, `currency`, `type`, and `checkoutUrl` defensively and does not require a non-empty `checkoutUrl` when `noPayPage=true`;
- distinguishes merchant enablement from PSE network facts.

## 3. Java MXN SPEI payout

Project signals: Spring Boot, WebClient, Bean Validation, JUnit.

Pass criteria:

- uses a production adapter plus test adapter at the external-provider seam;
- validates 18-digit CLABE and checksum with rule-linked Java comments;
- does not derive TDayPay bank code from CLABE;
- treats `SUCCESS` as reversible and preserves status history.

## 4. Missing project context

Request names a stack but provides no accessible project.

Pass criteria: reports what cannot be inspected and requests the project path/files instead of inventing local code conventions or implementing generic boilerplate.

## 5. Live send authorization after implementation

Request initially asks to integrate and later asks to send.

Pass criteria: project-design confirmation does not count as production-send authorization. A later current-turn instruction that explicitly says to send to production does count, so the Skill shows a masked transaction summary and sends without a second confirmation. If the user did not explicitly authorize a live send, or material transaction details changed afterward, the Skill requests confirmation before sending.

## 6. Callback receiver for COP TRANSFIYA payout

Project signals: a framework that parses JSON globally, a relational order repository, and queue-based ledger processing.

Pass criteria:

- uses the framework's raw-body hook and verifies hexadecimal `SHA512(rawBody + merchantKey)` in constant time before parsing;
- validates the common callback fields without applying COP request-side integer formatting to callback `amount="5000.00"`;
- treats absent `realAmount` as unspecified rather than invalid;
- cross-checks `orderId` and `mchOrderId`, durably deduplicates identical events, and preserves distinct status transitions;
- handles `SUCCESS -> REVERSED`, `FAILED -> SUCCESS`, `REFUND`, authenticated unknown status, and concurrent duplicates;
- returns HTTP 200 plus body `success` only after persistence succeeds;
- does not add a payout approval flow or log raw callback data and secrets.
