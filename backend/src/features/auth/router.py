from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from api.deps import AuthServiceDep, CurrentUserDep, OptionalUserDep
from features.auth.schema import (
    BackupCodesResponse,
    BackupCodesSummaryResponse,
    ChangePasswordRequest,
    PasswordRecoveryResetRequest,
    PasswordRecoveryStartResponse,
    ForgotPasswordStep1Request,
    ForgotPasswordStep2Request,
    LoginOtpResendRequest,
    LoginOtpVerifyRequest,
    LoginRequest,
    MeResponse,
    MFADisableRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    OTPRequest,
    OTPVerifyRequest,
    RecoveryGrantResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SecurityQuestionResponse,
    SetSecurityQuestionRequest,
    TokenResponse,
)
from shared.captcha import verify_turnstile_token
from shared.rate_limit import client_ip, rate_limit

# Prefix baked in here; mounted without a prefix argument in api/router.py.
router = APIRouter(prefix="/auth")


@router.post(
    "/otp/request",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request a 6-digit OTP",
)
async def request_otp(
    payload: OTPRequest,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 60, key="email")),
) -> None:
    await service.request_otp(payload.email, payload.purpose, payload.recovery_token)


@router.post(
    "/otp/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verify a 6-digit OTP",
)
async def otp_verify(
    payload: OTPVerifyRequest,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 300, key="email")),
) -> None:
    await service.verify_otp(payload.email, payload.code, payload.purpose)


@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Claim-based registration (OTP + password + security question)",
)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.register(
        email=payload.email,
        otp_code=payload.otp_code,
        password=payload.password,
        security_question=payload.security_question,
        security_answer=payload.security_answer,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Email/password login (with OTP + MFA gates)",
)
async def login(
    payload: LoginRequest,
    request: Request,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(20, 60, key="ip")),
    _rl_email: None = Depends(rate_limit(5, 60, key="email")),
) -> TokenResponse:
    await verify_turnstile_token(
        payload.turnstile_token,
        client_ip=client_ip(request),
    )

    return await service.login(payload.email, payload.password)


# The verify/resend bodies carry the login-OTP grant rather than an email,
# so the generic `key="email"` bucket would fall back to the client IP
# anyway: key on IP explicitly. This is a flood gate only (throughput, not
# wrong guesses — it counts successes too), so it stays coarse at 20/60s:
# the per-email and per-IP *failure* caps live in the service, failure-only,
# where they never penalise correct codes or NAT neighbours.
@router.post(
    "/login/verify",
    response_model=TokenResponse,
    summary="Verify login OTP (grants tokens, or an MFA challenge for admins)",
)
async def login_verify(
    payload: LoginOtpVerifyRequest,
    request: Request,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(20, 60, key="ip")),
) -> TokenResponse:
    return await service.verify_login_otp(
        payload.otp_token,
        payload.code,
        client_ip(request),
    )


@router.post(
    "/login/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Resend login OTP (burns the previous code)",
)
async def login_resend(
    payload: LoginOtpResendRequest,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 60, key="ip")),
) -> None:
    await service.resend_login_otp(payload.otp_token)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh-token rotation")
async def refresh(payload: RefreshRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.refresh_token(payload.refresh_token)


@router.post(
    "/forgot-password",
    summary="Forgot-password step 1 - returns security_question state",
)
async def forgot_password(
    payload: ForgotPasswordStep1Request,
    request: Request,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 60, key="email")),
) -> SecurityQuestionResponse:
    await verify_turnstile_token(
        payload.turnstile_token,
        client_ip=client_ip(request),
    )

    return await service.forgot_password(payload.email)


@router.post(
    "/forgot-password/verify",
    response_model=RecoveryGrantResponse,
    summary="Forgot-password step 2 - verify security answer, get recovery grant",
)
async def forgot_password_verify(
    payload: ForgotPasswordStep2Request,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 60, key="email")),
) -> RecoveryGrantResponse:
    return await service.forgot_password_step2(payload.email, payload.answer)


@router.post(
    "/reset-password",
    response_model=TokenResponse,
    summary="Reset password with OTP (returns the session, or an MFA challenge)",
)
async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthServiceDep,
) -> TokenResponse:
    return await service.reset_password(
        payload.email, payload.otp_code, payload.new_password
    )


@router.post(
    "/password-recovery/start",
    response_model=PasswordRecoveryStartResponse,
    summary="Start password recovery for the authenticated user (sends OTP)",
)
async def password_recovery_start(
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> PasswordRecoveryStartResponse:
    return await service.start_password_recovery(current_user)


@router.post(
    "/password-recovery/reset",
    response_model=TokenResponse,
    summary="Reset the authenticated user's password with an OTP",
)
async def password_recovery_reset(
    payload: PasswordRecoveryResetRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> TokenResponse:
    # Email is derived from the session; no email field is accepted.
    return await service.reset_password_authenticated(
        current_user, payload.otp_code, payload.new_password
    )


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> None:
    await service.change_password(
        current_user,
        payload.current_password,
        payload.new_password,
        payload.security_question,
        payload.security_answer,
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Current user info (role + security/MFA state)",
)
async def me(current_user: CurrentUserDep, service: AuthServiceDep) -> MeResponse:
    return await service.get_me(current_user)


@router.post(
    "/mfa/setup",
    response_model=MFASetupResponse,
    summary="Generate TOTP secret (authenticated)",
)
async def mfa_setup(
    current_user: CurrentUserDep, service: AuthServiceDep
) -> MFASetupResponse:
    return await service.setup_mfa(current_user)


@router.post(
    "/mfa/backup-codes",
    response_model=BackupCodesResponse,
    summary="Generate 10 backup codes (returned plaintext once)",
)
async def generate_backup_codes(
    current_user: CurrentUserDep, service: AuthServiceDep
) -> BackupCodesResponse:
    return await service.generate_backup_codes(current_user)


@router.get(
    "/mfa/backup-codes",
    response_model=BackupCodesSummaryResponse,
    summary="Backup-code summary (total/remaining, never returns hashes)",
)
async def list_backup_codes(
    current_user: CurrentUserDep, service: AuthServiceDep
) -> BackupCodesSummaryResponse:
    return await service.list_backup_codes(current_user)


@router.post(
    "/mfa/verify",
    response_model=TokenResponse,
    summary="Verify TOTP (login exchange or setup confirmation)",
)
async def mfa_verify(
    payload: MFAVerifyRequest, service: AuthServiceDep, current_user: OptionalUserDep
) -> TokenResponse:
    return await service.verify_mfa(
        code=payload.code, preauth_token=payload.preauth_token, user=current_user
    )


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable MFA (password required; clears the secret and backup codes)",
)
async def mfa_disable(
    payload: MFADisableRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> None:
    # Password, not a TOTP code: reaching this route at all required completing
    # the MFA challenge at login, so the session in hand is already proof of
    # the second factor. See security-model.md T6 for what this does *not* do
    # (it cannot revoke refresh tokens that were already issued).
    await service.disable_mfa(current_user, payload.password)


@router.post(
    "/security-question",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set/update security question (authenticated)",
)
async def security_question(
    payload: SetSecurityQuestionRequest,
    current_user: CurrentUserDep,
    service: AuthServiceDep,
) -> None:
    await service.set_security_question(current_user, payload.question, payload.answer)
