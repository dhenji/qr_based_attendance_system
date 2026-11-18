"""Purpose-specific OTP email rendering.

Pure functions only: no I/O, no settings lookup. The caller resolves the
application name and expiration and passes them in, so the rendering stays
trivially testable and the expiration text can never drift from the backend's
actual OTP TTL.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass

from shared.enums import OtpPurpose


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """Subject + plain-text + HTML body for one outbound message."""

    subject: str
    text: str
    html: str


def _minute_word(minutes: int) -> str:
    return "minute" if minutes == 1 else "minutes"


def render_otp_email(
    purpose: OtpPurpose,
    otp_code: str,
    *,
    app_name: str,
    expires_minutes: int,
) -> RenderedEmail:
    brand: str = (app_name or "").strip() or "Attendly"
    minutes: int = expires_minutes if expires_minutes and expires_minutes > 0 else 5

    if purpose is OtpPurpose.LOGIN:
        heading = "Confirm Your Login"
        subject = f"Your Login Verification Code \u2013 {brand}"
        intro = (
            f"We received a request to confirm your login to your {brand} account. "
            "Use the verification code below to finish signing in."
        )
    elif purpose is OtpPurpose.FORGET_PASSWORD:
        heading = "Reset Your Password"
        subject = f"Your Password Reset Code \u2013 {brand}"
        intro = (
            f"We received a request to reset the password for your {brand} account. "
            "Use the verification code below to continue."
        )
    else:  # CLAIM (default)
        heading = "Verify Your Email Address"
        subject = f"Your Verification Code \u2013 {brand}"
        intro = (
            f"We received a request to verify your email address for your {brand} account. "
            "Use the verification code below to complete your account setup."
        )

    brand_escaped: str = _html.escape(brand, quote=True)
    code_escaped: str = _html.escape(otp_code, quote=True)
    intro_escaped: str = _html.escape(intro, quote=True)
    heading_escaped: str = _html.escape(heading, quote=True)
    subject_escaped: str = _html.escape(subject, quote=True)

    minute_word: str = _minute_word(minutes)

    text: str = (
        "Hello,\n\n"
        f"{intro}\n\n"
        f"{otp_code}\n\n"
        f"This code expires in {minutes} {minute_word}.\n\n"
        "For your security:\n"
        "- Never share this code with anyone.\n"
        f"- {brand} will never ask you to disclose your verification code.\n"
        "- If you did not request this code, you can safely ignore this email.\n\n"
        f"Thank you,\n"
        f"The {brand} Team\n\n"
        "If you did not request this code, no action is needed. "
        "For help, contact your system administrator."
    )

    html_body: str = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject_escaped}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f6f8;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:12px;">
        <tr>
          <td style="padding:24px 32px 8px;text-align:center;">
            <div style="font-size:20px;font-weight:700;color:#111827;">{brand_escaped}</div>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 32px 0;">
            <h1 style="margin:0 0 12px;font-size:22px;font-weight:700;color:#111827;text-align:center;">{heading_escaped}</h1>
            <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#374151;">{intro_escaped}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 16px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td align="center" style="background-color:#f3f4f6;border:1px solid #d1d5db;border-radius:10px;padding:20px;">
                  <div style="font-family:'Courier New',Courier,monospace;font-size:34px;font-weight:700;letter-spacing:8px;color:#111827;">{code_escaped}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 16px;">
            <p style="margin:0;font-size:14px;color:#6b7280;text-align:center;">This code expires in <strong style="color:#111827;">{minutes} {minute_word}</strong>.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 16px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#fffbeb;border:1px solid #fde68a;border-radius:8px;">
              <tr>
                <td style="padding:14px 16px;">
                  <p style="margin:0 0 8px;font-size:13px;font-weight:600;color:#92400e;">For your security</p>
                  <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;color:#92400e;">
                    <li>Never share this code with anyone.</li>
                    <li>{brand_escaped} will never ask you to disclose your verification code.</li>
                    <li>If you did not request this code, you can safely ignore this email.</li>
                  </ul>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 32px 24px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;font-size:12px;line-height:1.6;color:#6b7280;text-align:center;">
              Thank you,<br>The {brand_escaped} Team<br><br>
              If you did not request this code, no action is needed. For help, contact your system administrator.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

    return RenderedEmail(subject=subject, text=text, html=html_body)
