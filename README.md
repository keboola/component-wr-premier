# wr-premier

`wr-premier` is a Keboola **writer** that loads rows from Keboola Storage tables into the
**PREMIER system** ([PREMIER](https://www.premier.cz), a Czech ERP/accounting software) via its
ApiComPrem JSON-RPC API. Each Keboola table row becomes one PREMIER create/write command call.

## How it works

The component uses **config rows** — one row = one input table → one PREMIER write command. Each
row reads exactly one mapped input table, and for every CSV row it issues one `POST /api/comm` call
to PREMIER, with the row's columns mapped to PREMIER parameters.

## Configuration

### Connection (config level)

| Parameter     | Description                                                                  |
|---------------|------------------------------------------------------------------------------|
| `host`        | PREMIER server host/IP.                                                       |
| `port`        | API port (e.g. `443`; the sandbox uses `12375`).                             |
| `use_https`   | Use HTTPS. Default `true`.                                                    |
| `username`    | PREMIER user.                                                                |
| `#password`   | PREMIER user password (encrypted).                                           |
| `id_uj`       | Accounting-unit GUID, sent as the `ID-UJ` header.                            |
| `max_retries` | Optional. Number of API retries. Default `5`.                               |

### Write target (row level)

| Parameter           | Description                                                                                              |
|---------------------|----------------------------------------------------------------------------------------------------------|
| `command`           | The PREMIER write command (e.g. `FA_OUT_ADD`). Chosen from a dropdown populated live from the API `INFO` command. |
| `column_mapping`    | List of `{source, target}` pairs mapping an input column → a PREMIER parameter name.                     |
| `dedup_key_column`  | Optional. An input column used as a natural key for idempotent re-runs.                                  |
| `continue_on_error` | Continue writing remaining rows after a failure. Default `true`.                                        |

## Sync actions

- **testConnection** — validates host + Basic auth + `ID-UJ`.
- **listCommands** — lists the available PREMIER write commands.

## Idempotency and deduplication

PREMIER write commands are **create-only with no idempotency key**, so re-running could create
duplicate documents. If `dedup_key_column` is set, the component records each successfully-written
key in `state.json` and skips those rows on subsequent runs. **If `dedup_key_column` is left empty,
every run re-sends every row — risking duplicates.** Written keys are persisted on every exit path,
including partial failures.

## Results table

The component outputs a `results` table with the columns `row_index`, `dedup_key`, `status`,
`message`, where `status` is `OK` / `ERR` / `SKIPPED`, so write outcomes are inspectable in Keboola.

- With `continue_on_error=true`, failed rows are recorded and the job still succeeds as long as at
  least one row succeeds (the job fails only if all rows fail).
- With `continue_on_error=false`, the job aborts on the first failed row (after persisting progress).

## Preconditions and limitations

- PREMIER is typically deployed **on-premise per customer** — there is no central cloud endpoint, so
  the PREMIER API server must be **network-reachable from Keboola** (public IP / VPN / reverse proxy),
  and `host`/`port` are configured per customer.
- The API requires the **PREMIER ENTERPRISE (SQL) edition** with the API module enabled by a PREMIER
  admin (who also generates the `ID-UJ`).
- PREMIER field/parameter names are Czech abbreviations (e.g. `DOKLAD`, `VARIABL`, `KOD_DPH`).

## Development

Run the tests with `uv run pytest`. Lint with `uv run ruff check src tests`.
