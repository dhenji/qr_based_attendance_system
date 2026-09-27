import csv
import io
from dataclasses import dataclass


@dataclass
class CsvParseError:
    line: int
    reason: str


@dataclass
class CsvRow:
    line: int
    values: dict[str, str]


def parse_csv(
    content: bytes, required_columns: tuple[str, ...]
) -> tuple[list[CsvRow], list[CsvParseError]]:
    """Structural CSV parse shared by offering bulk-enroll and roster imports.

    Returns (rows, errors). Never raises on bad rows — every structural
    problem is reported as a CsvParseError with its 1-based line number
    (header = 1). Per-row domain validation stays in the caller.
    """
    try:
        text: str = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [CsvParseError(line=1, reason="file is not valid UTF-8")]

    if not text.strip():
        return [], [CsvParseError(line=1, reason="empty file")]

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return [], [CsvParseError(line=1, reason="missing header row")]

    header: set[str] = {(name or "").strip() for name in reader.fieldnames}
    missing: list[str] = sorted(set(required_columns) - header)

    if missing:
        return [], [
            CsvParseError(line=1, reason=f"missing columns: {', '.join(missing)}")
        ]

    rows: list[CsvRow] = []

    for lineno, raw in enumerate(reader, start=2):
        values: dict[str, str] = {
            col: ((raw.get(col) or "").strip()) for col in required_columns
        }
        rows.append(CsvRow(line=lineno, values=values))

    return rows, []


def is_valid_email(value: str) -> bool:
    """Minimal email shape check shared by CSV importers."""
    if not value or "@" not in value:
        return False

    local, _, domain = value.partition("@")

    return bool(local) and "." in domain and not domain.startswith(".")
