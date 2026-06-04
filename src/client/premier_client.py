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
