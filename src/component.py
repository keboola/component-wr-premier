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
        if not params.command:
            raise UserException("No PREMIER command selected for this configuration row.")
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

        results_def = self.create_out_table_definition(RESULTS_TABLE, schema=RESULTS_COLUMNS)
        successes = 0
        failures = 0
        skipped = 0

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
                    skipped += 1
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
        logging.info(
            "PREMIER writer finished: %d succeeded, %d failed, %d skipped.",
            successes,
            failures,
            skipped,
        )

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
