# Official payment-network rules

Verified: 2026-09-10.

These facts explain the payment scheme behind a TDayPay channel. They do not prove that TDayPay or a particular merchant has enabled the channel, institution, identifier, amount, or SLA. Provider/API rules take precedence when they are stricter.

## Mexico: SPEI

Official sources:

- [Banco de México: Mi SPEI](https://www.banxico.org.mx/servicios/mi-spei_-transferencias-ban.html)
- [Banco de México: compiled Circular 14/2017](https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-14-2017/%7BA06FBFEE-06BB-F249-32FC-25B334B2A744%7D.pdf)
- [Banco de México: CLABE check-digit algorithm, Circular 12/2018 Annex 4](https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-12-2018/%7BA6023AE0-8135-44ED-04DA-2068117ED5FD%7D.pdf)

Rules and safe implications:

- SPEI is a domestic MXN inter-institution transfer system.
- The network can identify a beneficiary with an 18-digit CLABE, an eligible 16-digit card, or a linked 10-digit mobile number. TDayPay's payout `SPEI` rule is narrower and requires CLABE; do not accept card or phone in that provider channel.
- CLABE has 18 digits: three bank digits, three plaza/region digits, eleven account digits, and one check digit. The official checksum uses repeating weights 3, 7, 1 over the first 17 digits. A checksum pass proves structure only.
- 1,500 UDIS is a low-value category threshold, not a universal maximum.
- Availability and timing vary by amount, participant, and request type. Do not promise that every TDayPay SPEI transaction is instant and 24/7.
- `Liquidado` means the network settled and informed the receiver; CEP or Confirmación de Abono is stronger evidence that the beneficiary was credited.

## Colombia: PSE

Official sources:

- [PSE help center](https://www.pse.com.co/es/persona-centro-de-ayuda)
- [PSE first-payment guidance](https://www.pse.com.co/es/persona-tu-primer-pago-por-pse)

Rules and safe implications:

- PSE is an online purchase/payment flow funded from a savings account, checking account, or electronic deposit; it is not a payout rail.
- A payer registers identity and contact information with PSE. The flow redirects to the selected financial institution for authentication and debit authorization.
- The payer's institution decides the permitted amount. This does not replace TDayPay's merchant- or route-specific limits.
- In this Skill, `PSE -> NET_BANKING` is an action-scoped TDayPay alias for COP payment only.

## Colombia: direct Nequi payment

Official source:

- [Nequi: paying with Botón Nequi](https://ayuda.nequi.com.co/hc/es/articles/35336140345101--C%C3%B3mo-pagar-con-el-Bot%C3%B3n-Nequi)

Rules and safe implications:

- The payer needs an eligible Nequi account, sufficient funds, and must approve the pending payment in the Nequi app.
- The merchant must support Botón Nequi. That general statement does not prove a specific TDayPay `mchId` has direct `NEQUI` enabled.
- Direct `NEQUI`, PSE via `NET_BANKING`, and Transfiya are separate flows. Do not inject `bankCode=507` or rewrite between them.

## Colombia: Transfiya

Official sources:

- [ACH Colombia: Transfiya low-value payment-system rules, version 2, August 2025](https://www.achcolombia.com.co/documents/1176249/0/Reglamento_del_Sistema_de_Pago_de_Bajo_Valor_ACH_Transfiya.pdf/8b99ec26-7784-5e59-0457-fe053100c057?t=1755791532417)
- [Nequi: Transfiya retirement in the Nequi app](https://ayuda.nequi.com.co/hc/es/articles/34016029816717--Hasta-cu%C3%A1ndo-puedo-enviar-y-recibir-por-Transfiya)

Rules and safe implications:

- ACH Colombia's 2025 rules describe a 24/7/365 immediate low-value system, a 20-second objective for at least 99.5% of orders, and a 1,000 UVB network ceiling. Participating institutions can set lower limits.
- TDayPay's public `TRANSFIYA` payout remains mobile-specific. Do not expand it to non-phone Bre-B keys merely because the wider network is interoperable.
- Nequi states that Transfiya send/receive in its app ended on 2025-10-05. Therefore a TDayPay Transfiya payout naming Nequi or code `507` needs current written provider/merchant confirmation.
- The Nequi conflict does not prove every Transfiya route is unavailable. It also does not authorize an automatic switch to `BRE_B`.

## Colombia: Bre-B

Official source:

- [Banco de la República: Bre-B FAQ](https://www.banrep.gov.co/es/bre-b/preguntas-frecuentes)

Rules and safe implications:

- Bre-B is a domestic immediate-payment service available through participating institutions 24/7/365; it is not a standalone app.
- A receiver registers a key tied to an eligible account or deposit. A sender needs the receiver key or scans a QR and does not need a sender key.
- Key types are national mobile number, registered identity number, registered email, an institution-generated identifier beginning with `@`, and merchant code for a business.
- Before confirmation, the sending channel shows a masked recipient name. This is an operational safety step, not a TDayPay request field.
- The official 2026 network ceiling is 1,000 UVB, displayed as 12,110,000 COP; an institution may impose lower value or count limits. TDayPay's public 3,000,000 COP ceiling is lower and remains the conservative provider rule.

## Evidence boundary checklist

Before turning any fact into a hard validator, confirm:

1. Does the source belong to TDayPay or to the national network?
2. Does it apply to `payment`, `payout`, or only the network in general?
3. Does it apply to the exact TDayPay `paymentType`?
4. Is the field documented in the TDayPay request, or is it validator-only context?
5. Is there a contradictory public example or an institution-specific retirement?
6. Does a current merchant contract override or narrow the public rule?
