from fastapi import APIRouter, Depends, Request, status

from api.deps import AuthServiceDep, CurrentUserDep, OptionalUserDep
from features.auth.schema import (
    ChangePasswordRequest,
    ForgotPasswordStep1Request,
    ForgotPasswordStep2Request,
    LoginRequest,
    MeResponse,
    MFASetupResponse,
    MFAVerifyRequest,
    OTPRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SecurityQuestionResponse,
    SetSecurityQuestionRequest,
    TokenResponse,
)
from shared.captcha import verify_turnstile_token
from shared.rate_limit import rate_limit

router = APIRouter()


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
    await service.request_otp(payload.email, payload.purpose)


@router.post(
    "/otp/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verify a 6-digit OTP",
)
async def otp_verify(payload: OTPVerifyRequest, service: AuthServiceDep) -> None:
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
        username=payload.username,
        password=payload.password,
        security_question=payload.security_question,
        security_answer=payload.security_answer,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Email/password login (with MFA gate)",
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
        client_ip=request.client.host if request.client is not None else None,
    )

    return await service.login(payload.email, payload.password)


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
        client_ip=request.client.host if request.client is not None else None,
    )

    return await service.forgot_password(payload.email)


@router.post(
    "/forgot-password/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forgot-password step 2 - verify security answer (3-attempt cap)",
)
async def forgot_password_verify(
    payload: ForgotPasswordStep2Request,
    service: AuthServiceDep,
    _: None = Depends(rate_limit(5, 60, key="email")),
) -> None:
    await service.forgot_password_step2(payload.email, payload.answer)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset password with OTP",
)
async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthServiceDep,
) -> None:
    await service.reset_password(payload.email, payload.otp_code, payload.new_password)


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
        current_user, payload.current_password, payload.new_password
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
