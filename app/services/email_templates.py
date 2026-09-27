from html import escape

from app.core.config import get_settings


def _layout(title: str, preview: str, content: str) -> str:
    settings = get_settings()
    logo = (
        f'<img src="{escape(settings.safesport_logo_url)}" alt="SafeSport" width="150" style="display:block;border:0">'
        if settings.safesport_logo_url
        else '<div style="font-size:24px;font-weight:800;color:#0f766e">SafeSport™</div>'
    )
    return f"""<!doctype html><html><body style="margin:0;background:#f5f7fa;font-family:Arial,sans-serif;color:#172033">
<div style="display:none;max-height:0;overflow:hidden">{escape(preview)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border:1px solid #e5e7eb;border-radius:12px">
<tr><td style="padding:28px 32px;border-bottom:1px solid #e5e7eb">{logo}</td></tr>
<tr><td style="padding:32px"><h1 style="margin:0 0 16px;font-size:24px;line-height:1.3">{escape(title)}</h1>{content}</td></tr>
<tr><td style="padding:20px 32px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.6">This security message was sent by SafeSport. If you did not request it, you can safely ignore it.</td></tr>
</table></td></tr></table></body></html>"""


def otp_email(code: str, purpose: str) -> tuple[str, str]:
    action = "sign in" if purpose == "login" else "verify your email"
    content = f"""<p style="margin:0 0 20px;color:#475569;line-height:1.6">Use this one-time code to {action}. It expires shortly.</p>
<div style="padding:18px;text-align:center;background:#f0fdfa;border:1px solid #99f6e4;border-radius:10px;font-size:34px;font-weight:800;letter-spacing:10px;color:#0f766e">{escape(code)}</div>
<p style="margin:20px 0 0;color:#64748b;font-size:13px;line-height:1.6">Never share this code with anyone. SafeSport staff will never ask for it.</p>"""
    return f"Your SafeSport {action} code", _layout("Your verification code", f"Your code is {code}", content)


def reset_email(reset_url: str) -> tuple[str, str]:
    content = f"""<p style="margin:0 0 24px;color:#475569;line-height:1.6">We received a request to reset your SafeSport password. This link expires shortly and can only be used once.</p>
<p style="margin:0 0 24px"><a href="{escape(reset_url)}" style="display:inline-block;padding:13px 22px;background:#0f766e;color:#fff;text-decoration:none;border-radius:8px;font-weight:700">Reset password</a></p>
<p style="margin:0;color:#64748b;font-size:13px;line-height:1.6">If the button does not work, copy this address into your browser:<br><span style="word-break:break-all">{escape(reset_url)}</span></p>"""
    return "Reset your SafeSport password", _layout("Reset your password", "Reset your SafeSport password", content)

