from logging import Logger, getLogger

from core.config import Settings, get_settings

logger: Logger = getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    settings: Settings = get_settings()

    if settings.debug:
        print("=" * 60)
        print("To:     ", to)
        print("Subject:", subject)
        print("=" * 60)
        print(body)
        print("=" * 60)
        return

    logger.warning("Email sending not implemented in production (to=%s)", to)


def send_otp_email(
    to: str,
    otp_code: str,
    subject: str = "Your OTP code",
) -> None:
    body: str = f"Your verification code is: {otp_code}"
    send_email(to, subject, body)
