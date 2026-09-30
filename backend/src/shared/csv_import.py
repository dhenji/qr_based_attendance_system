from __future__ import annotations

import csv
import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(kw_only=True)
class CsvParseError:
    line: int
    reason: str


@dataclass(kw_only=True)
class CsvRow:
    line: int
    values: dict[str, str]


def parse_csv(
    content: bytes, required_columns: Sequence[str]
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


def strip_cell(value: str) -> str:
    return value.strip()


def strip_upper(value: str) -> str:
    return value.strip().upper()


def strip_lower(value: str) -> str:
    return value.strip().lower()


@dataclass(frozen=True)
class CsvColumn:
    """One expected header plus how its cell is normalized.

    `required_reason` makes the column mandatory: a blank cell fails the row
    with that exact message. Leave it None for optional columns, which
    normalize to an empty string and are carried through as-is.
    """

    name: str
    normalize: Callable[[str], str] = strip_cell
    required_reason: str | None = None


@dataclass(frozen=True)
class CsvGroup:
    """Columns that must all be present together.

    Fails the row with `reason` formatted against the schema's `subject` and
    `subject_column` value.
    """

    columns: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class CsvEmailCheck:
    """Email shape check on one column, reported with `reason`."""

    column: str
    reason: str


CsvCheck = CsvGroup | CsvEmailCheck


@dataclass(frozen=True)
class CsvSchema:
    """Declarative description of one CSV import format.

    `checks` runs in order after the per-column required check, and the first
    failure reports and skips the row — so order is part of the contract, not
    an implementation detail.
    """

    columns: tuple[CsvColumn, ...]
    subject: str
    subject_column: str
    checks: tuple[CsvCheck, ...] = ()
    subject_fallback: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


def csv_template_header(columns: Sequence[CsvColumn]) -> str:
    """Header line for the downloadable template, in declared column order."""
    return ",".join(column.name for column in columns) + "\n"


def parse_import_csv[E](
    content: bytes,
    schema: CsvSchema,
    *,
    error: Callable[[int, str], E],
) -> tuple[list[CsvRow], list[E]]:
    """Parse `content` against `schema`, returning (rows, errors).

    Rows come back with every cell normalized by its column's `normalize` and
    validated against the required columns plus `schema.checks` in order.
    Never raises on bad rows: structural problems short-circuit to a single
    line-1 error, and a failing row is reported with its own 1-based line
    number and omitted from the result.
    """
    raw_rows, structural_errors = parse_csv(content, schema.names)

    if structural_errors:
        return [], [error(found.line, found.reason) for found in structural_errors]

    rows: list[CsvRow] = []
    errors: list[E] = []

    for raw in raw_rows:
        reason: str | None = _row_error(raw, schema)

        if reason is not None:
            errors.append(error(raw.line, reason))
            continue

        rows.append(CsvRow(line=raw.line, values=_normalized(raw, schema)))

    return rows, errors


def _normalized(raw: CsvRow, schema: CsvSchema) -> dict[str, str]:
    return {
        column.name: column.normalize(raw.values.get(column.name) or "")
        for column in schema.columns
    }


def _row_error(raw: CsvRow, schema: CsvSchema) -> str | None:
    values: dict[str, str] = _normalized(raw, schema)
    subject: str = values.get(schema.subject_column) or schema.subject_fallback
    fields: dict[str, str] = {"subject": schema.subject, "key": subject}

    for column in schema.columns:
        if column.required_reason and not values[column.name]:
            return column.required_reason

    for check in schema.checks:
        if isinstance(check, CsvGroup):
            if any(not values[name] for name in check.columns):
                return check.reason.format(**fields)
        elif not is_valid_email(values.get(check.column) or ""):
            return check.reason.format(**fields)

    return None
