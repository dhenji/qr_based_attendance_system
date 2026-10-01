"""Outbound email: OTP codes and excuse notifications.

`send_email` is the single delivery path and it never raises. Three branches,
in order:

- `debug` logs the whole message instead of opening a connection, so a developer
  sees exactly what a student would have received.
- An empty `smtp_host` logs and skips. Mail is deployment config
  (production-checklist §7), not a boot requirement, so a deployment with no
  relay degrades to a log line instead of failing every request that would have
  sent one.
- Otherwise the message goes out over `smtplib`: implicit TLS when
  `smtp_use_ssl` (port 465), `STARTTLS` otherwise (port 587).

`smtplib` is stdlib and nothing connects at import time, so this module stays
import-safe and adds no dependency to `requirements.txt`.

Notifications are fire-and-forget: `dispatch_emails` hands the batch to the
event loop's default executor and returns immediately, so relay latency never
lands on the request that triggered it. The dispatch happens while the request's
transaction is still open, so a commit that fails afterwards leaves the mail
already sent - accepted, because a duplicate notice is cheaper than making the
excuse endpoint depend on the relay. Nothing survives a process restart and
there is no notification table or queue; a user who misses a notice can always
re-check the request in the app.
"""

from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from logging import Logger, getLogger

from core.config import Settings, get_settings

logger: Logger = getLogger(__name__)

# Used only when neither SMTP_FROM nor SMTP_USER names a sender, so the header
# is never empty - a relay rejects a message with no From.
DEFAULT_FROM_ADDRESS: str = "noreply@localhost"

# In-flight executor futures. A future the event loop no longer holds a
# reference to can be garbage-collected before it runs, which would silently drop
# the send, so they are parked here until they settle.
_PENDING: set[asyncio.Future[None]] = set()


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    """One message waiting to go out."""

    to: str
    subject: str
    body: str


def send_email(
    to: str, subject: str, body: str, *, settings: Settings | None = None
) -> bool:
    """Deliver one message. Returns True when SMTP accepted it.

    Blocking, and synchronous because the OTP path has always been: it is called
    straight from a request handler with no executor involved. Callers that must
    not block use `dispatch_email`/`dispatch_emails` instead.

    A failure is logged and reported as False rather than raised. Every caller
    is a path that has already (or is about to) commit real work, and failing a
    committed excuse request because the relay is down would be the worse
    outcome.
    """

    current: Settings = settings or get_settings()

    if current.debug:
        logger.info("DEBUG email to=%s subject=%s\n%s", to, subject, body)
        return False

    if not current.smtp_host:
        logger.info("SMTP_HOST unset; not sending email to=%s subject=%s", to, subject)
        return False

    message: EmailMessage = _build_message(to, subject, body, current)

    try:
        with _smtp_client(current) as client:
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Email delivery failed to=%s subject=%s: %s", to, subject, exc)
        return False

    logger.info("Email sent to=%s subject=%s", to, subject)

    return True


def send_otp_email(
    to: str,
    otp_code: str,
    subject: str = "Your OTP code",
) -> None:
    body: str = f"Your verification code is: {otp_code}"
    send_email(to, subject, body)


def dispatch_email(to: str, subject: str, body: str) -> None:
    """Queue one message without waiting for delivery."""

    dispatch_emails([OutboundEmail(to=to, subject=subject, body=body)])


def dispatch_emails(
    messages: Sequence[OutboundEmail], *, settings: Settings | None = None
) -> None:
    """Queue a batch of messages and return immediately.

    The whole batch goes out as one executor job, so a bulk action that owes
    fifty students a notice costs one hop onto the thread pool rather than fifty
    - and the fifty handshakes still run one at a time, in order, on that one
    thread.

    Addresses with no value are dropped: an unreachable recipient is not a
    reason to hold the rest of the batch back.
    """

    batch: list[OutboundEmail] = [message for message in messages if message.to]

    if not batch:
        return

    current: Settings = settings or get_settings()

    try:
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (a script or a sync entry point). Send inline rather
        # than dropping the messages on the floor.
        _deliver(batch, current)
        return

    future: asyncio.Future[None] = loop.run_in_executor(
        None, _deliver, batch, current
    )
    _PENDING.add(future)
    future.add_done_callback(_settle)


def _deliver(batch: Sequence[OutboundEmail], settings: Settings) -> None:
    for message in batch:
        send_email(message.to, message.subject, message.body, settings=settings)


def _settle(future: asyncio.Future[None]) -> None:
    _PENDING.discard(future)

    if future.cancelled():
        return

    error: BaseException | None = future.exception()

    if error is not None:
        logger.warning("Email dispatch failed: %s", error)


def _build_message(
    to: str, subject: str, body: str, settings: Settings
) -> EmailMessage:
    message: EmailMessage = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user or DEFAULT_FROM_ADDRESS
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    return message


@contextmanager
def _smtp_client(settings: Settings) -> Iterator[smtplib.SMTP]:
    """Open an authenticated SMTP session and close it on the way out."""

    timeout: float = settings.smtp_timeout_seconds

    if settings.smtp_use_ssl:
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)

    with client:
        client.ehlo()

        # Implicit TLS is already encrypted, and STARTTLS on an implicit-TLS
        # connection is an error, so the negotiation is skipped there.
        if settings.smtp_start_tls and not settings.smtp_use_ssl:
            client.starttls()
            # The greeting has to be repeated for the new session's extensions.
            client.ehlo()

        # Relays that need no credentials are legitimate; login only when a
        # user is configured.
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)

        yield client