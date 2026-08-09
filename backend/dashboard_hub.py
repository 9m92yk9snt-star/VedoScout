"""Dashboard Hub — admin-controlled community numbers, inbox
(messages/notifications composed by admin), and Trials & Opportunities
for the player dashboard. Premium gating: free users never receive
scout/agent/club message content — only a locked count for the UI."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


COMMUNITY_DEFAULTS = {
    "enabled": True,
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


def build_dashboard_hub_router(db, user_dep, admin_dep) -> APIRouter:
    router = APIRouter(tags=["dashboard-hub"])

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
    @router.get("/dashboard/community")
    async def get_community(user=Depends(user_dep)):
        doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
        return {**COMMUNITY_DEFAULTS, **(doc.get("value") or {})}

    @router.get("/admin/dashboard/community")
    async def admin_get_community(admin=Depends(admin_dep)):
        doc = await db.settings.find_one({"key": "dashboard_community"}, {"_id": 0}) or {}
        return {**COMMUNITY_DEFAULTS, **(doc.get("value") or {})}

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
        return current

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
        return doc

    @router.get("/admin/dashboard/messages")
    async def admin_list_messages(admin=Depends(admin_dep)):
        msgs = await db.dashboard_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        counts = {}
        async for row in db.dashboard_message_reads.aggregate(
            [{"$group": {"_id": "$message_id", "n": {"$sum": 1}}}]
        ):
            counts[row["_id"]] = row["n"]
        for m in msgs:
            m["read_count"] = counts.get(m["id"], 0)
        return {"messages": msgs}

    @router.delete("/admin/dashboard/messages/{message_id}")
    async def admin_delete_message(message_id: str, admin=Depends(admin_dep)):
        res = await db.dashboard_messages.delete_one({"id": message_id})
        if res.deleted_count == 0:
            raise HTTPException(404, "Message not found")
        await db.dashboard_message_reads.delete_many({"message_id": message_id})
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
        return {"locked": False, "items": items, "count": n_active}

    # ── Admin opportunities CRUD ──────────────────────────────────────
    @router.get("/admin/dashboard/opportunities")
    async def admin_list_opportunities(admin=Depends(admin_dep)):
        items = await db.dashboard_opportunities.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
        return {"items": items}

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
        return {"ok": True}

    return router
