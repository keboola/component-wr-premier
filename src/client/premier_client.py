from dataclasses import dataclass, field

import requests
from keboola.http_client import HttpClient


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
        except requests.RequestException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (401, 403):
                raise PremierAuthError(
                    f"PREMIER rejected the credentials or ID-UJ (HTTP {status})."
                ) from e
            raise PremierClientError(f"PREMIER API request failed (HTTP {status}).") from e
        return PremierResponse.from_dict(raw)

    def test_connection(self) -> None:
        """Validate host reachability + Basic auth + ID-UJ via a harmless read command."""
        resp = self.call("VERZEAPI")
        if not resp.is_ok:
            raise PremierClientError(
                f"PREMIER connection check failed: {resp.error_message or 'unexpected response'}"
            )
