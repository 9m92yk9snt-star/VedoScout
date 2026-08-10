"""
email_service.py — Gmail SMTP + transactional & bulk email for ScoutMePlay.

Design:
  - Uses stdlib `smtplib` + `email.message.EmailMessage` (SSL on port 465).
  - Reads SMTP config from env variables. If ANY are missing the module
    silently no-ops with a WARNING log — the backend still works in dev
    even without email credentials configured.
  - Send helpers accept `background_tasks: BackgroundTasks` so API endpoints
    never block on SMTP latency.
  - Bulk send throttles at ~1 email per second to stay well below Gmail's
    free-tier limits (500/day, ~100/hour). For volumes > 500/day switch to
    a transactional provider (SendGrid / Postmark) — see notes below.

Env vars required (all in backend/.env):
  SMTP_HOST         = smtp.gmail.com
  SMTP_PORT         = 465
  SMTP_USERNAME     = scoutmeplay@gmail.com
  SMTP_PASSWORD     = <16-char Google App Password>
  SMTP_FROM_NAME    = ScoutMePlay
  SMTP_FROM_EMAIL   = scoutmeplay@gmail.com   (usually same as SMTP_USERNAME)

Obtaining the Gmail App Password:
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Step Verification if not already on
  3. Under "How you sign in to Google" click "App passwords"
     (or open https://myaccount.google.com/apppasswords directly)
  4. Name the app "ScoutMePlay Backend", click "Create"
  5. Copy the 16-character password Google shows you into SMTP_PASSWORD
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

logger = logging.getLogger(__name__)


def _smtp_config() -> Optional[dict]:
    """Reads SMTP env vars — returns None if incomplete (email disabled)."""
    host = os.environ.get("SMTP_HOST")
    port_raw = os.environ.get("SMTP_PORT")
    user = os.environ.get("SMTP_USERNAME")
    pwd = os.environ.get("SMTP_PASSWORD")
    if not host or not port_raw or not user or not pwd:
        return None
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        logger.warning("SMTP_PORT is not an integer — email disabled")
        return None
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": pwd,
        "from_name": os.environ.get("SMTP_FROM_NAME") or "ScoutMePlay",
        "from_email": os.environ.get("SMTP_FROM_EMAIL") or user,
    }


def email_enabled() -> bool:
    """Public — used by callers to log/skip when email is not configured."""
    return _smtp_config() is not None


# ── Email log + open tracking (admin visibility) ─────────────────────────────
_LOG = {"col": None}


def enable_email_log(mongo_url: str, db_name: str) -> None:
    """Called once at startup. Sync pymongo client — send_email runs in
    executor threads, so sync writes are safe and simple here."""
    try:
        from pymongo import MongoClient
        _LOG["col"] = MongoClient(mongo_url)[db_name]["email_log"]
        logger.info("email log enabled")
    except Exception as exc:
        logger.warning("email log disabled: %s", exc)


def _public_site_url() -> str:
    url = os.environ.get("SITE_PUBLIC_URL") or os.environ.get("FRONTEND_URL")
    return url.rstrip("/") if url else "https://scoutmeplay.com"


def _log_email(log_id: str, to: str, subject: str, category: Optional[str], status: str) -> None:
    col = _LOG["col"]
    if col is None:
        return
    try:
        from datetime import datetime, timezone
        col.insert_one({
            "id": log_id,
            "to": (to or "").lower()[:120],
            "subject": (subject or "")[:200],
            "category": (category or "other")[:40],
            "status": status,
            "ts": datetime.now(timezone.utc),
            "opened_at": None,
        })
    except Exception as exc:
        logger.warning("email log insert failed: %s", exc)


def _track_links(html: str, log_id: str) -> str:
    """Rewrites every http(s) link through /api/email/click/{log_id} so clicks
    are measurable. The click endpoint only redirects to our own domains."""
    import re
    from urllib.parse import quote
    base = f"{_public_site_url()}/api/email/click/{log_id}"

    def _sub(m):
        url = m.group(2)
        if "/api/email/" in url:
            return m.group(0)
        return f'{m.group(1)}{base}?u={quote(url, safe="")}{m.group(3)}'

    return re.sub(r'(href=")(https?://[^"]+)(")', _sub, html or "")


def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    category: Optional[str] = None,
    track: bool = True,
) -> bool:
    """Send ONE email synchronously via Gmail SMTP.

    Returns True on success, False on failure or when SMTP is not configured.
    Never raises — logs errors and returns False so callers can fire-and-forget
    in background tasks without crashing the request.
    """
    cfg = _smtp_config()
    if cfg is None:
        logger.warning("SMTP not configured — skipping email to %s (subject: %s)", to, subject)
        return False
    if not to or "@" not in to:
        logger.warning("Skipping email — invalid recipient: %r", to)
        return False

    # open-tracking pixel (best-effort — some clients block remote images).
    # Skipped for transactional mail (receipts) — trackers raise spam scores.
    import uuid as _uuid
    log_id = _uuid.uuid4().hex
    if track:
        pixel = (f'<img src="{_public_site_url()}/api/email/open/{log_id}.png" '
                 f'width="1" height="1" style="display:none" alt="">')
        if "</body>" in html_body:
            html_body = html_body.replace("</body>", pixel + "</body>", 1)
        else:
            html_body = html_body + pixel
        # click tracking — every link becomes measurable via /api/email/click/{id}
        html_body = _track_links(html_body, log_id)

    msg = EmailMessage()
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    # multipart/alternative: plaintext fallback for clients that block HTML
    msg.set_content(text_body or _html_to_text(html_body))
    msg.add_alternative(html_body, subtype="html")

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=20) as server:
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        logger.info("Sent email to %s (subject: %s)", to, subject)
        _log_email(log_id, to, subject, category, "sent")
        return True
    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "Gmail auth failed — check SMTP_USERNAME + SMTP_PASSWORD (App Password required). "
            "Details: %s",
            exc,
        )
        _log_email(log_id, to, subject, category, "failed")
        return False
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("SMTP failure sending to %s: %s", to, exc)
        _log_email(log_id, to, subject, category, "failed")
        return False


async def send_email_async(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    category: Optional[str] = None,
    track: bool = True,
) -> bool:
    """Non-blocking wrapper — runs the sync send in a thread executor so it
    can be awaited from FastAPI endpoints without blocking the event loop."""
    return await asyncio.get_running_loop().run_in_executor(
        None,
        send_email,
        to, subject, html_body, text_body, reply_to, category, track,
    )


async def send_bulk_email(
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    delay_seconds: float = 1.0,
    on_progress=None,
) -> dict:
    """Send the same subject/body to many recipients, throttled.

    Args:
        recipients: list of email addresses. Duplicates are removed.
        delay_seconds: sleep between sends (default 1s -> ~60/min, well
                       below Gmail's ~100/hour hidden throttle).
        on_progress: optional async callback(sent, failed, total) invoked
                     after each email — used by the admin UI to store
                     job progress in Mongo.

    Returns a dict {sent, failed, total, invalid_emails, failed_emails}.
    """
    unique = []
    seen = set()
    for r in recipients:
        r = (r or "").strip().lower()
        if not r or "@" not in r or r in seen:
            continue
        seen.add(r)
        unique.append(r)

    total = len(unique)
    sent = 0
    failed = 0
    failed_emails: list[str] = []

    if total == 0 or not email_enabled():
        return {
            "sent": 0, "failed": 0, "total": 0,
            "invalid_emails": 0, "failed_emails": [],
            "skipped_reason": None if total else "no_recipients"
                              if email_enabled() else "smtp_not_configured",
        }

    for addr in unique:
        ok = await send_email_async(addr, subject, html_body, text_body, reply_to)
        if ok:
            sent += 1
        else:
            failed += 1
            failed_emails.append(addr)
        if on_progress:
            try:
                await on_progress(sent, failed, total)
            except Exception as exc:
                logger.warning("Bulk progress callback raised: %s", exc)
        # Throttle between sends
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return {
        "sent": sent,
        "failed": failed,
        "total": total,
        "invalid_emails": len(recipients) - total,
        "failed_emails": failed_emails[:20],  # cap for storage
    }


def _html_to_text(html: str) -> str:
    """Very small HTML → text fallback for the plaintext alternative.
    Not a full renderer — just strips tags and collapses whitespace.
    """
    import re
    txt = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.IGNORECASE)
    txt = re.sub(r"</p\s*>", "\n\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()
