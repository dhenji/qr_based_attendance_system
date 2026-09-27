from shared.csv_import import is_valid_email, parse_csv

COLS = ("student_id", "first_name", "email")


def test_parses_valid_rows_with_line_numbers() -> None:
    content = b"student_id,first_name,email\nS001,Ada,ada@example.com\n"

    rows, errors = parse_csv(content, COLS)

    assert errors == []
    assert len(rows) == 1
    assert rows[0].line == 2
    assert rows[0].values["student_id"] == "S001"


def test_strips_bom_and_whitespace() -> None:
    content = "﻿student_id,first_name,email\n S001 , Ada , ada@example.com \n".encode(
        "utf-8"
    )

    rows, errors = parse_csv(content, COLS)

    assert errors == []
    assert rows[0].values == {
        "student_id": "S001",
        "first_name": "Ada",
        "email": "ada@example.com",
    }


def test_empty_file_reports_line_1() -> None:
    rows, errors = parse_csv(b"", COLS)

    assert rows == []
    assert len(errors) == 1
    assert errors[0].line == 1


def test_non_utf8_reports_line_1() -> None:
    rows, errors = parse_csv(b"\xff\xfe invalid", COLS)

    assert rows == []
    assert errors[0].line == 1


def test_missing_columns_reports_line_1() -> None:
    rows, errors = parse_csv(b"student_id,first_name\nS001,Ada\n", COLS)

    assert rows == []
    assert errors[0].line == 1
    assert "email" in errors[0].reason


def test_extra_columns_are_allowed() -> None:
    content = b"student_id,first_name,email,extra\nS001,Ada,ada@example.com,x\n"

    rows, errors = parse_csv(content, COLS)

    assert errors == []
    assert len(rows) == 1


def test_email_shape_check() -> None:
    assert is_valid_email("ada@example.com")
    assert not is_valid_email("")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("ada@.com")
    assert not is_valid_email("@example.com")
