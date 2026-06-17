# wr-premier — Design Spec

> Type: writer
> Component ID: keboola.wr-premier
> Status: draft
> Date: 2026-06-04

## 1. Overview & source system

`keboola.wr-premier` is a **writer** that pushes rows from Keboola Storage tables into the
**PREMIER system** (Czech ERP / accounting / economic software, https://www.premier.cz) via its
**ApiComPrem** API — creating partners, invoices, orders, stock cards, and other documents from
tabular data managed in Keboola.

- **Target system:** PREMIER system, ApiComPrem engine.
- **API docs:** vendor page https://www.premier.cz/produkty/moduly/dalsi-reseni/api/ ; manual
  https://premier-system.atlassian.net/wiki/spaces/PS/pages/8349813/PREMIER+API (Czech, gated) ;
  live contract reverse-engineered from the public test client at
  `https://dev.premier.cz/cmd_test/index.html`.
- **Primary use case:** a Keboola user who keeps master/transactional data (partners, invoices,
  orders, stock) in Keboola and wants to load it into their on-premise PREMIER ENTERPRISE instance
  without manual re-keying.

The API is a **custom JSON-RPC over HTTPS POST** (not REST, not SOAP): every call hits a single
`/api/comm` endpoint with a body naming a command and its parameters. It is **create-oriented**
(22 write commands), per-customer **on-premise**, and uses **HTTP Basic auth + an `ID-UJ` header**
identifying the accounting unit.

## 2. Keboola mapping

How PREMIER maps onto how Keboola runs a writer:

- **Input tables → API writes.** This is a writer: it *reads* one Keboola input-mapping table per
  configuration row and, for each table row, issues one PREMIER **write command** (`*_ADD`/`*_UPD`).
- **Config rows, one row per write target.** PREMIER exposes 22 distinct write commands
  (`PARTNERI_ADD`, `FA_OUT_ADD`, `OB_IN_ADD`, `SKLAD_ADD`, …). Per Keboola convention, multiple
  independent objects → **config rows**, one row per command/target. Each row = "take this input
  table and write it into PREMIER via command X with this column→parameter mapping." Rows can be
  enabled/run/retried independently and run in parallel. *(Override note: a single row is fine for a
  user writing just one object.)*
- **No incremental "load" in the extractor sense.** A writer doesn't produce output tables, so
  output-mapping incremental loading does not apply. What *does* matter is **idempotency**: PREMIER
  write commands are **create-only with no idempotency key**, so re-running a row risks duplicate
  documents. Strategy: persist per-row **`state.json`** tracking which input rows were already
  written successfully (keyed by a user-designated natural key column, e.g. `VARIABL`/document
  number), and skip them on re-run. See §6.
- **Secrets → `#`-prefixed.** The PREMIER user password is `#password` (encrypted). Username, host,
  port, and `ID-UJ` are non-secret.
- **Sync actions:**
  - `testConnection` — validate host reachability + Basic auth + `ID-UJ` by issuing a harmless read
    (e.g. `VERZEAPI` or `INFO`).
  - `listCommands` — call `INFO` (prikaz=FULL), filter to `typ_prikazu == "IN"`, and populate the
    row's "command" dropdown with the live write-command catalog (so the UI never offers a command
    the customer's instance doesn't license).
  - (Optional, later) `listCommandParameters` — given a chosen command, surface its documented
    parameters to assist column mapping.
- **No output bucket.** A writer has no output tables by default. **Exception:** we will write **one
  results table** (`out.c-wr-premier.results` or default-bucket equivalent) recording per-input-row
  write status — see §4/§6 — so the "continue-on-failure" outcome is inspectable in Keboola.

## 3. Authentication & connection

- **Auth: HTTP Basic** over HTTPS — the username + password of a PREMIER user, base64-encoded into
  `Authorization: Basic …`. Chosen because it is the only method the API exposes (no OAuth/token
  flow). Plus the mandatory **`ID-UJ`** header (accounting-unit GUID) selecting which company DB to
  write to.
- **Connection: custom JSON-RPC over HTTPS POST** to `https://<host>:<port>/api/comm`. There is no
  alternative surface; this is the only API.
- **Confirmed request contract** (from the live test client):
  - Method/URL: `POST https://<host>:<port>/api/comm`
  - Headers: `Content-Type: application/json; charset=UTF-8`, `ID-UJ: <guid>`,
    `Authorization: Basic <base64(user:pass)>`
  - Body: `{"command":{"inComm":"<CMD>","inParam":{"parameters":{<k>:<v>, …}}}}`
  - Response: `{"Result":"OK"|"ERR","CommandIn":"<cmd>","Data":[…],"Error":[{number,desc}],"Warning":[…]}`
- **Provisioning (NOT headless on the customer side):** before Keboola can connect, a PREMIER admin
  must, on the customer's own server:
  1. Run PREMIER **ENTERPRISE** (SQL edition; MS SQL 2016+, compat level ≥130) — the API works only
     with this edition.
  2. Install the **ApiComPrem** Windows service (`apicompremservice.exe`); the SQL service account
     needs `sysadmin`.
  3. Run `ApiComPremForm.exe` to bind accounting units and generate the **`ID_UJ`** GUID, and hand
     that GUID to the integrator.
  4. Make the service **network-reachable from Keboola** (public IP, VPN, or reverse proxy) and
     supply host:port.
  Once that's done, the writer authenticates headlessly per run (plain Basic + header).
- **Blockers / access (see §9 for ranking):**
  - **On-premise reachability** is the dominant architectural constraint — there is no central cloud
    endpoint; each customer is a distinct reachable host or the writer cannot connect.
  - **Sandbox:** the public `dev.premier.cz:12375` instance (test unit `ID-UJ
    3ce17312-8dbd-49a0-94d3-2e01b65e4173`) is reachable and serves all read/`INFO` commands without
    even requiring auth. **It is unknown whether it persists writes**, and we will not blind-fire
    creates into it (see §7 + §9). The user has **no real customer credentials yet**.

## 4. Data model & endpoints

- **In scope for v1:** a **generic, command-driven writer** covering **all 22 PREMIER `IN` (write)
  commands**, surfaced via the `listCommands` dropdown rather than hard-coded per object. The user's
  requirement is "write everywhere the API allows," so the design treats the command as data, not as
  bespoke code per object. The 22 write commands (from a live `INFO` FULL dump):

  | Command | Purpose | Command | Purpose |
  |---|---|---|---|
  | `PARTNERI_ADD` | add/edit partner | `FA_ZIN_ADD` | received advance invoice |
  | `PART_ADR_ADD` | partner address | `FA_IN_AUDIT` | mark received invoice audited |
  | `PART_KON_ADD` | partner contact | `FA_ZOUT_ADD` | issued advance invoice |
  | `OB_IN_ADD` | received order | `FA_ZIN_AUDIT` | audit received advance invoice |
  | `OB_OUT_ADD` | issued order | `ZAKAZKA_ADD` | add job/contract |
  | `OB_IN_UPD` | update order | `ZAKAZKA_UPD` | supplement job/contract |
  | `PRIJEMKY_ADD` | goods receipt | `SKLAD_ADD` | warehouse stock card |
  | `VYDEJKY_ADD` | goods issue | `NABIDKY_ADD` | quotation |
  | `VYDEJKY_UPD` | supplement goods issue | `VAZBY_ADD` | document links |
  | `FA_IN_ADD` | received invoice | `FA_IN_UPD` | supplement invoice |
  | `FA_OUT_ADD` | issued invoice | `FA_ZIN_UPD` | supplement advance invoice |

- **No pagination** on writes (each call writes one document/record). **Rate limits: none
  documented** — the writer will issue calls sequentially per row with a small, configurable
  inter-request pause and bounded retry/back-off on transient HTTP/5xx errors.
- **No batch/multi-document call documented** — one input row → one command call (a command may
  carry a line-items array within a single document, e.g. invoice lines, but that's intra-document).
- **Response shape:** flat envelope `{Result, Data, Error, Warning}`. The writer interprets
  `Result=="OK"` as success and `Result=="ERR"` (or HTTP error) as a row failure, capturing
  `Error[].desc` into the results table.
- **Field-level schemas:** `INFO` returns command-level *control* parameters (e.g. `typCmd
  ADD/UPD`); the full column schema for a record lives in the underlying DB table and is fetched via
  `INFO table_name=<real table>`. v1 does **not** hard-validate record fields against the schema —
  the user maps input columns to PREMIER parameter names, and PREMIER's own server-side validation
  is the authority (errors surface per-row).

## 5. Configuration & schema

> Handoff: the actual `configSchema.json` / `configRowSchema.json` is built by `component-build-ui`.
> This section describes the fields only.

**Config-level (shared, entered once):**
- `host` (string, required) — PREMIER server host/IP.
- `port` (integer, required, default e.g. 443) — API port (sandbox uses 12375).
- `use_https` (boolean, default true).
- `username` (string, required) — PREMIER user.
- `#password` (string, secret, required) — PREMIER user password.
- `id_uj` (string, required) — accounting-unit GUID (`ID-UJ` header).
- `request_delay_ms` / `max_retries` (optional, advanced) — pacing/back-off knobs.
- Sync action: **`testConnection`**.

**Row-level (per write target):**
- `command` (string, required) — the PREMIER write command; populated by the **`listCommands`**
  sync-action dropdown (live `IN` commands).
- `column_mapping` (object/array, required) — maps input-table column names → PREMIER parameter
  names (`inParam.parameters` keys). Free-form because parameter sets vary per command; a future
  iteration can drive this from `listCommandParameters`.
- `dedup_key_column` (string, optional) — input column used as the natural key for idempotent
  re-runs (state-tracked). If empty, every run re-sends every row (documented caveat).
- `continue_on_error` (boolean, default true) — per the agreed failure mode; when true, failed rows
  are recorded and the job still succeeds if any row succeeds.

**Input mapping:** exactly one input table per row (the rows-to-write source).

**Sync actions:** `testConnection` (config level), `listCommands` (row level), optional
`listCommandParameters` (row level, later).

## 6. Code architecture

- **`client/premier_client.py` — `PremierClient`** (separate from `component.py`):
  - `__init__(host, port, use_https, username, password, id_uj, delay_ms, max_retries)` — builds the
    base URL and the static headers (incl. `Authorization`, `ID-UJ`).
  - `call(command: str, parameters: dict) -> PremierResponse` — the single POST primitive; wraps the
    `{"command":{"inComm":…,"inParam":{"parameters":…}}}` envelope, parses
    `{Result,Data,Error,Warning}`, applies retry/back-off on transient errors.
  - `test_connection()` — issues `VERZEAPI`/`INFO`; raises on failure.
  - `list_write_commands()` — `INFO` FULL → filter `typ_prikazu=="IN"` → list of command names.
  - `write(command, parameters)` — thin wrapper over `call` returning success/`Error[].desc`.
- **`configuration.py`** — Pydantic models: one config-level model (connection/auth), one row-level
  model (command, mapping, dedup, continue_on_error). Validated early; missing/invalid config →
  `UserException`.
- **`component.py` — `run()` is a thin orchestrator:**
  1. Parse + validate config (Pydantic).
  2. Build `PremierClient`.
  3. Read the input table (csv) for the row.
  4. Load `state.json` (set of already-written dedup keys).
  5. For each input row: build `parameters` via `column_mapping`; skip if dedup key already in
     state; else `client.write(...)`; record outcome.
  6. Write the **results table** (input identifier, status OK/ERR, error message) and update
     `state.json` with newly-succeeded keys.
  7. If `continue_on_error` is false and any row failed → `UserException`.
- **Sync actions** (`@sync_action`): `testConnection`, `listCommands`, (later) `listCommandParameters`.
- **Error handling:**
  - `UserException` (exit 1): bad/missing config, auth failure (401), host unreachable, `ID-UJ`
    rejected, all rows failed, or any failure when `continue_on_error=false`.
  - Unexpected (exit 2): programming errors, unhandled exceptions.
- **Dependencies:** `keboola.component` (CommonInterface), `requests` (HTTP), `pydantic` (config
  models), `tenacity` (retry/back-off) — all standard CF choices.

## 7. Testing

- **Datadir tests:**
  - Happy path — one input row → one mocked `Result=OK` → results table shows OK, exit 0.
  - Partial failure — two rows, one `Result=ERR`; `continue_on_error=true` → results table has
    OK+ERR, exit 0; with `continue_on_error=false` → exit 1.
  - Dedup — row whose key is already in `state.json` is skipped (no call issued).
  - Config validation — missing `#password`/`id_uj` → `UserException` exit 1.
  - Auth failure — mocked 401 → `UserException` exit 1.
- **VCR strategy:**
  - **Read-side cassettes are recordable now** against `dev.premier.cz:12375` (no auth needed):
    `VERZEAPI`, `INFO` FULL — these seed `testConnection` and `listCommands` tests. (An `INFO` FULL
    response — 63 commands — is already captured at `/tmp/info_noauth.json` during research and can
    seed a cassette.)
  - **Write-side cassettes:** we will **not** blind-fire creates at the sandbox. Two options,
    decided at implementation time: (a) get explicit authorization to send **one** controlled
    `*_ADD` to `dev.premier.cz` and record it, or (b) hand-author the write cassette from the
    documented `{Result:OK}` envelope until a real instance is available. Default to (b) to avoid
    polluting the shared sandbox; upgrade to a real recording once customer creds exist.
  - **Sanitizers:** `VCR_SANITIZERS` must scrub the `Authorization` header and the `username`/
    `#password`/`id_uj` values from request bodies/headers in all cassettes.
- **Sync action tests:** `testConnection` (OK + failure), `listCommands` (returns the 22 IN
  commands from the recorded `INFO`).

## 8. Deployment & validation (CF test project)

- Image for the `initial-implementation` branch is built by `push.yml` on push (Phase 1 already
  proved the pipeline is green).
- Via **kbagent**, create a config in the **cf-dev** project with the image tag **overridden** to
  the branch build, pointed at `dev.premier.cz:12375` + the public test `ID-UJ`, using a
  **read-only** validation path first (`testConnection` + `listCommands`) so the smoke test doesn't
  depend on writes succeeding.
- A successful end-to-end run = job `success`, `testConnection` passes, `listCommands` returns the
  write catalog, and the results table is produced. Confirm the **resolved image tag** matches the
  branch build (not a stale `0.0.1`). A write-path smoke test is gated on having a writable target.

## 9. Open risks & blockers

1. **On-premise reachability (architectural, high).** No cloud endpoint; every real customer needs a
   network-reachable host. Keboola→customer connectivity (public IP/VPN/reverse proxy) is a
   per-customer prerequisite outside the component's control. *Owner: customer/solution eng.*
2. **No writable sandbox confirmed (testing, high).** `dev.premier.cz` serves reads freely but we
   have not confirmed it persists writes, and we won't blind-write to it. Write-path cassettes and
   the write smoke test are therefore blocked on either authorized single-write sandbox testing or
   real customer creds. *Owner: user to provide creds / authorize a controlled sandbox write.*
3. **Create-only + no idempotency (correctness, high).** Re-runs can duplicate documents. Mitigated
   by `state.json` dedup keyed on a user-chosen natural-key column — but if the user leaves
   `dedup_key_column` empty, duplicates are possible. Must be surfaced clearly in the UI/docs.
4. **Per-command parameter schemas not statically known (scope, medium).** v1 relies on free-form
   column→parameter mapping + PREMIER server-side validation rather than enforcing field schemas.
   Acceptable for v1; a later iteration can drive validation from `INFO table_name=…`.
5. **Enterprise-SQL-only + licensed API module (access, medium).** The API needs PREMIER ENTERPRISE
   (SQL) and the API module may be a paid add-on; non-Enterprise customers cannot use the writer.
   Documentation must state this precondition. *Owner: customer.*
6. **Czech field names + evolving API (maintainability, low).** Parameters are Czech abbreviations
   and the API evolves; the manual is "informational only," so `INFO` (live) is the source of truth —
   which is exactly why `listCommands` is driven off `INFO` rather than a hard-coded list.
