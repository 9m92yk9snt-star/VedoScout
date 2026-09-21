"""Dashboard Hub — admin-controlled community numbers, inbox
(messages/notifications composed by admin), and Trials & Opportunities
for the player dashboard. Premium gating: free users never receive
scout/agent/club message content — only a locked count for the UI."""
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("dashboard_hub")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


COMMUNITY_DEFAULTS = {
    "enabled": True,
    "use_live_players": False,
    "players_in_library": 2847, "players_wk": 146,
    "clubs_looking": 312, "clubs_wk": 12,
    "scouts_searching": 156, "scouts_wk": 8,
    "active_agents": 24, "agents_wk": 4,
    "trial_invites": 18, "trials_wk": 3,
}

VALID_TARGETS = ("all", "free", "premium", "vip")
VALID_SENDERS = ("admin", "scout", "agent", "club")
VALID_KINDS = ("notification", "message")
EXTERNAL_SENDERS = ("scout", "agent", "club")


class CommunityUpdate(BaseModel):
    enabled: Optional[bool] = None
    use_live_players: Optional[bool] = None
    players_in_library: Optional[int] = None
    players_wk: Optional[int] = None
    clubs_looking: Optional[int] = None
    clubs_wk: Optional[int] = None
    scouts_searching: Optional[int] = None
    scouts_wk: Optional[int] = None
    active_agents: Optional[int] = None
    agents_wk: Optional[int] = None
    trial_invites: Optional[int] = None
    trials_wk: Optional[int] = None


class ComposeMessage(BaseModel):
    kind: str = "notification"
    sender_type: str = "admin"
    sender_name: str = "ScoutMePlay Team"
    subject: str
    body: str
    target: str = "all"
    target_email: Optional[str] = None
    link: Optional[str] = None


class ReadAllPayload(BaseModel):
    kind: Optional[str] = None


class ReplyPayload(BaseModel):
    body: str


class OpportunityIn(BaseModel):
    title: str
    club_name: Optional[str] = ""
    age_band: Optional[str] = ""
    location: Optional[str] = ""
    deadline: Optional[str] = None
    cta_url: Optional[str] = None
    is_new: bool = True
    active: bool = True


class OpportunityUpdate(BaseModel):
    title: Optional[str] = None
    club_name: Optional[str] = None
    age_band: Optional[str] = None
    location: Optional[str] = None
    deadline: Optional[str] = None
    cta_url: Optional[str] = None
    is_new: Optional[bool] = None
    active: Optional[bool] = None


def build_dashboard_hub_router(db, user_dep, admin_dep, email_sender=None, email_enabled=None) -> APIRouter:
    router = APIRouter(tags=["dashboard-hub"])

    _site = (os.environ.get("SITE_PUBLIC_URL") or os.environ.get("FRONTEND_URL") or "https://scoutmeplay.com").rstrip("/")

    def _active_tier(user: dict) -> Optional[str]:
        sub = (user or {}).get("subscription") or {}
        if sub.get("status") in ("active", "trialing", "past_due"):
            return sub.get("tier")
        return None

    async def _premium_access(user: dict) -> bool:
        if user.get("role") in ("admin", "scout"):
            return True
        if _active_tier(user):
            return True
        pp = user.get("progress_pass") or {}
        try:
            if int(pp.get("credits_remaining") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
        n = await db.reports.count_documents({
            "user_id": user["id"],
            "$or": [{"is_paid": True}, {"manually_unlocked": True}],
        })
        return n > 0

    def _visible_to(user: dict, has_premium: bool, tier: Optional[str], m: dict) -> bool:
        if m.get("target_email"):
            return (user.get("email") or "").lower() == m["target_email"].lower()
        t = m.get("target") or "all"
        if t == "all":
            return True
        if t == "free":
            return not has_premium
        if t == "premium":
            return has_premium and tier != "vip"
        if t == "vip":
            return tier == "vip"
        return False

    async def _visible_messages(user: dict):
        has_premium = await _premium_access(user)
        tier = _active_tier(user)
        docs = await db.dashboard_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        visible, locked = [], 0
        for m in docs:
            if not _visible_to(user, has_premium, tier, m):
                continue
            if m.get("sender_type") in EXTERNAL_SENDERS and not has_premium:
                locked += 1
                continue
            visible.append(m)
        return has_premium, visible, locked

    # ── Community numbers ─────────────────────────────────────────────
    async def _live_player_counts():
        total = await db.users.count_documents({"discoverable": True})
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        wk = await db.users.count_documents(
            {"discoverable": True, "discoverable_updated_at": {"$gte": week_ago}}
        )
        return total, wk

    @router.get("/dashboard/community")
    async def get_community(user=Depends(user_dep)):
        doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
        data = {**COMMUNITY_DEFAULTS, **(doc.get("value") or {})}
        if data.get("use_live_players"):
            live, live_wk = await _live_player_counts()
            data["players_in_library"] = live
            data["players_wk"] = live_wk
        return data

    @router.get("/admin/dashboard/community")
    async def admin_get_community(admin=Depends(admin_dep)):
        doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
        data = {**COMMUNITY_DEFAULTS, **(doc.get("value") or {})}
        live, live_wk = await _live_player_counts()
        data["live_players_in_library"] = live
        data["live_players_wk"] = live_wk
        return data

    @router.put("/admin/dashboard/community")
    async def admin_put_community(payload: CommunityUpdate, admin=Depends(admin_dep)):
        doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
        current = {**COMMUNITY_DEFAULTS, **(doc.get("value") or {})}
        updates = {k: v for k, v in payload.dict().items() if v is not None}
        current.update(updates)
        await db.settings.update_one(
            {"key": "dashboard_community"},
            {"$set": {"value": current, "updated_at": _now_iso()}},
            upsert=True,
        )
        live, live_wk = await _live_player_counts()
        return {**current, "live_players_in_library": live, "live_players_wk": live_wk}

    # ── Performance (latest unlocked report scores) ───────────────────
    @router.get("/dashboard/performance")
    async def get_performance(user=Depends(user_dep)):
        doc = await db.reports.find_one(
            {
                "user_id": user["id"],
                "$or": [{"is_paid": True}, {"manually_unlocked": True}],
                "full_report.scores": {"$exists": True},
            },
            {"_id": 0, "id": 1, "created_at": 1, "player_details": 1, "full_report.scores": 1},
            sort=[("created_at", -1)],
        )
        if not doc:
            return {"has_report": False}
        sc = (doc.get("full_report") or {}).get("scores") or {}
        pillars = {k: sc.get(k) for k in ("technical", "tactical", "physical", "mentality")}
        overall = sc.get("overall_development")
        vals = [v for v in pillars.values() if isinstance(v, (int, float))]
        if overall is None and vals:
            overall = round(sum(vals) / len(vals), 1)
        pd = doc.get("player_details") or {}
        return {
            "has_report": True,
            "report_id": doc["id"],
            "player_name": pd.get("player_name"),
            "created_at": doc.get("created_at"),
            "overall": overall,
            "scores": pillars,
        }

    # ── Inbox (user) ──────────────────────────────────────────────────
    @router.get("/dashboard/inbox")
    async def get_inbox(user=Depends(user_dep)):
        has_premium, visible, locked = await _visible_messages(user)
        read_ids = set()
        async for r in db.dashboard_message_reads.find(
            {"user_id": user["id"]}, {"_id": 0, "message_id": 1}
        ):
            read_ids.add(r.get("message_id"))
        notifications, messages = [], []
        for m in visible:
            item = {**m, "read": m["id"] in read_ids}
            (messages if m.get("kind") == "message" else notifications).append(item)
        msg_ids = [m["id"] for m in messages]
        if msg_ids:
            replies_by_msg = {}
            async for r in db.dashboard_message_replies.find(
                {"message_id": {"$in": msg_ids}, "user_id": user["id"]}, {"_id": 0}
            ).sort("created_at", 1):
                replies_by_msg.setdefault(r["message_id"], []).append(r)
            for m in messages:
                m["replies"] = replies_by_msg.get(m["id"], [])
        return {
            "premium_access": has_premium,
            "notifications": notifications,
            "messages": messages,
            "locked_message_count": locked,
            "unread_notifications": sum(1 for m in notifications if not m["read"]),
            "unread_messages": sum(1 for m in messages if not m["read"]),
        }

    @router.post("/dashboard/inbox/{message_id}/read")
    async def mark_read(message_id: str, user=Depends(user_dep)):
        msg = await db.dashboard_messages.find_one({"id": message_id}, {"_id": 0})
        if not msg:
            raise HTTPException(404, "Message not found")
        await db.dashboard_message_reads.update_one(
            {"user_id": user["id"], "message_id": message_id},
            {"$set": {"read_at": _now_iso()}},
            upsert=True,
        )
        return {"ok": True}

    @router.post("/dashboard/inbox/read-all")
    async def mark_all_read(payload: ReadAllPayload, user=Depends(user_dep)):
        _, visible, _ = await _visible_messages(user)
        ids = [m["id"] for m in visible if not payload.kind or m.get("kind") == payload.kind]
        for mid in ids:
            await db.dashboard_message_reads.update_one(
                {"user_id": user["id"], "message_id": mid},
                {"$set": {"read_at": _now_iso()}},
                upsert=True,
            )
        return {"ok": True, "marked": len(ids)}

    @router.get("/dashboard/inbox/badges")
    async def inbox_badges(user=Depends(user_dep)):
        has_premium, visible, locked = await _visible_messages(user)
        read_ids = set()
        async for r in db.dashboard_message_reads.find(
            {"user_id": user["id"]}, {"_id": 0, "message_id": 1}
        ):
            read_ids.add(r.get("message_id"))
        un_n = sum(1 for m in visible if m.get("kind") != "message" and m["id"] not in read_ids)
        un_m = sum(1 for m in visible if m.get("kind") == "message" and m["id"] not in read_ids)
        return {
            "premium_access": has_premium,
            "unread_notifications": un_n,
            "unread_messages": un_m,
            "locked_messages": locked,
            "total": un_n + un_m + locked,
        }

    @router.post("/dashboard/inbox/{message_id}/reply")
    async def reply_to_message(message_id: str, payload: ReplyPayload, user=Depends(user_dep)):
        body = (payload.body or "").strip()
        if not body:
            raise HTTPException(400, "body is required")
        if len(body) > 2000:
            raise HTTPException(400, "Reply is too long (max 2000 characters)")
        msg = await db.dashboard_messages.find_one({"id": message_id}, {"_id": 0})
        if not msg:
            raise HTTPException(404, "Message not found")
        if msg.get("kind") != "message":
            raise HTTPException(400, "You can only reply to messages")
        has_premium = await _premium_access(user)
        tier = _active_tier(user)
        if not _visible_to(user, has_premium, tier, msg):
            raise HTTPException(403, "This message is not in your inbox")
        if msg.get("sender_type") in EXTERNAL_SENDERS and not has_premium:
            raise HTTPException(403, "Replying to scouts, agents and clubs is a Premium feature")
        reply = {
            "id": str(uuid.uuid4()),
            "message_id": message_id,
            "user_id": user["id"],
            "user_email": (user.get("email") or "").lower(),
            "user_name": user.get("full_name") or user.get("email"),
            "body": body,
            "created_at": _now_iso(),
        }
        await db.dashboard_message_replies.insert_one({**reply})
        await db.dashboard_message_reads.update_one(
            {"user_id": user["id"], "message_id": message_id},
            {"$set": {"read_at": _now_iso()}},
            upsert=True,
        )
        return reply

    # ── Profile views (scout database detail opens) ───────────────────
    @router.get("/dashboard/profile-views")
    async def profile_views(user=Depends(user_dep)):
        has_premium = await _premium_access(user)
        if not has_premium:
            return {"locked": True, "total": 0, "this_week": 0}
        total = await db.profile_view_events.count_documents({"player_user_id": user["id"]})
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        this_week = await db.profile_view_events.count_documents(
            {"player_user_id": user["id"], "ts": {"$gte": week_ago}}
        )
        return {
            "locked": False,
            "total": total,
            "this_week": this_week,
            "discoverable": bool(user.get("discoverable")),
        }

    # ── Email alert: external message → notify eligible members ──────
    async def _alert_recipient_emails(msg: dict):
        if msg.get("target_email"):
            return [msg["target_email"]]
        t = msg.get("target") or "all"
        if t == "free":
            return []  # free users can't see external messages — never email them
        emails = set()
        sub_q = {"subscription.status": {"$in": ["active", "trialing", "past_due"]}}
        if t == "vip":
            sub_q["subscription.tier"] = "vip"
        elif t == "premium":
            sub_q["subscription.tier"] = {"$ne": "vip"}
        async for u in db.users.find(sub_q, {"_id": 0, "email": 1}).limit(500):
            if u.get("email"):
                emails.add(u["email"].lower())
        if t in ("all", "premium"):
            uids = await db.reports.distinct(
                "user_id", {"$or": [{"is_paid": True}, {"manually_unlocked": True}]}
            )
            if uids:
                async for u in db.users.find({"id": {"$in": uids[:500]}}, {"_id": 0, "email": 1}):
                    if u.get("email"):
                        emails.add(u["email"].lower())
        return list(emails)[:500]

    async def _send_message_email_alert(msg: dict):
        try:
            recipients = await _alert_recipient_emails(msg)
            if not recipients:
                return
            sender_name = msg.get("sender_name") or "a scout"
            sender_type = msg.get("sender_type") or "scout"
            subject = f"New message from {sender_name} on ScoutMePlay"
            dash_url = f"{_site}/dashboard?scroll=dashboard-inbox-anchor"
            html = f"""
            <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;background:#F6F4EE;padding:24px;">
              <div style="background:#0A0F0D;padding:18px 24px;border-radius:14px 14px 0 0;">
                <span style="color:#fff;font-weight:900;font-size:20px;letter-spacing:2px;">SCOUT<span style="background:#CCFF00;color:#0A0F0D;padding:0 4px;">ME</span>PLAY</span>
              </div>
              <div style="background:#fff;padding:28px 24px;border-radius:0 0 14px 14px;">
                <p style="font-size:15px;color:#1a1f1a;margin:0 0 6px;"><strong>A {sender_type} just messaged you.</strong></p>
                <p style="font-size:14px;color:#4a554a;margin:0 0 18px;">{sender_name} sent you a message: &ldquo;{(msg.get('subject') or '')[:120]}&rdquo;</p>
                <a href="{dash_url}" style="display:inline-block;background:#1F4F2F;color:#fff;text-decoration:none;font-weight:800;text-transform:uppercase;letter-spacing:1px;font-size:13px;padding:12px 26px;border-radius:999px;">Read &amp; reply on your dashboard</a>
                <p style="font-size:12px;color:#8a948a;margin:20px 0 0;">You receive this because you're a ScoutMePlay member with inbox access.</p>
              </div>
            </div>"""
            text = f"{sender_name} ({sender_type}) sent you a message on ScoutMePlay: {msg.get('subject')}. Read & reply: {dash_url}"
            sent = 0
            for email in recipients:
                try:
                    ok = await email_sender(email, subject, html, text)
                    if ok:
                        sent += 1
                except Exception:
                    logger.exception(f"message email alert failed for {email}")
            logger.info(f"[dashboard-hub] message alert emails sent: {sent}/{len(recipients)}")
        except Exception:
            logger.exception("message email alert task failed")

    # ── Admin messages ────────────────────────────────────────────────
    @router.post("/admin/dashboard/messages")
    async def admin_compose(payload: ComposeMessage, admin=Depends(admin_dep)):
        if payload.kind not in VALID_KINDS:
            raise HTTPException(400, "Invalid kind")
        if payload.sender_type not in VALID_SENDERS:
            raise HTTPException(400, "Invalid sender_type")
        if payload.target not in VALID_TARGETS:
            raise HTTPException(400, "Invalid target")
        subject = (payload.subject or "").strip()
        body = (payload.body or "").strip()
        if not subject or not body:
            raise HTTPException(400, "subject and body are required")
        target_email = (payload.target_email or "").strip().lower() or None
        if target_email:
            u = await db.users.find_one({"email": target_email}, {"_id": 0, "id": 1})
            if not u:
                raise HTTPException(404, f"No user with email {target_email}")
        doc = {
            "id": str(uuid.uuid4()),
            "kind": payload.kind,
            "sender_type": payload.sender_type,
            "sender_name": (payload.sender_name or "ScoutMePlay Team").strip(),
            "subject": subject,
            "body": body,
            "target": payload.target,
            "target_email": target_email,
            "link": (payload.link or "").strip() or None,
            "created_at": _now_iso(),
            "created_by": admin.get("email"),
        }
        await db.dashboard_messages.insert_one({**doc})
        if (
            payload.kind == "message"
            and payload.sender_type in EXTERNAL_SENDERS
            and email_sender is not None
            and (email_enabled is None or email_enabled())
        ):
            asyncio.create_task(_send_message_email_alert(doc))
        return doc

    @router.get("/admin/dashboard/messages")
    async def admin_list_messages(admin=Depends(admin_dep)):
        msgs = await db.dashboard_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        counts = {}
        async for row in db.dashboard_message_reads.aggregate(
            [{"$group": {"_id": "$message_id", "n": {"$sum": 1}}}]
        ):
            counts[row["_id"]] = row["n"]
        rcounts = {}
        async for row in db.dashboard_message_replies.aggregate(
            [{"$group": {"_id": "$message_id", "n": {"$sum": 1}}}]
        ):
            rcounts[row["_id"]] = row["n"]
        for m in msgs:
            m["read_count"] = counts.get(m["id"], 0)
            m["reply_count"] = rcounts.get(m["id"], 0)
        return {"messages": msgs}

    @router.get("/admin/dashboard/messages/{message_id}/replies")
    async def admin_message_replies(message_id: str, admin=Depends(admin_dep)):
        replies = await db.dashboard_message_replies.find(
            {"message_id": message_id}, {"_id": 0}
        ).sort("created_at", 1).to_list(500)
        return {"replies": replies}

    @router.delete("/admin/dashboard/messages/{message_id}")
    async def admin_delete_message(message_id: str, admin=Depends(admin_dep)):
        res = await db.dashboard_messages.delete_one({"id": message_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "Message not found")
        await db.dashboard_message_reads.delete_many({"message_id": message_id})
        await db.dashboard_message_replies.delete_many({"message_id": message_id})
        return {"ok": True}

    # ── Opportunities (user) ──────────────────────────────────────────
    @router.get("/dashboard/opportunities")
    async def get_opportunities(user=Depends(user_dep)):
        has_premium = await _premium_access(user)
        n_active = await db.dashboard_opportunities.count_documents({"active": True})
        if not has_premium:
            return {"locked": True, "items": [], "count": n_active}
        items = await db.dashboard_opportunities.find(
            {"active": True}, {"_id": 0}
        ).sort("created_at", -1).to_list(50)
        my_interest = set()
        async for r in db.dashboard_opportunity_interest.find(
            {"user_id": user["id"]}, {"_id": 0, "opportunity_id": 1}
        ):
            my_interest.add(r.get("opportunity_id"))
        for o in items:
            o["interested"] = o["id"] in my_interest
        return {"locked": False, "items": items, "count": n_active}

    @router.post("/dashboard/opportunities/{opp_id}/interest")
    async def opportunity_interest(opp_id: str, user=Depends(user_dep)):
        if not await _premium_access(user):
            raise HTTPException(403, "Trials & opportunities are a Premium feature")
        opp = await db.dashboard_opportunities.find_one({"id": opp_id, "active": True}, {"_id": 0})
        if not opp:
            raise HTTPException(404, "Opportunity not found")
        await db.dashboard_opportunity_interest.update_one(
            {"user_id": user["id"], "opportunity_id": opp_id},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "opportunity_id": opp_id,
                "user_email": (user.get("email") or "").lower(),
                "user_name": user.get("full_name") or user.get("email"),
                "created_at": _now_iso(),
            }},
            upsert=True,
        )
        return {"ok": True, "interested": True}

    @router.delete("/dashboard/opportunities/{opp_id}/interest")
    async def opportunity_interest_withdraw(opp_id: str, user=Depends(user_dep)):
        await db.dashboard_opportunity_interest.delete_one(
            {"user_id": user["id"], "opportunity_id": opp_id}
        )
        return {"ok": True, "interested": False}

    # ── Admin opportunities CRUD ──────────────────────────────────────
    @router.get("/admin/dashboard/opportunities")
    async def admin_list_opportunities(admin=Depends(admin_dep)):
        items = await db.dashboard_opportunities.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        icounts = {}
        async for row in db.dashboard_opportunity_interest.aggregate(
            [{"$group": {"_id": "$opportunity_id", "n": {"$sum": 1}}}]
        ):
            icounts[row["_id"]] = row["n"]
        for o in items:
            o["interest_count"] = icounts.get(o["id"], 0)
        return {"items": items}

    @router.get("/admin/dashboard/opportunities/{opp_id}/interest")
    async def admin_opportunity_applicants(opp_id: str, admin=Depends(admin_dep)):
        applicants = await db.dashboard_opportunity_interest.find(
            {"opportunity_id": opp_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        return {"applicants": applicants}

    @router.post("/admin/dashboard/opportunities")
    async def admin_create_opportunity(payload: OpportunityIn, admin=Depends(admin_dep)):
        title = (payload.title or "").strip()
        if not title:
            raise HTTPException(400, "title is required")
        doc = {
            "id": str(uuid.uuid4()),
            "title": title,
            "club_name": (payload.club_name or "").strip(),
            "age_band": (payload.age_band or "").strip(),
            "location": (payload.location or "").strip(),
            "deadline": (payload.deadline or "").strip() or None,
            "cta_url": (payload.cta_url or "").strip() or None,
            "is_new": bool(payload.is_new),
            "active": bool(payload.active),
            "created_at": _now_iso(),
        }
        await db.dashboard_opportunities.insert_one({**doc})
        return doc

    @router.put("/admin/dashboard/opportunities/{opp_id}")
    async def admin_update_opportunity(opp_id: str, payload: OpportunityUpdate, admin=Depends(admin_dep)):
        updates = {k: v for k, v in payload.dict().items() if v is not None}
        if not updates:
            raise HTTPException(400, "No fields to update")
        res = await db.dashboard_opportunities.update_one({"id": opp_id}, {"$set": updates})
        if res.matched_count == 0:
            raise HTTPException(404, "Opportunity not found")
        doc = await db.dashboard_opportunities.find_one({"id": opp_id}, {"_id": 0})
        return doc

    @router.delete("/admin/dashboard/opportunities/{opp_id}")
    async def admin_delete_opportunity(opp_id: str, admin=Depends(admin_dep)):
        res = await db.dashboard_opportunities.delete_one({"id": opp_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "Opportunity not found")
        await db.dashboard_opportunity_interest.delete_many({"opportunity_id": opp_id})
        return {"ok": True}

    return router
