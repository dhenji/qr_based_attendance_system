"""Unit cover for `shared/email.py`: the SMTP transport, the two fallbacks, and
the fire-and-forget dispatch.

Nothing here touches the database or the network. `smtplib` is replaced on the
module under test (`shared.email.smtplib`) rather than in `sys.modules`: the
production import is a plain top-level `import smtplib`, so rebinding that one
name is enough to intercept every connection attempt.

Settings are built explicitly and passed as `settings=`, so no assertion here
depends on `get_settings()` reading the developer's `.env`.
"""

from __future__ import annotations

import asyncio
import smtplib
import threading
from email.message import EmailMessage
from typing import Any

import pytest

from core.config import Settings

from shared import email as email_module
from shared.email import (
    DEFAULT_FROM_ADDRESS,
    OutboundEmail,
    dispatch_email,
    dispatch_emails,
    send_email,
    send_otp_email,
)


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "debug": False,
        "jwt_secret": "test-secret-0123456789abcdef-0123456789",
        "smtp_host": "smtp.test.local",
        "smtp_port": 587,
        "smtp_user": "mailer@test.local",
        "smtp_password": "smtp-secret",
    }
    base.update(overrides)

    return Settings(**base)


class _Recorder:
    """What the fake clients were asked to do.

    Kept out of the client classes themselves: `SMTP` and `SMTP_SSL` are two
    distinct classes, so class-level state on one would not be visible through
    the other, and the fixture has to be able to inspect a send whichever
    constructor production picked.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.messages: list[EmailMessage] = []
        self.constructed: list[str] = []
        self.connect_args: dict[str, Any] = {}
        self.failure: BaseException | None = None

    @property
    def names(self) -> list[str]:
        return [call[0] for call in self.calls]


def _smtp_class(recorder: _Recorder, flavour: str) -> type:
    """Build a fake `smtplib` client class that records into `recorder`."""

    class _FakeClient:
        def __init__(
            self, host: str, port: int, *, timeout: float | None = None
        ) -> None:
            recorder.constructed.append(flavour)
            recorder.connect_args = {"host": host, "port": port, "timeout": timeout}
            recorder.calls.append(("__init__", host, port))

        def __enter__(self) -> "_FakeClient":
            recorder.calls.append(("enter",))
            return self

        def __exit__(self, *exc: Any) -> None:
            recorder.calls.append(("exit",))

        def ehlo(self) -> None:
            recorder.calls.append(("ehlo",))

        def starttls(self) -> None:
            recorder.calls.append(("starttls",))

        def login(self, user: str, password: str) -> None:
            recorder.calls.append(("login", user, password))

        def send_message(self, message: EmailMessage) -> None:
            recorder.calls.append(("send_message",))

            if recorder.failure is not None:
                raise recorder.failure

            recorder.messages.append(message)

    return _FakeClient


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Replace `shared.email.smtplib` with two fake client classes."""

    fake: _Recorder = _Recorder()
    module = smtplib
    module.SMTP = _smtp_class(fake, "plain")  # type: ignore[assignment]
    module.SMTP_SSL = _smtp_class(fake, "ssl")  # type: ignore[assignment]
    monkeypatch.setattr(email_module, "smtplib", module)

    return fake


def test_debug_mode_logs_and_never_connects(
    recorder: _Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(debug=True)

    with caplog.at_level("INFO", logger=email_module.__name__):
        delivered: bool = send_email(
            "student@test.local", "Your code", "123456", settings=settings
        )

    assert delivered is False
    assert recorder.calls == [], "debug mode must not open a connection"
    assert "123456" in caplog.text


def test_unset_host_skips_instead_of_raising(
    recorder: _Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(smtp_host="")

    with caplog.at_level("INFO", logger=email_module.__name__):
        delivered: bool = send_email(
            "student@test.local", "Subject", "Body", settings=settings
        )

    assert delivered is False
    assert recorder.calls == []
    assert "SMTP_HOST unset" in caplog.text


def test_plain_relay_negotiates_tls_and_authenticates(
    recorder: _Recorder,
) -> None:
    settings = _settings()

    delivered: bool = send_email(
        "student@test.local", "Excuse approved", "Body text", settings=settings
    )

    assert delivered is True
    assert recorder.constructed == ["plain"]
    assert recorder.connect_args == {
        "host": "smtp.test.local",
        "port": 587,
        "timeout": 10,
    }
    # ehlo -> starttls -> ehlo -> login, then the connection is closed on the way
    # out. The greeting is repeated because STARTTLS starts a new session.
    assert recorder.names == [
        "__init__",
        "enter",
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
        "exit",
    ]
    assert ("login", "mailer@test.local", "smtp-secret") in recorder.calls


def test_implicit_tls_skips_starttls(recorder: _Recorder) -> None:
    settings = _settings(smtp_port=465, smtp_use_ssl=True, smtp_start_tls=False)

    delivered: bool = send_email(
        "student@test.local", "Subject", "Body", settings=settings
    )

    assert delivered is True
    assert recorder.constructed == ["ssl"]
    assert recorder.connect_args["port"] == 465
    assert recorder.names == [
        "__init__",
        "enter",
        "ehlo",
        "login",
        "send_message",
        "exit",
    ]


def test_implicit_tls_never_negotiates_starttls_on_top(
    recorder: _Recorder,
) -> None:
    """`SMTP_USE_SSL=true` with STARTTLS left on must not double-encrypt.

    `.env.example` ships `SMTP_START_TLS=true`, so a deployment that moves the
    port to 465 without also flipping STARTTLS off lands on this combination.
    """

    settings = _settings(smtp_port=465, smtp_use_ssl=True, smtp_start_tls=True)

    send_email("student@test.local", "Subject", "Body", settings=settings)

    assert "starttls" not in recorder.names


def test_relay_without_credentials_skips_login(recorder: _Recorder) -> None:
    settings = _settings(smtp_user="", smtp_password="")

    send_email("student@test.local", "Subject", "Body", settings=settings)

    assert "login" not in recorder.names


def test_message_carries_from_to_subject_and_body(recorder: _Recorder) -> None:
    send_email(
        "student@test.local",
        "Excuse rejected: CS101",
        "Your excuse was rejected.\n\nReason: No medical certificate.",
        settings=_settings(smtp_from="no-reply@attendance.test"),
    )

    message: EmailMessage = recorder.messages[0]
    assert message["From"] == "no-reply@attendance.test"
    assert message["To"] == "student@test.local"
    assert message["Subject"] == "Excuse rejected: CS101"
    assert "No medical certificate." in message.get_content()


def test_from_falls_back_to_user_then_placeholder(recorder: _Recorder) -> None:
    send_email("a@test.local", "Subject", "Body", settings=_settings(smtp_from=""))
    assert recorder.messages[0]["From"] == "mailer@test.local"

    recorder.messages = []
    send_email(
        "a@test.local",
        "Subject",
        "Body",
        settings=_settings(smtp_from="", smtp_user="", smtp_password=""),
    )
    assert recorder.messages[0]["From"] == DEFAULT_FROM_ADDRESS


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPException("relay refused the message"),
        smtplib.SMTPServerDisconnected("connection dropped"),
        OSError("connection refused"),
    ],
)
def test_delivery_failure_is_swallowed(
    recorder: _Recorder,
    failure: BaseException,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dead relay must not raise into the request that already committed."""

    recorder.failure = failure
    settings = _settings()

    with caplog.at_level("WARNING", logger=email_module.__name__):
        delivered: bool = send_email(
            "student@test.local", "Subject", "Body", settings=settings
        )

    assert delivered is False
    assert "Email delivery failed" in caplog.text


def test_otp_email_still_routes_through_send_email(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The auth path depends on this signature and the default subject.

    `send_otp_email` takes no settings argument - it has always resolved them
    itself - so the fixture has to stand in for the deployment's `.env`.
    """

    monkeypatch.setattr(email_module, "get_settings", _settings)

    send_otp_email("student@test.local", "998877")

    message: EmailMessage = recorder.messages[0]
    assert message["To"] == "student@test.local"
    assert message["Subject"] == "Your Verification Code \u2013 Attendly"
    plain_part = message.get_body(preferencelist=("plain",))
    assert plain_part is not None
    assert "998877" in plain_part.get_content()
    html_part = message.get_body(preferencelist=("html",))
    assert html_part is not None
    assert "998877" in html_part.get_content()


def _capture_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Replace `send_email` on the module and report the calls it received."""

    sent: list[tuple[str, str, str]] = []
    threads: list[str] = []

    def _fake_send(
        to: str,
        subject: str,
        body: str,
        *,
        html: str | None = None,
        settings: Settings | None = None,
    ) -> bool:
        sent.append((to, subject, body))
        threads.append(threading.current_thread().name)
        return True

    monkeypatch.setattr(email_module, "send_email", _fake_send)

    return sent, threads


async def _let_executor_finish() -> None:
    """Yield to the loop long enough for the queued job to complete."""

    await asyncio.sleep(0.05)


def test_dispatch_runs_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`dispatch_emails` returns before delivery, and delivers the whole batch."""

    sent, threads = _capture_sends(monkeypatch)
    caller_thread: str = threading.current_thread().name
    batch = [
        OutboundEmail(to="a@test.local", subject="S", body="B"),
        OutboundEmail(to="b@test.local", subject="S", body="B"),
    ]

    async def _run() -> None:
        dispatch_emails(batch)
        # Nothing awaited the job, so hand the loop a chance to run it.
        await _let_executor_finish()

    asyncio.run(_run())

    assert sent == [("a@test.local", "S", "B"), ("b@test.local", "S", "B")]
    assert len(set(threads)) == 1, "a batch must be one executor job"
    assert threads[0] != caller_thread, "delivery must not run on the request"
    assert email_module._PENDING == set(), "settled futures must be released"


def test_dispatch_drops_addressless_recipients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One unreachable recipient must not hold the rest of the batch back."""

    sent, _ = _capture_sends(monkeypatch)

    dispatch_emails([OutboundEmail(to="", subject="S", body="B")])

    assert sent == []


def test_dispatch_without_a_loop_sends_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sync entry point has no loop to defer to; deliver rather than drop."""

    sent, threads = _capture_sends(monkeypatch)

    dispatch_email("a@test.local", "S", "B")

    assert sent == [("a@test.local", "S", "B")]
    assert threads == [threading.current_thread().name]


def test_dispatch_survives_a_worker_that_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed job is logged and forgotten, not surfaced to the event loop."""

    def _boom(to: str, subject: str, body: str, **kwargs: Any) -> bool:
        raise RuntimeError("worker died")

    monkeypatch.setattr(email_module, "send_email", _boom)

    async def _run() -> None:
        dispatch_email("a@test.local", "S", "B")
        await _let_executor_finish()

    with caplog.at_level("WARNING", logger=email_module.__name__):
        asyncio.run(_run())

    assert "Email dispatch failed" in caplog.text
    assert email_module._PENDING == set()
