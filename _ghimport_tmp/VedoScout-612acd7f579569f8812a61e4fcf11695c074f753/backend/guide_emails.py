"""guide_emails.py — funnel + newsletter email templates (ScoutMePlay warm voice)."""

from __future__ import annotations

from email_templates import _wrap_html, _btn, _site_url


def _hi(first: str | None) -> str:
    return f"Hi {first}," if first else "Hi,"


def _unsub(url: str) -> str:
    return f"""<p style="font-size:11px; color:#9A9E94; margin-top:28px;">
    You're receiving this because you requested our free parent guide.
    <a href="{url}" style="color:#9A9E94;">Unsubscribe anytime</a> — one click, no hard feelings.</p>"""


def render_guide_delivery_email(first: str | None, pdf_url: str, unsubscribe_url: str):
    subject = "Your free guide: The 5 Things Every Football Parent Gets Wrong"
    inner = f"""
    <h1 style="font-size:24px; margin:0 0 14px 0; color:#0A0F0D;">Here's your guide 🎁</h1>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">{_hi(first)}</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      Thanks for caring enough to read it — that already puts your child ahead.
      Inside you'll find the 5 mistakes almost every football parent makes,
      each with a self-check and a fix you can use <b>this week</b>.</p>
    {_btn("Download the guide", pdf_url)}
    <p style="font-size:13px; line-height:1.7; color:#3A3E36; margin-top:22px;">
      One small ask: pick <b>one</b> mistake and work on it for a month. That's how change sticks.</p>
    <p style="font-size:13px; line-height:1.7; color:#3A3E36;">Warmly,<br>The ScoutMePlay team</p>
    {_unsub(unsubscribe_url)}"""
    html = _wrap_html(inner, "Your free parent guide is ready to download")
    text = f"{_hi(first)}\n\nYour free guide is ready: {pdf_url}\n\nPick one mistake and work on it for a month.\n\n— The ScoutMePlay team\n\nUnsubscribe: {unsubscribe_url}"
    return html, text, subject


def render_guide_report_offer_email(first: str | None, code: str, percent: int,
                                    base_price: float, new_price: float, unsubscribe_url: str):
    site = _site_url()
    subject = f"See your child's game like a scout — {percent}% off your first report"
    inner = f"""
    <h1 style="font-size:24px; margin:0 0 14px 0; color:#0A0F0D;">Did the guide sting a little?</h1>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">{_hi(first)}</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      Mistake #4 — praising the wrong things — is the one most parents recognise.
      The tricky part: it's hard to praise decisions you can't see.</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      That's exactly what a ScoutMePlay report shows you: the decisions, the movement,
      the moments goals never capture. Upload one match video, and we'll break down your child's game
      the way a scout would.</p>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background:#F0F4EC; border:1px dashed #1F4F2F; margin:18px 0;">
      <tr><td style="padding:18px 22px; text-align:center;">
        <div style="font-size:11px; letter-spacing:2px; text-transform:uppercase; color:#1F4F2F; font-weight:700;">Your code — {percent}% off a full report</div>
        <div style="font-size:26px; font-weight:900; letter-spacing:4px; color:#0A0F0D; margin-top:6px;">{code}</div>
        <div style="font-size:12px; color:#6B6F66; margin-top:6px;">${base_price:.0f} → <b style="color:#1F4F2F;">${new_price:.0f}</b> · enter the code at checkout</div>
      </td></tr>
    </table>
    {_btn("Upload a match video", f"{site}/upload")}
    <p style="font-size:13px; line-height:1.7; color:#3A3E36; margin-top:22px;">
      The free preview costs nothing — no card required to start.</p>
    {_unsub(unsubscribe_url)}"""
    html = _wrap_html(inner, f"{percent}% off your first scout report — code inside")
    text = f"{_hi(first)}\n\nGet {percent}% off your first ScoutMePlay report with code {code} (${base_price:.0f} -> ${new_price:.0f}).\nUpload a match video: {site}/upload\n\nUnsubscribe: {unsubscribe_url}"
    return html, text, subject


def render_guide_membership_offer_email(first: str | None, code: str, percent: int, unsubscribe_url: str):
    site = _site_url()
    subject = f"For families who are all-in: {percent}% off your first month"
    inner = f"""
    <h1 style="font-size:24px; margin:0 0 14px 0; color:#0A0F0D;">Following the journey, match after match</h1>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">{_hi(first)}</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      One report shows you a snapshot. A membership shows you the <b>curve</b> — how your child's game
      grows from month to month, which parts of the plan are working, and what to focus on next.</p>
    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="background:#F0F4EC; border:1px dashed #1F4F2F; margin:18px 0;">
      <tr><td style="padding:18px 22px; text-align:center;">
        <div style="font-size:11px; letter-spacing:2px; text-transform:uppercase; color:#1F4F2F; font-weight:700;">New member code — {percent}% off your first month</div>
        <div style="font-size:26px; font-weight:900; letter-spacing:4px; color:#0A0F0D; margin-top:6px;">{code}</div>
        <div style="font-size:12px; color:#6B6F66; margin-top:6px;">Enter it on the checkout page</div>
      </td></tr>
    </table>
    {_btn("See memberships", f"{site}/#pricing-section")}
    <p style="font-size:13px; line-height:1.7; color:#3A3E36; margin-top:22px;">
      No pressure — the guide is yours either way. This is here when you're ready.</p>
    {_unsub(unsubscribe_url)}"""
    html = _wrap_html(inner, f"{percent}% off your first month — new member code inside")
    text = f"{_hi(first)}\n\n{percent}% off your first ScoutMePlay membership month with code {code}.\nSee plans: {site}/#pricing-section\n\nUnsubscribe: {unsubscribe_url}"
    return html, text, subject


def render_guide_paid_guide_email(first: str | None, price: float, link: str, unsubscribe_url: str):
    subject = "The complete playbook — for parents who want to go deeper"
    inner = f"""
    <h1 style="font-size:24px; margin:0 0 14px 0; color:#0A0F0D;">Want the full playbook?</h1>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">{_hi(first)}</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      The free guide covered the 5 big mistakes. The complete edition goes deeper:
      age-by-age development guides, week plans, conversation scripts for hard moments,
      and how scouts actually evaluate young players.</p>
    {_btn(f"Get the complete edition — ${price:.0f}", link)}
    <p style="font-size:13px; line-height:1.7; color:#3A3E36; margin-top:22px;">
      Every page written in the same honest, warm voice — hope and realism together.</p>
    {_unsub(unsubscribe_url)}"""
    html = _wrap_html(inner, "The complete parent playbook")
    text = f"{_hi(first)}\n\nThe complete parent playbook is available for ${price:.0f}: {link}\n\nUnsubscribe: {unsubscribe_url}"
    return html, text, subject


def render_newsletter_welcome_email(unsubscribe_url: str):
    site = _site_url()
    subject = "Welcome to The ScoutMePlay Letter ⚽"
    inner = f"""
    <h1 style="font-size:24px; margin:0 0 14px 0; color:#0A0F0D;">You're in — welcome!</h1>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      Every week we send one good football story: training ideas, honest scouting insight
      and stories from families on the same journey as yours. Written by people, for people.</p>
    <p style="font-size:14px; line-height:1.7; color:#3A3E36;">
      While you wait for the first letter, our journal is full of pieces parents tell us they wish
      they'd read sooner.</p>
    {_btn("Read the journal", f"{site}/blog")}
    <p style="font-size:13px; line-height:1.7; color:#3A3E36; margin-top:22px;">Warmly,<br>The ScoutMePlay team</p>
    <p style="font-size:11px; color:#9A9E94; margin-top:28px;">
      You signed up for our weekly letter on scoutmeplay.com.
      <a href="{unsubscribe_url}" style="color:#9A9E94;">Unsubscribe anytime</a> — one click, no hard feelings.</p>"""
    html = _wrap_html(inner, "One good football story, every week")
    text = f"Welcome to The ScoutMePlay Letter!\n\nOne good football story, every week.\nRead the journal: {site}/blog\n\nUnsubscribe: {unsubscribe_url}"
    return html, text, subject
