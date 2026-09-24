# HHGOA column maps for GraphStudio Load Data wizard (header OFF, separator ",")
# Column numbers are 1-based positions in the .noheader.csv files.

## transactions_graph.noheader.csv (20 cols, ~590k rows)
| # | Column | Target |
|---|--------|--------|
| 1 | TransactionID | Txn.id |
| 3 | TransactionAmt | Txn.amt |
| 18 | ts | Txn.ts |
| 19 | channel | Txn.channel |
| 4 | ProductCD | Txn.product |
| 11 | addr1 | Txn.region |
| 20 | risk_score | Txn.risk_score |
| 17 | customer_id | Card.id, Card.customer_id |
| 17 | customer_id | Customer.id (risk_note blank) |
| 11 | addr1 | BillingRegion.id |
| 17 -> 1 | | OWNS? no — skip; use MADE (17 -> 1) |
| 17 -> 1 | | MADE edge (Card -> Txn) |
| 1 -> 11 | | BILLED_IN edge (Txn -> BillingRegion) |
| 17 -> 17 | | OWNS edge (Customer -> Card) |

## identity.noheader.csv (41 cols, ~144k rows)
| # | Column | Target |
|---|--------|--------|
| 41 | DeviceInfo | DeviceProfile.id |
| 41 | DeviceInfo | DeviceProfile.info |
| 31 | id_30 (OS) | DeviceProfile.os |
| 32 | id_31 (browser) | DeviceProfile.browser |
| 34 | id_33 (screen) | DeviceProfile.screen |
| 1 -> 41 | | FROM_DEVICE edge (Txn -> DeviceProfile) |

## closed_cases_history.noheader.csv (15 cols) — DONE
Loaded 2026-09-24: 2324 lines, 0 errors. ClosedCase/Card/Customer + OWNS/ON_CARD edges live.
