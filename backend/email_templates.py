"""
email_templates.py — HTML + plaintext email templates for ScoutMePlay.

Every template returns `(html, plaintext, subject)`. Uses only inline styles
so it renders correctly across Gmail, Outlook, Apple Mail, mobile clients.
The palette matches the app: forest #1F4F2F, forest-pop #2D6B3D, volt #CCFF00,
cream #F5F1E8, ink #0A0F0D.
"""
from __future__ import annotations

import os
from typing import Optional


def _site_url() -> str:
    """The public URL of the site — used to build absolute links inside
    the email bodies. Falls back to a sensible default so preview envs
    still send working emails.
    """
    url = os.environ.get("SITE_PUBLIC_URL") or os.environ.get("FRONTEND_URL")
    if url:
        return url.rstrip("/")
    # In prod this env var should be set to https://scoutmeplay.com
    return "https://scoutmeplay.com"


def _wrap_html(inner_html: str, preheader: str = "") -> str:
    """Full ScoutMePlay-branded email chrome around a content block."""
    site = _site_url()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ScoutMePlay</title>
</head>
<body style="margin:0; padding:0; background:#F5F1E8; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color:#0A0F0D;">
  <span style="display:none !important; visibility:hidden; opacity:0; max-height:0; max-width:0; overflow:hidden; mso-hide:all;">
    {preheader}
  </span>
  <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background:#F5F1E8;">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="max-width:600px; background:#FFFFFF; border:1px solid #D4CFC1;">
        <!-- Header — forest bar with volt accent -->
        <tr><td style="background:#1F4F2F; padding:20px 28px; border-bottom:3px solid #CCFF00;">
          <table role="presentation" cellspacing="0" cellpadding="0" width="100%">
            <tr>
              <td style="color:#FFFFFF; font-size:20px; font-weight:900; letter-spacing:2px; text-transform:uppercase;">
                Scout<span style="color:#CCFF00;">Me</span>Play
              </td>
              <td align="right" style="color:#FFFFFFAA; font-size:9px; letter-spacing:2.5px; text-transform:uppercase; font-weight:700;">
                Pro Scout Intelligence
              </td>
            </tr>
          </table>
        </td></tr>
        <!-- Content -->
        <tr><td style="padding:36px 28px 24px 28px;">
          {inner_html}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#0A0F0D; padding:22px 28px; color:#F5F1E8AA; font-size:11px; line-height:1.6;">
          <table role="presentation" cellspacing="0" cellpadding="0" width="100%">
            <tr>
              <td>
                <span style="color:#CCFF00; font-weight:800; letter-spacing:2px; text-transform:uppercase; font-size:9px;">
                  MENTALKIDS / Denmark
                </span><br>
                <a href="{site}" style="color:#F5F1E8; text-decoration:none;">{site.replace("https://", "").replace("http://", "")}</a>
              </td>
              <td align="right" style="font-size:9px; letter-spacing:1.5px; text-transform:uppercase; color:#F5F1E888;">
                Professional · Independent · Evidence-based
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _btn(label: str, href: str) -> str:
    """Consistent volt-lime CTA button used across templates."""
    return f"""
    <table role="presentation" cellspacing="0" cellpadding="0">
      <tr><td style="background:#CCFF00; padding:14px 26px;">
        <a href="{href}" style="color:#0A0F0D; font-weight:900; font-size:13px; letter-spacing:2px; text-transform:uppercase; text-decoration:none; display:inline-block;">
          {label} →
        </a>
      </td></tr>
    </table>
    """


# ── WELCOME ────────────────────────────────────────────────────────────────
def render_welcome_email(user_name: Optional[str] = None) -> tuple[str, str, str]:
    site = _site_url()
    display_name = (user_name or "player").strip() or "player"
    subject = f"Welcome to ScoutMePlay, {display_name} — your scout journey starts here"
    preheader = "Upload your first video and get an instant AI scout report."
    inner = f"""
    <h1 style="margin:0 0 8px 0; font-size:28px; letter-spacing:-0.5px; color:#0A0F0D; text-transform:uppercase; font-weight:900; line-height:1.05;">
      Welcome, {display_name}.
    </h1>
    <div style="height:3px; width:48px; background:#CCFF00; margin:0 0 20px 0;"></div>
    <p style="margin:0 0 14px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      Your account is live &mdash; you now have access to <strong>Pro Scout Intelligence</strong>, the football scout analysis platform built for ambitious U7&ndash;U21 players.
    </p>
    <p style="margin:0 0 22px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      Here&apos;s how to get your first report:
    </p>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin:0 0 26px 0;">
      <tr><td style="padding:0 0 10px 0; font-size:14px; color:#1F2724;">
        <strong style="color:#1F4F2F;">01</strong> &nbsp;&nbsp; Upload a video from a real match or training (5&ndash;15 min ideal).
      </td></tr>
      <tr><td style="padding:0 0 10px 0; font-size:14px; color:#1F2724;">
        <strong style="color:#1F4F2F;">02</strong> &nbsp;&nbsp; Mark your player in 10 taps so we know who to analyse.
      </td></tr>
      <tr><td style="padding:0 0 10px 0; font-size:14px; color:#1F2724;">
        <strong style="color:#1F4F2F;">03</strong> &nbsp;&nbsp; Get an <strong>instant AI scout report</strong> across 4 pillars: Technical, Tactical, Physical, Mindset.
      </td></tr>
    </table>
    {_btn("Upload your first video", f"{site}/upload")}
    <p style="margin:24px 0 0 0; font-size:12px; color:#6B6B6B; line-height:1.6;">
      Honest, age-appropriate, professional. No hype, no false trial promises &mdash; just the real read.
    </p>
    """
    plaintext = (
        f"Welcome to ScoutMePlay, {display_name}!\n\n"
        f"Your account is live. Upload your first video and get an instant AI scout report across "
        f"Technical, Tactical, Physical and Mindset.\n\n"
        f"Upload here: {site}/upload\n\n"
        f"ScoutMePlay — Professional · Independent · Evidence-based"
    )
    return _wrap_html(inner, preheader), plaintext, subject


# ── CURVE REMINDER ─────────────────────────────────────────────────────────
def render_curve_reminder_email(
    parent_name: Optional[str],
    player_name: Optional[str],
    weeks_since: int,
) -> tuple[str, str, str]:
    site = _site_url()
    player = (player_name or "your player").strip() or "your player"
    first = player.split(" ")[0]
    greet = (parent_name or "").strip()
    greet_line = f"Hi {greet}," if greet else "Hi,"
    subject = f"{first}'s development curve is waiting for its next point"
    preheader = f"It's been {weeks_since} weeks — upload a new video and see exactly how much {first} has grown."
    inner = f"""
    <h1 style="margin:0 0 8px 0; font-size:26px; letter-spacing:-0.5px; color:#0A0F0D; text-transform:uppercase; font-weight:900; line-height:1.1;">
      {first}&apos;s next chapter is ready to be measured.
    </h1>
    <div style="height:3px; width:48px; background:#CCFF00; margin:0 0 20px 0;"></div>
    <p style="margin:0 0 14px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      {greet_line}
    </p>
    <p style="margin:0 0 14px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      It&apos;s been <strong>{weeks_since} weeks</strong> since {first}&apos;s last analysis &mdash; the perfect window for real, visible development.
    </p>
    <p style="margin:0 0 22px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      Upload a new video and your next report will <strong>automatically compare every skill</strong> against last time:
    </p>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin:0 0 24px 0; background:#F5F1E8; border-left:3px solid #CCFF00;">
      <tr><td style="padding:16px 18px;">
        <p style="margin:0 0 8px 0; font-size:14px; color:#1F4F2F; font-weight:800; letter-spacing:1px; text-transform:uppercase;">The Development Curve shows you</p>
        <p style="margin:0 0 6px 0; font-size:14px; color:#1F2724;">&#9650;&nbsp; Category deltas &mdash; e.g. <strong>Technical 6.2 &rarr; 7.0</strong></p>
        <p style="margin:0 0 6px 0; font-size:14px; color:#1F2724;">&#127942;&nbsp; Biggest improvements &mdash; did the home drills pay off?</p>
        <p style="margin:0; font-size:14px; color:#1F2724;">&#128200;&nbsp; From the 3rd analysis: {first}&apos;s full progress chart over time</p>
      </td></tr>
    </table>
    {_btn("Upload a new video", f"{site}/upload")}
    <p style="margin:24px 0 0 0; font-size:12px; color:#6B6B6B; line-height:1.6;">
      Tip: film the same type of footage as last time (match or training) &mdash; it makes the comparison strongest.
      You receive this because {first} has a ScoutMePlay analysis. Reply to this email to opt out of reminders.
    </p>
    """
    plaintext = (
        f"{greet_line}\n\n"
        f"It's been {weeks_since} weeks since {player}'s last ScoutMePlay analysis — the perfect window for visible development.\n\n"
        f"Upload a new video and the next report automatically compares every skill against last time: "
        f"category deltas (e.g. Technical 6.2 -> 7.0), biggest improvements, and from the 3rd analysis a full progress chart.\n\n"
        f"Upload here: {site}/upload\n\n"
        f"Tip: film the same type of footage as last time — it makes the comparison strongest.\n"
        f"Reply to this email to opt out of reminders."
    )
    return _wrap_html(inner, preheader), plaintext, subject


# ── PURCHASE CONFIRMATION ─────────────────────────────────────────────────
def render_purchase_confirmation(
    user_name: Optional[str],
    product_name: str,
    amount_cents: int,
    currency: str = "USD",
    extra_details: Optional[str] = None,
) -> tuple[str, str, str]:
    """extra_details: e.g. 'Extra report — Premium subscriber rate' shown as
    a small subtitle under the product name.
    """
    site = _site_url()
    display_name = (user_name or "").strip() or "there"
    amount = amount_cents / 100.0
    amount_str = f"${amount:.2f}" if (currency or "USD").upper() == "USD" else f"{amount:.2f} {currency.upper()}"
    subject = f"Payment received — {product_name} · ScoutMePlay"
    preheader = f"Thanks for your purchase — {amount_str} · {product_name}"
    details_html = f'<div style="margin-top:4px; font-size:12px; color:#6B6B6B;">{extra_details}</div>' if extra_details else ""
    inner = f"""
    <span style="display:inline-block; padding:4px 10px; background:#1F4F2F; color:#CCFF00; font-size:10px; letter-spacing:2px; text-transform:uppercase; font-weight:800;">
      Payment received
    </span>
    <h1 style="margin:14px 0 8px 0; font-size:28px; letter-spacing:-0.5px; color:#0A0F0D; text-transform:uppercase; font-weight:900; line-height:1.05;">
      Thanks, {display_name}.
    </h1>
    <div style="height:3px; width:48px; background:#CCFF00; margin:0 0 20px 0;"></div>
    <p style="margin:0 0 22px 0; font-size:15px; line-height:1.6; color:#1F2724;">
      Your purchase went through successfully. Your account is updated and you can start uploading right away.
    </p>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background:#F5F1E8; border:1px solid #D4CFC1; margin:0 0 24px 0;">
      <tr><td style="padding:16px 18px;">
        <div style="font-size:9.5px; letter-spacing:2px; text-transform:uppercase; font-weight:800; color:#1F4F2F;">Order</div>
        <div style="margin-top:6px; font-size:16px; font-weight:800; color:#0A0F0D;">{product_name}</div>
        {details_html}
        <div style="margin-top:10px; font-size:24px; font-weight:900; color:#1F4F2F; letter-spacing:-0.5px;">{amount_str}</div>
      </td></tr>
    </table>
    {_btn("Go to your dashboard", f"{site}/dashboard")}
    <p style="margin:22px 0 0 0; font-size:12px; color:#6B6B6B; line-height:1.6;">
      A receipt is automatically issued via Stripe. If you need an invoice for accounting, reply to this email
      and we&apos;ll send one over.
    </p>
    """
    plaintext = (
        f"Payment received — {amount_str}\n"
        f"Product: {product_name}\n"
        f"{(extra_details + chr(10)) if extra_details else ''}"
        f"\nGo to your dashboard: {site}/dashboard\n\n"
        f"Thanks for backing ScoutMePlay."
    )
    return _wrap_html(inner, preheader), plaintext, subject


# ── ADMIN BULK-MAIL RENDERER ──────────────────────────────────────────────
def render_bulk_email(subject: str, body_html: str, preheader: str = "") -> tuple[str, str, str]:
    """Wraps an admin-authored HTML body in the ScoutMePlay chrome."""
    inner = f"""
    <div style="font-size:15px; line-height:1.65; color:#1F2724;">
      {body_html}
    </div>
    """
    plaintext = f"{subject}\n\n(Please view this email in an HTML-capable client for the full formatting.)"
    return _wrap_html(inner, preheader or subject), plaintext, subject


# ── ADMIN SALE NOTIFICATION ───────────────────────────────────────────────
def render_admin_sale_notification(
    product_name: str,
    amount_cents: int,
    currency: str,
    buyer_email: str,
    buyer_name: Optional[str] = None,
    extra_details: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, str, str]:
    """Realtime sales feed to the ScoutMePlay operator inbox.
    Fires from the Stripe webhook right after every successful payment.
    """
    site = _site_url()
    amount = amount_cents / 100.0
    amount_str = f"${amount:.2f}" if (currency or "USD").upper() == "USD" else f"{amount:.2f} {(currency or 'USD').upper()}"
    display_buyer = (buyer_name or "").strip() or buyer_email
    short_product = product_name.replace(" Subscription", "").replace(" Purchase", "")
    subject = f"💸 New sale — {amount_str} · {short_product} · {display_buyer}"
    preheader = f"{amount_str} from {display_buyer} — {product_name}"
    details_html = f'<div style="margin-top:4px; font-size:12px; color:#6B6B6B;">{extra_details}</div>' if extra_details else ""
    session_html = f'<div style="margin-top:14px; font-size:10.5px; color:#6B6B6B; letter-spacing:1px; text-transform:uppercase; font-weight:700;">Stripe session</div><div style="margin-top:2px; font-size:12px; color:#0A0F0D; font-family:monospace; word-break:break-all;">{session_id}</div>' if session_id else ""
    inner = f"""
    <span style="display:inline-block; padding:4px 10px; background:#CCFF00; color:#0A0F0D; font-size:10px; letter-spacing:2px; text-transform:uppercase; font-weight:800;">
      New sale
    </span>
    <h1 style="margin:14px 0 8px 0; font-size:32px; letter-spacing:-0.5px; color:#0A0F0D; text-transform:uppercase; font-weight:900; line-height:1.05;">
      {amount_str}
    </h1>
    <div style="height:3px; width:48px; background:#CCFF00; margin:0 0 20px 0;"></div>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background:#F5F1E8; border:1px solid #D4CFC1; margin:0 0 22px 0;">
      <tr><td style="padding:16px 18px;">
        <div style="font-size:9.5px; letter-spacing:2px; text-transform:uppercase; font-weight:800; color:#1F4F2F;">Product</div>
        <div style="margin-top:6px; font-size:16px; font-weight:800; color:#0A0F0D;">{product_name}</div>
        {details_html}
        <div style="margin-top:16px; font-size:9.5px; letter-spacing:2px; text-transform:uppercase; font-weight:800; color:#1F4F2F;">Buyer</div>
        <div style="margin-top:4px; font-size:14px; font-weight:700; color:#0A0F0D;">{display_buyer}</div>
        <div style="margin-top:2px; font-size:12px; color:#6B6B6B;">{buyer_email}</div>
        {session_html}
      </td></tr>
    </table>
    {_btn("Open admin dashboard", f"{site}/admin")}
    <p style="margin:22px 0 0 0; font-size:11px; color:#6B6B6B; line-height:1.6;">
      Auto-generated when Stripe fires <code>checkout.session.completed</code>. Payments feed lives at <a href="{site}/admin" style="color:#1F4F2F; font-weight:700;">/admin → Payments</a>.
    </p>
    """
    plaintext = (
        f"NEW SALE — {amount_str}\n"
        f"Product: {product_name}\n"
        f"{(extra_details + chr(10)) if extra_details else ''}"
        f"Buyer: {display_buyer} <{buyer_email}>\n"
        f"{('Stripe session: ' + session_id + chr(10)) if session_id else ''}"
        f"\nAdmin: {site}/admin"
    )
    return _wrap_html(inner, preheader), plaintext, subject
