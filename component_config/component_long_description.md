# PREMIER Writer

Loads tabular data from Keboola Storage into the **PREMIER system** ([premier.cz](https://www.premier.cz)) — a Czech ERP/accounting platform — through its **ApiComPrem** JSON-RPC API.

The writer is **command-driven**: each configuration row maps one input table to one PREMIER write command (e.g. `PARTNERI_ADD`, `FA_OUT_ADD`, `SKLAD_ADD`). For every row of the input table the component issues one `POST /api/comm` call, mapping the table's columns to the command's PREMIER parameters. The list of available write commands is loaded live from the API.

## Features

- One configuration row = one input table → one PREMIER write command.
- Column-to-parameter mapping configured per row.
- Optional deduplication: a chosen key column lets re-runs skip already-written rows.
- Per-row results table (`OK` / `ERR` / `SKIPPED`) for inspecting outcomes.
- Continue-on-error or fail-fast behaviour.
- Connection test and live command list available as configuration-time actions.

## Requirements

- PREMIER **ENTERPRISE (SQL)** edition with the API module enabled.
- The PREMIER API server must be network-reachable from Keboola (PREMIER is deployed on-premise per customer — there is no central cloud endpoint).
- A PREMIER user, password, and the accounting-unit identifier (`ID-UJ`), provisioned by a PREMIER administrator.
