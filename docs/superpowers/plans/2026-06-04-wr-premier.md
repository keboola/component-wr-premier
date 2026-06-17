# wr-premier Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `keboola.wr-premier`, a generic command-driven Keboola writer that loads rows from Keboola input tables into the PREMIER system (Czech ERP) via its ApiComPrem JSON-RPC API.

**Architecture:** A `PremierClient` (subclass of `keboola.http_client.HttpClient`) wraps the single `POST /api/comm` endpoint — every PREMIER command is `{"command":{"inComm":<CMD>,"inParam":{"parameters":{…}}}}` with HTTP Basic auth + an `ID-UJ` header. The component uses **config rows** (one row = one input table → one PREMIER write command, with a column→parameter mapping). `run()` is a thin orchestrator: validate config → read input CSV → skip rows already written (state-based dedup) → call the command per row → write a per-row results table → update state. Two sync actions: `testConnection` and `listCommands` (the live write-command catalog from `INFO`).

**Tech Stack:** Python 3.14, `keboola-component` (CommonInterface, sync actions, exceptions), `keboola-http-client` (`HttpClient` with retries/Basic auth), `pydantic` v2 (config models), `responses` (HTTP mocking in unit tests), `keboola.datadirtest` + VCR (functional tests). Linting via `ruff`.

**Branch:** all work happens on `initial-implementation` (created in Task 0).

**Reference contract (verified live against `dev.premier.cz:12375`):**
- Endpoint: `POST https://<host>:<port>/api/comm`
- Headers: `Content-Type: application/json; charset=UTF-8`, `ID-UJ: <guid>`, `Authorization: Basic <base64(user:pass)>`
- Request body: `{"command":{"inComm":"<CMD>","inParam":{"parameters":{<k>:<v>}}}}`
- Response body: `{"Result":"OK"|"ERR","CommandIn":"<cmd>","Data":[…],"Error":[{"number":…,"desc":…}],"Warning":[…]}`
- `INFO` with params `{"prikaz":"FULL"}` returns `Data` of command descriptors, each with `nazov` (command name) and `typ_prikazu` (`"IN"` = write, `"OUT"` = read).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/client/__init__.py` | Re-export `PremierClient`, `PremierResponse`, and the client exceptions. |
| `src/client/premier_client.py` | `PremierResponse` (parsed envelope), `PremierClient` (the `HttpClient` subclass: `call`, `test_connection`, `list_write_commands`, `write`), and `PremierAuthError`/`PremierClientError`. |
| `src/configuration.py` | Pydantic config model(s): connection/auth (config-level) + command/mapping/dedup (row-level), merged from `self.configuration.parameters`. Raises `UserException` on validation error. |
| `src/component.py` | `Component.run()` orchestrator + `@sync_action` handlers `testConnection` and `listCommands`. Entry point with exit-code handling. |
| `component_config/configSchema.json` | Config-level UI schema (connection/auth + `testConnection` button). *Built via component-build-ui (Task 11).* |
| `component_config/configRowSchema.json` | Row-level UI schema (command dropdown via `listCommands`, column mapping, dedup, continue_on_error). *Built via component-build-ui (Task 11).* |
| `tests/test_premier_response.py` | Unit tests for `PremierResponse` parsing/helpers. |
| `tests/test_premier_client.py` | Unit tests for `PremierClient` using `responses`. |
| `tests/test_configuration.py` | Unit tests for config validation. |
| `tests/functional/` | datadir + VCR functional tests (set up in Task 10, recorded in Phase 5 by component-test). |

---

## Task 0: Create the implementation branch

**Files:** none (git only)

- [ ] **Step 1: Create and switch to the branch**

Run:
```bash
git checkout -b initial-implementation
```
Expected: `Switched to a new branch 'initial-implementation'`

- [ ] **Step 2: Add the test/runtime dependency for HTTP mocking**

Edit `pyproject.toml` — add `responses>=0.25.0` to the `dev` dependency group:
```toml
[dependency-groups]
dev = [
    "keboola.datadirtest>=2.0.0",
    "pytest>=9.0.2",
    "responses>=0.25.0",
    "ruff>=0.15.2",
]
```

- [ ] **Step 3: Sync and verify**

Run:
```bash
uv sync
```
Expected: resolves and installs `responses` with no errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add responses dev dependency, start initial-implementation"
```

---

## Task 1: `PremierResponse` envelope

**Files:**
- Create: `src/client/premier_client.py`
- Test: `tests/test_premier_response.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_premier_response.py`:
```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from client.premier_client import PremierResponse


def test_ok_response_parses():
    raw = {"Result": "OK", "CommandIn": "FA_OUT_ADD", "Data": [{"id": 1}], "Error": [], "Warning": []}
    resp = PremierResponse.from_dict(raw)
    assert resp.is_ok is True
    assert resp.data == [{"id": 1}]
    assert resp.error_message == ""


def test_err_response_collects_error_descriptions():
    raw = {
        "Result": "ERR",
        "CommandIn": "FA_OUT_ADD",
        "Data": [],
        "Error": [{"number": 5, "desc": "Invalid DPH code"}, {"number": 6, "desc": "Missing partner"}],
        "Warning": [],
    }
    resp = PremierResponse.from_dict(raw)
    assert resp.is_ok is False
    assert resp.error_message == "Invalid DPH code; Missing partner"


def test_missing_keys_default_to_empty():
    resp = PremierResponse.from_dict({"Result": "OK"})
    assert resp.data == []
    assert resp.errors == []
    assert resp.warnings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_premier_response.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'client'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/client/premier_client.py`:
```python
from dataclasses import dataclass, field


@dataclass
class PremierResponse:
    """Parsed PREMIER ApiComPrem response envelope."""

    result: str
    data: list = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return self.result == "OK"

    @property
    def error_message(self) -> str:
        return "; ".join(str(e.get("desc", "")) for e in self.errors)

    @classmethod
    def from_dict(cls, raw: dict) -> "PremierResponse":
        return cls(
            result=raw.get("Result", ""),
            data=raw.get("Data", []) or [],
            errors=raw.get("Error", []) or [],
            warnings=raw.get("Warning", []) or [],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_premier_response.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/client/premier_client.py tests/test_premier_response.py
git commit -m "feat: add PremierResponse envelope parser"
```

---

## Task 2: `PremierClient.call` + auth/error mapping

**Files:**
- Modify: `src/client/premier_client.py`
- Create: `src/client/__init__.py`
- Test: `tests/test_premier_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_premier_client.py`:
```python
import sys
from pathlib import Path

import pytest
import requests
import responses

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from client.premier_client import PremierAuthError, PremierClient, PremierClientError

BASE = "https://premier.example.com:12375/api/comm"


def make_client():
    return PremierClient(
        host="premier.example.com",
        port=12375,
        use_https=True,
        username="user",
        password="pass",
        id_uj="11111111-2222-3333-4444-555555555555",
    )


@responses.activate
def test_call_sends_correct_envelope_and_parses_ok():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"x": 1}]}, status=200)
    client = make_client()
    resp = client.call("VERZEAPI", {"foo": "bar"})
    assert resp.is_ok is True
    sent = responses.calls[0].request
    body = sent.body if isinstance(sent.body, str) else sent.body.decode()
    assert '"inComm": "VERZEAPI"' in body
    assert '"foo": "bar"' in body
    assert sent.headers["ID-UJ"] == "11111111-2222-3333-4444-555555555555"
    assert sent.headers["Authorization"].startswith("Basic ")


@responses.activate
def test_call_raises_auth_error_on_401():
    responses.add(responses.POST, BASE, status=401)
    client = make_client()
    with pytest.raises(PremierAuthError):
        client.call("VERZEAPI")


@responses.activate
def test_call_raises_client_error_on_400():
    responses.add(responses.POST, BASE, status=400)
    client = make_client()
    with pytest.raises(PremierClientError):
        client.call("VERZEAPI")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_premier_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'PremierClient'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/client/premier_client.py` (add the import at the top of the file):
```python
import requests
from keboola.http_client import HttpClient
```

Then add below `PremierResponse`:
```python
class PremierClientError(Exception):
    """Non-auth transport/protocol error talking to the PREMIER API."""


class PremierAuthError(PremierClientError):
    """Authentication or accounting-unit (ID-UJ) rejection."""


class PremierClient(HttpClient):
    """Client for the PREMIER ApiComPrem JSON-RPC endpoint (`POST /api/comm`)."""

    ENDPOINT = "comm"

    def __init__(
        self,
        host: str,
        port: int,
        use_https: bool,
        username: str,
        password: str,
        id_uj: str,
        max_retries: int = 5,
    ):
        scheme = "https" if use_https else "http"
        base_url = f"{scheme}://{host}:{port}/api/"
        super().__init__(
            base_url,
            max_retries=max_retries,
            default_http_header={
                "Content-Type": "application/json; charset=UTF-8",
                "ID-UJ": id_uj,
            },
            auth=(username, password),
        )

    def call(self, command: str, parameters: dict | None = None) -> PremierResponse:
        body = {"command": {"inComm": command, "inParam": {"parameters": parameters or {}}}}
        try:
            raw = self.post(endpoint_path=self.ENDPOINT, json=body)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (401, 403):
                raise PremierAuthError(
                    f"PREMIER rejected the credentials or ID-UJ (HTTP {status})."
                ) from e
            raise PremierClientError(f"PREMIER API request failed (HTTP {status}).") from e
        return PremierResponse.from_dict(raw)
```

Create `src/client/__init__.py`:
```python
from client.premier_client import (
    PremierAuthError,
    PremierClient,
    PremierClientError,
    PremierResponse,
)

__all__ = [
    "PremierAuthError",
    "PremierClient",
    "PremierClientError",
    "PremierResponse",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_premier_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/client/premier_client.py src/client/__init__.py tests/test_premier_client.py
git commit -m "feat: add PremierClient.call with auth/error mapping"
```

---

## Task 3: `PremierClient.test_connection`

**Files:**
- Modify: `src/client/premier_client.py`
- Test: `tests/test_premier_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_premier_client.py`:
```python
@responses.activate
def test_test_connection_ok():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"verze": "1.0.1.280"}]}, status=200)
    client = make_client()
    client.test_connection()  # must not raise


@responses.activate
def test_test_connection_err_result_raises():
    responses.add(responses.POST, BASE, json={"Result": "ERR", "Error": [{"desc": "bad unit"}]}, status=200)
    client = make_client()
    with pytest.raises(PremierClientError):
        client.test_connection()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_premier_client.py -k test_connection -v`
Expected: FAIL — `AttributeError: 'PremierClient' object has no attribute 'test_connection'`.

- [ ] **Step 3: Write minimal implementation**

Add to `PremierClient` (in `src/client/premier_client.py`):
```python
    def test_connection(self) -> None:
        """Validate host reachability + Basic auth + ID-UJ via a harmless read command."""
        resp = self.call("VERZEAPI")
        if not resp.is_ok:
            raise PremierClientError(
                f"PREMIER connection check failed: {resp.error_message or 'unexpected response'}"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_premier_client.py -k test_connection -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/client/premier_client.py tests/test_premier_client.py
git commit -m "feat: add PremierClient.test_connection"
```

---

## Task 4: `PremierClient.list_write_commands`

**Files:**
- Modify: `src/client/premier_client.py`
- Test: `tests/test_premier_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_premier_client.py`:
```python
@responses.activate
def test_list_write_commands_filters_to_in_type():
    responses.add(
        responses.POST,
        BASE,
        json={
            "Result": "OK",
            "Data": [
                {"nazov": "FA_OUT_ADD", "typ_prikazu": "IN", "popis": "issued invoice"},
                {"nazov": "INFO", "typ_prikazu": "OUT", "popis": "info"},
                {"nazov": "PARTNERI_ADD", "typ_prikazu": "IN", "popis": "add partner"},
            ],
        },
        status=200,
    )
    client = make_client()
    commands = client.list_write_commands()
    assert commands == ["FA_OUT_ADD", "PARTNERI_ADD"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_premier_client.py -k list_write_commands -v`
Expected: FAIL — `AttributeError: ... has no attribute 'list_write_commands'`.

- [ ] **Step 3: Write minimal implementation**

Add to `PremierClient`:
```python
    def list_write_commands(self) -> list[str]:
        """Return the live catalog of write (`typ_prikazu == "IN"`) command names via INFO."""
        resp = self.call("INFO", {"prikaz": "FULL"})
        if not resp.is_ok:
            raise PremierClientError(
                f"Could not list PREMIER commands: {resp.error_message or 'unexpected response'}"
            )
        return [
            str(item["nazov"])
            for item in resp.data
            if isinstance(item, dict) and item.get("typ_prikazu") == "IN" and item.get("nazov")
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_premier_client.py -k list_write_commands -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/client/premier_client.py tests/test_premier_client.py
git commit -m "feat: add PremierClient.list_write_commands"
```

---

## Task 5: `PremierClient.write`

**Files:**
- Modify: `src/client/premier_client.py`
- Test: `tests/test_premier_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_premier_client.py`:
```python
@responses.activate
def test_write_returns_response_unchanged():
    responses.add(responses.POST, BASE, json={"Result": "OK", "Data": [{"doc": 42}]}, status=200)
    client = make_client()
    resp = client.write("FA_OUT_ADD", {"DOKLAD": "FV1", "VARIABL": "2024001"})
    assert resp.is_ok is True
    body = responses.calls[0].request.body
    body = body if isinstance(body, str) else body.decode()
    assert '"inComm": "FA_OUT_ADD"' in body
    assert '"VARIABL": "2024001"' in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_premier_client.py -k test_write -v`
Expected: FAIL — `AttributeError: ... has no attribute 'write'`.

- [ ] **Step 3: Write minimal implementation**

Add to `PremierClient`:
```python
    def write(self, command: str, parameters: dict) -> PremierResponse:
        """Issue a single write/create command. The caller inspects `is_ok` / `error_message`."""
        return self.call(command, parameters)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_premier_client.py -k test_write -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/client/premier_client.py tests/test_premier_client.py
git commit -m "feat: add PremierClient.write"
```

---

## Task 6: Configuration models

**Files:**
- Modify: `src/configuration.py` (replace template content)
- Test: `tests/test_configuration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_configuration.py`:
```python
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from keboola.component.exceptions import UserException

from configuration import Configuration

VALID = {
    "host": "premier.example.com",
    "port": 12375,
    "use_https": True,
    "username": "user",
    "#password": "secret",
    "id_uj": "11111111-2222-3333-4444-555555555555",
    "command": "FA_OUT_ADD",
    "column_mapping": [{"source": "doc", "target": "DOKLAD"}],
}


def test_valid_config_parses_and_maps_secret():
    cfg = Configuration(**VALID)
    assert cfg.password == "secret"
    assert cfg.command == "FA_OUT_ADD"
    assert cfg.mapping_as_dict() == {"doc": "DOKLAD"}
    assert cfg.continue_on_error is True  # default


def test_missing_password_raises_userexception():
    data = {k: v for k, v in VALID.items() if k != "#password"}
    with pytest.raises(UserException):
        Configuration(**data)


def test_missing_command_raises_userexception():
    data = {k: v for k, v in VALID.items() if k != "command"}
    with pytest.raises(UserException):
        Configuration(**data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_configuration.py -v`
Expected: FAIL — current `Configuration` requires `print_hello`/`#api_token`, so all three tests error.

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/configuration.py` with:
```python
import logging

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class ColumnMap(BaseModel):
    source: str  # input table column name
    target: str  # PREMIER inParam parameter name


class Configuration(BaseModel):
    # --- connection / auth (config level) ---
    host: str
    port: int = 443
    use_https: bool = True
    username: str
    password: str = Field(alias="#password")
    id_uj: str
    max_retries: int = 5

    # --- write target (row level) ---
    command: str
    column_mapping: list[ColumnMap] = Field(default_factory=list)
    dedup_key_column: str | None = None
    continue_on_error: bool = True

    debug: bool = False

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Validation Error: {', '.join(error_messages)}")

        if self.debug:
            logging.debug("Component will run in Debug mode")

    def mapping_as_dict(self) -> dict[str, str]:
        """input-column -> PREMIER-parameter."""
        return {m.source: m.target for m in self.column_mapping}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_configuration.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/configuration.py tests/test_configuration.py
git commit -m "feat: replace template config with PREMIER writer configuration"
```

---

## Task 7: `Component.run()` orchestration

**Files:**
- Modify: `src/component.py` (replace template `run()`; keep the entrypoint block)
- Test: `tests/functional/` datadir cases drive this in Task 10; this task is verified by the unit-style component test below.
- Test: `tests/test_component_run.py`

This task implements: read the single input table → build parameters per row via the mapping → skip rows whose dedup key is already in `state.json` → call `client.write` → collect per-row results → write a results output table → update state → honor `continue_on_error`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_component_run.py`:
```python
import csv
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from keboola.component.exceptions import UserException

from client.premier_client import PremierResponse


def _write_datadir(tmp_path, rows, continue_on_error=True, state=None):
    data_dir = tmp_path / "data"
    (data_dir / "in" / "tables").mkdir(parents=True)
    (data_dir / "out" / "tables").mkdir(parents=True)
    in_table = data_dir / "in" / "tables" / "src.csv"
    with open(in_table, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc", "vs"])
        w.writeheader()
        w.writerows(rows)
    # minimal manifest so the SDK sees a destination/columns
    (data_dir / "in" / "tables" / "src.csv.manifest").write_text(
        json.dumps({"destination": "in.c-main.src", "columns": ["doc", "vs"]})
    )
    config = {
        "parameters": {
            "host": "premier.example.com",
            "port": 12375,
            "use_https": True,
            "username": "user",
            "#password": "secret",
            "id_uj": "11111111-2222-3333-4444-555555555555",
            "command": "FA_OUT_ADD",
            "column_mapping": [{"source": "doc", "target": "DOKLAD"}, {"source": "vs", "target": "VARIABL"}],
            "dedup_key_column": "vs",
            "continue_on_error": continue_on_error,
        },
        "storage": {"input": {"tables": [{"source": "in.c-main.src", "destination": "src.csv"}]}},
    }
    (data_dir / "config.json").write_text(json.dumps(config))
    if state is not None:
        (data_dir / "in").mkdir(exist_ok=True)
        (data_dir / "in" / "state.json").write_text(json.dumps(state))
    return data_dir


def _run(data_dir):
    from component import Component

    with mock.patch.dict("os.environ", {"KBC_DATADIR": str(data_dir)}):
        comp = Component()
        comp.run()


def _read_results(data_dir):
    out = data_dir / "out" / "tables" / "results.csv"
    with open(out) as f:
        return list(csv.DictReader(f))


def test_all_rows_written_ok(tmp_path):
    data_dir = _write_datadir(tmp_path, [{"doc": "FV1", "vs": "2024001"}, {"doc": "FV2", "vs": "2024002"}])
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="OK")
        _run(data_dir)
    results = _read_results(data_dir)
    assert [r["status"] for r in results] == ["OK", "OK"]
    # state should now contain both dedup keys
    state = json.loads((data_dir / "out" / "state.json").read_text())
    assert set(state["written_keys"]) == {"2024001", "2024002"}


def test_partial_failure_continue(tmp_path):
    data_dir = _write_datadir(tmp_path, [{"doc": "FV1", "vs": "2024001"}, {"doc": "FV2", "vs": "2024002"}])

    def side_effect(command, params):
        if params["VARIABL"] == "2024002":
            return PremierResponse(result="ERR", errors=[{"desc": "bad DPH"}])
        return PremierResponse(result="OK")

    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.side_effect = side_effect
        _run(data_dir)  # must NOT raise (continue_on_error=True)
    results = _read_results(data_dir)
    statuses = {r["vs"]: r["status"] for r in results}
    assert statuses == {"2024001": "OK", "2024002": "ERR"}
    state = json.loads((data_dir / "out" / "state.json").read_text())
    assert state["written_keys"] == ["2024001"]  # only the success is recorded


def test_dedup_skips_already_written(tmp_path):
    data_dir = _write_datadir(
        tmp_path,
        [{"doc": "FV1", "vs": "2024001"}, {"doc": "FV2", "vs": "2024002"}],
        state={"written_keys": ["2024001"]},
    )
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="OK")
        _run(data_dir)
        # only the not-yet-written row triggers a write call
        assert MockClient.return_value.write.call_count == 1
    statuses = {r["vs"]: r["status"] for r in _read_results(data_dir)}
    assert statuses == {"2024001": "SKIPPED", "2024002": "OK"}


def test_fail_fast_raises(tmp_path):
    data_dir = _write_datadir(
        tmp_path, [{"doc": "FV1", "vs": "2024001"}], continue_on_error=False
    )
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="ERR", errors=[{"desc": "nope"}])
        try:
            _run(data_dir)
            raised = False
        except UserException:
            raised = True
    assert raised is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_component_run.py -v`
Expected: FAIL — the template `run()` does not import `PremierClient`, writes `output.csv` not `results.csv`, etc.

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/component.py` with:
```python
"""PREMIER system writer component."""

import csv
import logging

from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement, ValidationResult

from client.premier_client import PremierAuthError, PremierClient, PremierClientError
from configuration import Configuration

RESULTS_TABLE = "results.csv"
RESULTS_COLUMNS = ["row_index", "dedup_key", "status", "message"]


class Component(ComponentBase):
    def __init__(self):
        super().__init__()

    def run(self):
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)

        input_tables = self.get_input_tables_definitions()
        if not input_tables:
            raise UserException("No input table found. Map exactly one table to this configuration row.")
        if len(input_tables) > 1:
            raise UserException("Expected exactly one input table per configuration row.")
        input_table = input_tables[0]

        mapping = params.mapping_as_dict()
        if not mapping:
            raise UserException("column_mapping is empty — map at least one input column to a PREMIER parameter.")

        state = self.get_state_file() or {}
        written_keys: list[str] = list(state.get("written_keys", []))
        already = set(written_keys)

        results_def = self.create_out_table_definition(RESULTS_TABLE, columns=RESULTS_COLUMNS)
        failures = 0
        successes = 0

        with (
            open(input_table.full_path, encoding="utf-8") as inp,
            open(results_def.full_path, "w", encoding="utf-8", newline="") as out,
        ):
            reader = csv.DictReader(inp)
            self._validate_columns(reader.fieldnames, mapping, params.dedup_key_column)
            writer = csv.DictWriter(out, fieldnames=RESULTS_COLUMNS)
            writer.writeheader()

            for idx, row in enumerate(reader):
                dedup_key = row.get(params.dedup_key_column) if params.dedup_key_column else None

                if dedup_key is not None and dedup_key in already:
                    writer.writerow(self._result(idx, dedup_key, "SKIPPED", "already written (state)"))
                    continue

                parameters = {target: row.get(source, "") for source, target in mapping.items()}
                resp = client.write(params.command, parameters)

                if resp.is_ok:
                    successes += 1
                    if dedup_key is not None:
                        written_keys.append(dedup_key)
                        already.add(dedup_key)
                    writer.writerow(self._result(idx, dedup_key, "OK", ""))
                else:
                    failures += 1
                    writer.writerow(self._result(idx, dedup_key, "ERR", resp.error_message))
                    if not params.continue_on_error:
                        self.write_manifest(results_def)
                        self.write_state_file({"written_keys": written_keys})
                        raise UserException(
                            f"Write failed on row {idx} (dedup key {dedup_key!r}): {resp.error_message}"
                        )

        self.write_manifest(results_def)
        self.write_state_file({"written_keys": written_keys})
        logging.info("PREMIER writer finished: %d succeeded, %d failed, %d skipped.",
                     successes, failures, len(already & set(written_keys)) if False else 0)

        if successes == 0 and failures > 0:
            raise UserException(f"All {failures} rows failed to write to PREMIER. See the results table.")

    @staticmethod
    def _result(idx: int, dedup_key, status: str, message: str) -> dict:
        return {"row_index": idx, "dedup_key": dedup_key or "", "status": status, "message": message}

    @staticmethod
    def _validate_columns(fieldnames, mapping: dict, dedup_key_column) -> None:
        cols = set(fieldnames or [])
        missing = [c for c in mapping if c not in cols]
        if missing:
            raise UserException(f"Input table is missing mapped column(s): {', '.join(sorted(missing))}.")
        if dedup_key_column and dedup_key_column not in cols:
            raise UserException(f"dedup_key_column '{dedup_key_column}' is not a column in the input table.")

    @staticmethod
    def _build_client(params: Configuration) -> PremierClient:
        return PremierClient(
            host=params.host,
            port=params.port,
            use_https=params.use_https,
            username=params.username,
            password=params.password,
            id_uj=params.id_uj,
            max_retries=params.max_retries,
        )

    @sync_action("testConnection")
    def test_connection(self) -> ValidationResult:
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)
        try:
            client.test_connection()
        except (PremierAuthError, PremierClientError) as e:
            raise UserException(str(e))
        return ValidationResult("Connection to PREMIER established.")

    @sync_action("listCommands")
    def list_commands(self) -> list[SelectElement]:
        params = Configuration(**self.configuration.parameters)
        client = self._build_client(params)
        try:
            commands = client.list_write_commands()
        except (PremierAuthError, PremierClientError) as e:
            raise UserException(str(e))
        return [SelectElement(value=c, label=c) for c in commands]


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
```

> Note for the implementer: the `listCommands`/`testConnection` sync actions instantiate `Configuration`, which requires `command` to be present. In a sync-action call the row may not yet have a `command`; if `Configuration` validation becomes a problem for `listCommands`, relax `command` to `command: str | None = None` in `configuration.py` and adjust `test_missing_command_raises_userexception` to assert on `run()` instead. Decide this when wiring sync-action tests in Task 11; the safer default is to make `command` optional and validate its presence at the top of `run()` with a `UserException`. If you take that route, add `if not params.command: raise UserException("No PREMIER command selected.")` as the first line after building the client in `run()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_component_run.py -v`
Expected: PASS (4 passed). If `successes`/`failures` logging line trips ruff later, it's cleaned in Task 8.

- [ ] **Step 5: Commit**

```bash
git add src/component.py tests/test_component_run.py
git commit -m "feat: implement PREMIER writer run() orchestration with dedup and results table"
```

---

## Task 8: Clean up the logging line and run ruff

**Files:**
- Modify: `src/component.py`

The `len(already & set(written_keys)) if False else 0` placeholder in the log line (left deliberately in Task 7 to avoid miscounting skipped rows) must be replaced with a real skipped counter.

- [ ] **Step 1: Add a `skipped` counter**

In `src/component.py`, inside `run()`: initialize `skipped = 0` next to `failures = 0`, increment it in the `SKIPPED` branch (`skipped += 1` before the `continue`), and replace the log call with:
```python
        logging.info(
            "PREMIER writer finished: %d succeeded, %d failed, %d skipped.",
            successes, failures, skipped,
        )
```

- [ ] **Step 2: Re-run the run tests**

Run: `uv run pytest tests/test_component_run.py -v`
Expected: PASS (4 passed).

- [ ] **Step 3: Run ruff across the project**

Run:
```bash
uv run ruff check src tests
uv run ruff format src tests
```
Expected: `All checks passed!` (fix any reported issues, e.g. import order, then re-run).

- [ ] **Step 4: Run the full unit suite**

Run: `uv run pytest tests/test_premier_response.py tests/test_premier_client.py tests/test_configuration.py tests/test_component_run.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/component.py
git commit -m "refactor: add skipped counter, ruff clean"
```

---

## Task 9: Update `data/config.json` example + README

**Files:**
- Modify: `data/config.json`
- Modify: `README.md`

- [ ] **Step 1: Write a realistic local-run config**

Replace `data/config.json` with:
```json
{
  "parameters": {
    "host": "dev.premier.cz",
    "port": 12375,
    "use_https": true,
    "username": "test",
    "#password": "test",
    "id_uj": "3ce17312-8dbd-49a0-94d3-2e01b65e4173",
    "command": "FA_OUT_ADD",
    "column_mapping": [
      {"source": "doc", "target": "DOKLAD"},
      {"source": "vs", "target": "VARIABL"}
    ],
    "dedup_key_column": "vs",
    "continue_on_error": true
  },
  "storage": {
    "input": {
      "tables": [
        {"source": "in.c-main.invoices", "destination": "src.csv"}
      ]
    }
  }
}
```

- [ ] **Step 2: Document the component in README.md**

Replace the template body of `README.md` with a description covering: what the writer does, the connection/auth parameters (host/port/username/`#password`/`id_uj`), that one config row = one input table → one PREMIER command, the `column_mapping`, dedup behaviour (`dedup_key_column` + state), `continue_on_error`, the results table, and the **on-premise reachability** + **Enterprise-SQL-only** preconditions. Keep it concise (≈40-60 lines).

- [ ] **Step 3: Commit**

```bash
git add data/config.json README.md
git commit -m "docs: realistic config.json example and README for PREMIER writer"
```

---

## Task 10: Functional (datadir + VCR) test scaffold

**Files:**
- Create: `tests/functional/` directory structure (one datadir case)
- Create: `tests/test_functional.py` (datadirtest runner)

This sets up the structure; **recording real cassettes is Phase 5 (component-test / generate-vcr-tests)**. Read-side cassettes (`VERZEAPI`, `INFO`) are recordable against `dev.premier.cz:12375`; write-side cassettes are deferred per the spec (no blind writes to the shared sandbox).

- [ ] **Step 1: Create a datadir test case directory**

Run:
```bash
mkdir -p tests/functional/test_list_commands/source/data
mkdir -p tests/functional/test_list_commands/expected/data/out/tables
```

- [ ] **Step 2: Add the datadirtest runner**

Create `tests/test_functional.py`:
```python
import os
import unittest
from pathlib import Path

from datadirtest import DataDirTester

FUNCTIONAL_DIR = Path(__file__).resolve().parent / "functional"


class TestFunctional(unittest.TestCase):
    def test_functional(self):
        os.environ["KBC_DATADIR"] = str(FUNCTIONAL_DIR)
        runner = DataDirTester(functional_tests_dir=str(FUNCTIONAL_DIR))
        runner.run()


if __name__ == "__main__":
    unittest.main()
```

> The concrete `source/data/config.json`, the recorded cassette, `secrets.json`, and `VCR_SANITIZERS` (scrubbing the `Authorization` header and `username`/`#password`/`id_uj`) are added by component-test in Phase 5, following the generate-vcr-tests skill. This task only lands the runner + directory so the suite has a home.

- [ ] **Step 3: Confirm the runner is discoverable (no cassette yet → expected to be skipped/empty)**

Run: `uv run pytest tests/test_functional.py -v`
Expected: collects without import errors. (It may pass trivially with no populated case, or be completed in Phase 5 — do not block the branch on a recorded cassette here.)

- [ ] **Step 4: Commit**

```bash
git add tests/functional tests/test_functional.py
git commit -m "test: scaffold datadir/VCR functional test runner"
```

---

## Task 11: configSchema + configRowSchema (delegate to component-build-ui)

**Files:**
- Create: `component_config/configSchema.json`
- Create/replace: `component_config/configRowSchema.json`

**This task is owned by `component-developer:component-build-ui`** — invoke it to build the two schemas. Provide it this field spec (from §5 of the design):

- **configSchema.json (config level):** `host` (string, required), `port` (integer, default 443), `use_https` (boolean, default true), `username` (string, required), `#password` (string secret, required), `id_uj` (string, required), `max_retries` (integer, advanced, default 5). Plus a **`testConnection`** sync-action button.
- **configRowSchema.json (row level):** `command` (string, required) populated by the **`listCommands`** sync-action dropdown; `column_mapping` (array of `{source, target}` objects, required); `dedup_key_column` (string, optional); `continue_on_error` (boolean, default true).

- [ ] **Step 1: Invoke component-build-ui** with the field spec above and have it write/validate both schemas (including the sync-action wiring) and run its schema tests.

- [ ] **Step 2: Confirm the schemas match the Pydantic model** — every `configSchema`/`configRowSchema` property must exist in `Configuration` (Task 6) with the same name/alias (`#password`, `id_uj`, `column_mapping` items `{source,target}`).

- [ ] **Step 3: Commit**

```bash
git add component_config/configSchema.json component_config/configRowSchema.json
git commit -m "feat: add config and config-row schemas for PREMIER writer"
```

---

## Task 12: Full suite + push the branch

**Files:** none (verification + git)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -v`
Expected: paste the `N passed` line — all green.

- [ ] **Step 2: Final ruff gate**

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 3: Push the branch**

Run:
```bash
git push -u origin initial-implementation
```
Expected: branch pushed; `push.yml` builds a branch image (used later for the Phase 7 cf-dev smoke test).

- [ ] **Step 4: Update the lifecycle tracker** — mark Phase 4 (implement) ready for its verifier per `docs/superpowers/wr-premier-lifecycle.md`.

---

## Notes carried from the spec (do not lose these)

- **No blind writes to `dev.premier.cz`.** Write-path cassettes/smoke tests need either explicit authorization for a single controlled sandbox write or real customer creds. Read-path (`VERZEAPI`/`INFO`) is freely recordable.
- **Idempotency depends on `dedup_key_column`.** If the user leaves it empty, re-runs re-send every row and PREMIER (create-only, no idempotency) will duplicate documents. Surface this in the UI description (component-build-ui) and README.
- **On-premise reachability & Enterprise-SQL-only** are customer preconditions, documented in the README — not solvable in code.
