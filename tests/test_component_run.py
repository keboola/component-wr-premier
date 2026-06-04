import csv
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from keboola.component.exceptions import UserException

from client.premier_client import PremierResponse


def _write_datadir(tmp_path, rows, continue_on_error=True, state=None, command="FA_OUT_ADD"):
    data_dir = tmp_path / "data"
    (data_dir / "in" / "tables").mkdir(parents=True)
    (data_dir / "out" / "tables").mkdir(parents=True)
    in_table = data_dir / "in" / "tables" / "src.csv"
    with open(in_table, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc", "vs"])
        w.writeheader()
        w.writerows(rows)
    (data_dir / "in" / "tables" / "src.csv.manifest").write_text(
        json.dumps({"destination": "in.c-main.src", "columns": ["doc", "vs"]})
    )
    params = {
        "host": "premier.example.com",
        "port": 12375,
        "use_https": True,
        "username": "user",
        "#password": "secret",
        "id_uj": "11111111-2222-3333-4444-555555555555",
        "column_mapping": [{"source": "doc", "target": "DOKLAD"}, {"source": "vs", "target": "VARIABL"}],
        "dedup_key_column": "vs",
        "continue_on_error": continue_on_error,
    }
    if command is not None:
        params["command"] = command
    config = {"parameters": params, "storage": {"input": {"tables": [{"source": "in.c-main.src", "destination": "src.csv"}]}}}
    (data_dir / "config.json").write_text(json.dumps(config))
    if state is not None:
        (data_dir / "in" / "state.json").write_text(json.dumps(state))
    return data_dir


def _run(data_dir):
    from component import Component

    with mock.patch.dict("os.environ", {"KBC_DATADIR": str(data_dir)}):
        comp = Component()
        comp.run()


def _read_results(data_dir):
    with open(data_dir / "out" / "tables" / "results.csv") as f:
        return list(csv.DictReader(f))


def test_all_rows_written_ok(tmp_path):
    data_dir = _write_datadir(tmp_path, [{"doc": "FV1", "vs": "2024001"}, {"doc": "FV2", "vs": "2024002"}])
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="OK")
        _run(data_dir)
    results = _read_results(data_dir)
    assert [r["status"] for r in results] == ["OK", "OK"]
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
        _run(data_dir)
    statuses = {r["dedup_key"]: r["status"] for r in _read_results(data_dir)}
    assert statuses == {"2024001": "OK", "2024002": "ERR"}
    state = json.loads((data_dir / "out" / "state.json").read_text())
    assert state["written_keys"] == ["2024001"]


def test_dedup_skips_already_written(tmp_path):
    data_dir = _write_datadir(
        tmp_path,
        [{"doc": "FV1", "vs": "2024001"}, {"doc": "FV2", "vs": "2024002"}],
        state={"written_keys": ["2024001"]},
    )
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="OK")
        _run(data_dir)
        assert MockClient.return_value.write.call_count == 1
    statuses = {r["dedup_key"]: r["status"] for r in _read_results(data_dir)}
    assert statuses == {"2024001": "SKIPPED", "2024002": "OK"}


def test_fail_fast_raises(tmp_path):
    data_dir = _write_datadir(tmp_path, [{"doc": "FV1", "vs": "2024001"}], continue_on_error=False)
    with mock.patch("component.PremierClient") as MockClient:
        MockClient.return_value.write.return_value = PremierResponse(result="ERR", errors=[{"desc": "nope"}])
        raised = False
        try:
            _run(data_dir)
        except UserException:
            raised = True
    assert raised is True


def test_missing_command_raises(tmp_path):
    data_dir = _write_datadir(tmp_path, [{"doc": "FV1", "vs": "2024001"}], command=None)
    with mock.patch("component.PremierClient"):
        raised = False
        try:
            _run(data_dir)
        except UserException:
            raised = True
    assert raised is True
