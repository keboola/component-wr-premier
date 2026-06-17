# PREMIER Writer

Loads Keboola Storage tables into the **PREMIER system** (Czech ERP, [premier.cz](https://www.premier.cz)) via its ApiComPrem API. One config row = one input table → one PREMIER write command (e.g. `FA_OUT_ADD`, `PARTNERI_ADD`).

- Per-row column → PREMIER parameter mapping.
- Optional dedup key skips already-written rows on re-runs.
- Results table with per-row `OK` / `ERR` / `SKIPPED`.

**Requires** PREMIER ENTERPRISE (SQL) with the API module, reachable from Keboola.
