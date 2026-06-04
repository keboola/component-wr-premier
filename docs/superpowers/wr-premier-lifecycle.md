# keboola.wr-premier — New Component Build Lifecycle

> **For agents (read this first):** This file is the **durable, cross-session source of truth** for
> building this new component. `TodoWrite` resets every session; this file does not. Whenever you
> start work on this component — in any skill, in any session — open this file, find the phase you
> own, and act on it.
>
> **The loop for every phase:**
> 1. Read this file; find your phase and the phase(s) before it. Earlier phases are dependencies —
>    if one isn't ticked, resolve it (or surface the blocker) before starting yours.
> 2. Do the phase's work.
> 3. Dispatch the **phase verifier** (see *Verification contract* below) as a fresh subagent.
> 4. **Only tick `- [x]` when the verifier returns ✅ with real evidence** — never on your own
>    say-so. Paste the evidence line under the phase.
> 5. Commit this file (`git add` + commit) so the next session sees the new state.
>
> Mirror the still-open phases into `TodoWrite` for the live in-session checklist, but treat *this
> file* as authoritative.

**Component:** `keboola.wr-premier`  ·  **Type:** `writer`
**Created:** `2026-06-04`
**Spec:** `docs/superpowers/specs/2026-06-04-wr-premier-design.md`
**Plan:** `docs/superpowers/plans/2026-06-04-wr-premier.md` (created in Phase 3)

---

## Verification contract

A phase is "done" only when it's confirmed against **real evidence** by a check that is independent of
the work itself.

**Preferred — dispatch a fresh subagent** (the `Task`/`Agent` tool) so the verifier has a clean context
and no implementer bias. **If subagent dispatch isn't available to you**, run the verification yourself
as a *separate, deliberate pass*: re-derive every piece of evidence from scratch (run the commands,
read the files, query the platform) and do **not** lean on your own earlier claims about what you did.
Either way, give the verifier the phase's **Definition of done** and this instruction:

> Verify ONLY whether this phase is genuinely complete, by gathering **real evidence** — run the
> commands, read the actual files, query the platform/portal/git as needed. Do **not** fix or change
> anything; you are a checker, not an implementer. Return either:
> - `✅ DONE` followed by the concrete evidence you observed (command output, file paths, job IDs,
>   tag names — the specifics), or
> - `❌ NOT DONE` followed by exactly what is missing or failing.
>
> If you cannot confirm a requirement with evidence, default to `❌ NOT DONE`. "Should be fine" is not
> evidence.

If the verifier returns ❌, the box stays unticked — fix the gap and re-verify. This mirrors the
superpowers principle: *evidence before assertions, always.*

---

## Phases

Later phases generally depend on earlier ones, so work top-down. Where two adjacent phases are
genuinely independent (Phase 6 portal value-setup and Phase 7 cf-dev smoke-test don't depend on each
other — both only need Phases 1–5), either order is fine.

### Phase 1 — Scaffold + bootstrap release · owner: `component-get-started` (verified here by `component-plan-new`)
- [x] complete

**Definition of done:**
- Repo pushed to `origin` under the correct org; initial commit on `main`.
- Per-repo portal creds set for the **target vendor**: `KBC_DEVELOPERPORTAL_USERNAME` (variable) +
  `KBC_DEVELOPERPORTAL_PASSWORD` (secret).
- Dev Portal **app created** (via `kbagent dev-portal create`) — the release pipeline needs a target.
- `0.0.1` tag exists and its `push.yml` run **built and pushed the image** (run is green).

> Note: `get-started` runs *before* this tracker exists. `component-plan-new` creates this file and
> runs the Phase 1 verifier retroactively to confirm the scaffold actually landed before planning.

**Evidence:** Verified 2026-06-04 by fresh subagent.
- Repo: `origin → https://github.com/keboola/component-wr-premier.git`, branch `main`, commit `eab4361 initial cookiecutter-template-based commit`.
- Creds: `KBC_DEVELOPERPORTAL_USERNAME=keboola+ComponentFactory_CI` (variable), `KBC_DEVELOPERPORTAL_PASSWORD` (secret) both set.
- Dev Portal app `keboola.wr-premier` exists (type writer, name "Premier").
- Release `0.0.1`; push.yml run `26944000114` concluded **success** (Build Production Image / Push to ECR / Update Dev Portal Properties / Deploy to KBC all green).
- Portal `repository.tag` = `0.0.1`, uri `…/developer-portal-v2/keboola.wr-premier`.

### Phase 2 — Research the source/target system · owner: `component-plan-new`
- [x] complete

**Definition of done:** a research summary settles API style(s), auth method(s) and which the vendor
recommends, pagination, rate limits, incremental/cursor support — plus a **feasibility & provisioning
verdict** (sandbox availability, headless-auth vs admin-only setup). Blockers surfaced to the user.

**Evidence:** Verified 2026-06-04 by fresh subagent against the spec. API style = custom JSON-RPC over
HTTPS POST `/api/comm` (live-verified contract). Auth = HTTP Basic + `ID-UJ` header (only method
exposed). No pagination/batch on writes; rate limits none documented; no incremental (create-only, no
idempotency → state.json dedup strategy). Provisioning = NOT headless on customer side (admin installs
ApiComPrem service, generates ID_UJ); sandbox `dev.premier.cz:12375` reachable for reads, writes
unconfirmed, no customer creds yet. 6 ranked blockers in spec §9.

### Phase 3 — Spec + implementation plan · owner: `component-plan-new`
- [x] complete

**Definition of done:** `docs/superpowers/specs/...-design.md` committed (full scope: source system,
Keboola mapping, auth/provisioning, data model, config/schema, code architecture, datadir + VCR
tests, cf-dev deployment, risks) with **no placeholders/TODOs**, AND a superpowers plan committed at
`docs/superpowers/plans/...md`. User approved the spec.

**Evidence:** Verified 2026-06-04 by fresh subagent. Spec `06fa5ad` (all 9 sections, zero placeholder
grep matches) + plan `8ed7e85` (13 bite-sized TDD tasks with real failing-test + implementation code;
imports/method names consistent across tasks; schema↔Pydantic parity cross-checked in Task 11). User
approved the spec by invoking `/superpowers:writing-plans`.

### Phase 4 — Implement on `initial-implementation` branch · owner: `component-develop`
- [x] complete

**Definition of done:** branch `initial-implementation` exists; component logic implemented per the
plan; `run()` is a clean orchestrator with logic in private methods; `ruff check` clean. Fine-grained
step tracking lives in the superpowers plan file — this box tracks the phase as a whole.

**Evidence:** Verified 2026-06-04 by fresh subagent. Branch `initial-implementation` pushed (16 impl
commits, main..branch). `src/component.py` run() is a clean orchestrator delegating to `_build_client`/
`_validate_columns`/`_result` + sync actions `testConnection`/`listCommands`; `src/configuration.py`
(PREMIER Configuration + ColumnMap); `src/client/premier_client.py` (PremierClient/PremierResponse/
exceptions). No leftover cookiecutter logic (grep clean). `uv run ruff check src tests` → All checks
passed. `uv run pytest -q` → 28 passed. configSchema.json + configRowSchema.json present (non-template).
Implemented via subagent-driven TDD; two review gates per task; final whole-impl review found no
functional blockers (one robustness fix applied: `from __future__ import annotations`).
Remaining for later phases: VCR cassettes (Phase 5) must verify the API-contract assumptions
(inParam.parameters nesting, INFO/typ_prikazu, VERZEAPI probe) against real responses.

### Phase 5 — Local VCR tests + cassettes · owner: `component-test`
- [x] complete

**Definition of done:** datadir/unit/VCR tests present; the **full `pytest` suite runs green** (paste
the `N passed` line, not "should pass"); cassettes recorded and **verifiably sanitized** — grep every
cassette for secret patterns (the values from `secrets.json`, common keys like `token`/`password`/
`authorization`/`api_key`, and the configured `VCR_SANITIZERS` targets) and paste a clean result.

**Evidence:** Verified 2026-06-04 (commit `07703b2`). VCR read-path functional cases recorded against
`dev.premier.cz:12375`: `01_testConnection` (VERZEAPI) + `02_listCommands` (INFO/FULL, 22 IN commands).
`VCRDataDirTester` runner; `VCR_SANITIZERS` in component.py. `uv run pytest -q` → **29 passed**;
`ruff check` clean. Cassette grep for `3ce17312` / `Authorization` / `ID-UJ` / password → **no matches**.
**Recording caught a real contract bug:** the live API returns `Data[0]["CommList"]` of `{CMD:{...}}`
envelopes (NOT a flat list); `list_write_commands()` was fixed to unwrap/flatten it and unit-test mocks
updated to the real shape. Write-path cassettes intentionally deferred (no blind sandbox writes).

### Phase 6 — Full Developer Portal value setup · owner: `component-dev-portal`
- [ ] complete

**Definition of done — MUST happen *after* the `0.0.1` release:** configSchema (and row schema if
config rows), sync actions, and the portal-owned properties (descriptions, UI options, etc.) are live
in the portal, confirmed via a fresh `kbagent dev-portal` GET.

> **Ordering, do not get this wrong:** the `0.0.1` release's CI-sync writes portal values from the
> repo. If you set portal values *before* that release, the release **overwrites** them. The bootstrap
> release already happened in Phase 1, so this manual value setup is safe here — but if any further
> release is cut afterwards, re-confirm the synced-vs-portal-owned property boundary.

**Evidence:** _

### Phase 7 — Deploy + smoke-test in cf-dev (image-tag override) · owner: `component-test` (tier 4)
- [ ] complete

**Definition of done:** an image built from the `initial-implementation` branch exists in the
platform; a config created in the **cf-dev** project (via kbagent) with the **image tag overridden**
to that branch build; a real job run **succeeded** end-to-end. Evidence must include the job ID, its
`success` status, **and the resolved image tag the job actually ran** — confirm it matches the
`initial-implementation` build, not a stale stable release (a green job against the wrong image is a
false pass).

**Evidence:** _

### Phase 8 — Final CF-standards review · owner: `component-review`
- [ ] complete

**Definition of done:** `component-review` run over the full implementation; no open **blocking**
(critical/important) findings; component aligns with Component Factory standards.

> **If you cut a release after Phase 6** (e.g. promoting the reviewed component to a stable version),
> the CI property-sync runs again and overwrites the `[script]` portal properties from the repo —
> **re-run the Phase 6 verifier afterward** to confirm the portal-owned values survived. Phase 6 is
> only protected from the *bootstrap* `0.0.1` release automatically.

**Evidence:** _
