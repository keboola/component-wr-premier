import logging

from keboola.component.exceptions import UserException
from pydantic import BaseModel, Field, ValidationError


class ColumnMap(BaseModel):
    source: str  # input table column name
    target: str  # PREMIER inParam parameter name


class Configuration(BaseModel):
    # --- connection / auth (config level) ---
    host: str = ""
    port: int = 443
    use_https: bool = True
    username: str = ""
    password: str = Field(default="", alias="#password")
    id_uj: str = ""
    max_retries: int = 5

    # --- write target (row level) ---
    command: str | None = None
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

    def require_connection(self) -> None:
        """Validate that all connection/auth fields are present.

        ``command`` intentionally stays optional — the sync actions
        (testConnection, listCommands) run before a command is chosen.
        """
        missing = [
            name
            for name, value in (
                ("host", self.host),
                ("username", self.username),
                ("#password", self.password),
                ("accounting unit (ID-UJ)", self.id_uj),
            )
            if not value
        ]
        if missing:
            raise UserException(f"Missing required connection setting(s): {', '.join(missing)}.")
