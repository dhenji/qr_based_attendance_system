from __future__ import annotations

PASSWORD_MIN_LENGTH: int = 8
PASSWORD_MAX_LENGTH: int = 128
OTP_CODE_LENGTH: int = 6
USERNAME_MIN_LENGTH: int = 3
USERNAME_MAX_LENGTH: int = 20

SECURITY_QUESTION_MIN_LENGTH: int = 3
SECURITY_QUESTION_MAX_LENGTH: int = 200
SECURITY_ANSWER_MIN_LENGTH: int = 2
SECURITY_ANSWER_MAX_LENGTH: int = 100

SECURITY_RECOVERY_MAX_ATTEMPTS: int = 3

BACKUP_CODE_LENGTH: int = 10
BACKUP_CODE_COUNT: int = 10
BACKUP_CODE_MAX_INPUT_LENGTH: int = 16
BACKUP_CODE_GROUPS: tuple[int, int, int] = (4, 4, 2)

# Preset security questions (wireframes.md:292-294 draws a Question: [Select]
# dropdown). Doubles as the decoy pool for forgot-password step 1, so responses
# for an unknown email are indistinguishable from a real one - see ADR-056.
SECURITY_QUESTION_POOL: tuple[str, ...] = (
    "What was the name of your first pet?",
    "What was your childhood nickname?",
    "What street did you grow up on?",
    "What was the name of your first school?",
    "What is your mother's maiden name?",
    "What was your favourite teacher's name?",
    "What city were you born in?",
    "What was the name of your first car?",
    "What is the name of your favourite childhood book?",
    "What was your grandmother's favourite flower?",
)
