import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { Bell, Mail, Lock, ShieldCheck, Briefcase, Search, CheckCheck, Send, CornerDownRight } from "lucide-react";

const timeAgo = (iso) => {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const SENDER_ICON = {
  admin: { Icon: ShieldCheck, cls: "bg-forest/10 text-forest" },
  scout: { Icon: Search, cls: "bg-blue-100 text-blue-600" },
  agent: { Icon: Briefcase, cls: "bg-amber-100 text-amber-600" },
  club: { Icon: ShieldCheck, cls: "bg-purple-100 text-purple-600" },
};

const FAKE_LOCKED_ROWS = [
  { name: "Agent Said M.", text: "Hi! We are interested in seeing more of your games." },
  { name: "Scout Fatima A.", text: "Great performance! Keep up the amazing work." },
  { name: "Agent Ibrahim K.", text: "We have upcoming trials next month." },
];

/* Notifications + Messages panels. Free users see admin notifications but a
 * locked FOMO state for external (scout/agent/club) messages. */
export default function InboxPanels({ onUpgrade }) {
  const [inbox, setInbox] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [replyDrafts, setReplyDrafts] = useState({});
  const [sendingReply, setSendingReply] = useState(false);

  const fetchInbox = () => {
    api.get("/dashboard/inbox").then(({ data }) => setInbox(data)).catch(() => {});
  };
  useEffect(fetchInbox, []);

  if (!inbox) return null;

  const markRead = async (m) => {
    setOpenId((v) => (v === m.id ? null : m.id));
    if (m.read) return;
    try {
      await api.post(`/dashboard/inbox/${m.id}/read`);
      setInbox((prev) => ({
        ...prev,
        notifications: prev.notifications.map((x) => (x.id === m.id ? { ...x, read: true } : x)),
        messages: prev.messages.map((x) => (x.id === m.id ? { ...x, read: true } : x)),
        unread_notifications: prev.notifications.filter((x) => x.id !== m.id && !x.read && prev.notifications.some((n) => n.id === x.id)).length,
        unread_messages: prev.messages.filter((x) => x.id !== m.id && !x.read).length,
      }));
    } catch { /* non-critical */ }
  };

  const markAll = async (kind) => {
    try {
      await api.post("/dashboard/inbox/read-all", { kind });
      fetchInbox();
    } catch { /* non-critical */ }
  };

  const sendReply = async (m) => {
    const text = (replyDrafts[m.id] || "").trim();
    if (!text || sendingReply) return;
    setSendingReply(true);
    try {
      const { data } = await api.post(`/dashboard/inbox/${m.id}/reply`, { body: text });
      setInbox((prev) => ({
        ...prev,
        messages: prev.messages.map((x) =>
          x.id === m.id ? { ...x, read: true, replies: [...(x.replies || []), data] } : x
        ),
      }));
      setReplyDrafts((d) => ({ ...d, [m.id]: "" }));
      toast.success("Reply sent");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send reply");
    } finally {
      setSendingReply(false);
    }
  };

  const { notifications, messages, premium_access: premium, locked_message_count: lockedCount } = inbox;

  const Row = ({ m, canReply = false }) => {
    const meta = SENDER_ICON[m.sender_type] || SENDER_ICON.admin;
    const { Icon } = meta;
    const internalLink = m.link && m.link.startsWith("/");
    return (
      <div>
        <button
          type="button"
          onClick={() => markRead(m)}
          data-testid={`inbox-row-${m.id}`}
          className="w-full text-left flex gap-3 px-5 py-3 hover:bg-cream-soft/60 transition-colors items-start"
        >
          <span className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${meta.cls}`}>
            <Icon className="w-[18px] h-[18px]" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-black text-ink truncate">{m.subject}</span>
            <span className={`block text-[12px] text-ink/60 mt-0.5 ${openId === m.id ? "" : "truncate"}`}>{m.body}</span>
            {m.sender_type !== "admin" && (
              <span className="block text-[10px] uppercase tracking-[0.14em] font-bold text-ink/40 mt-1">
                {m.sender_name} · {m.sender_type}
              </span>
            )}
            {openId === m.id && m.link && (
              internalLink ? (
                <Link to={m.link} className="inline-block mt-1.5 text-[11px] font-bold text-forest underline">
                  Open →
                </Link>
              ) : (
                <a href={m.link} target="_blank" rel="noreferrer" className="inline-block mt-1.5 text-[11px] font-bold text-forest underline">
                  Open link →
                </a>
              )
            )}
          </span>
          <span className="shrink-0 flex flex-col items-end gap-1.5">
            <span className="text-[10px] text-ink/40 whitespace-nowrap">{timeAgo(m.created_at)}</span>
            {!m.read && <span className="w-2.5 h-2.5 rounded-full bg-forest" data-testid={`inbox-unread-dot-${m.id}`} />}
          </span>
        </button>
        {openId === m.id && canReply && (
          <div className="px-5 pb-4 sm:pl-[72px]" data-testid={`reply-thread-${m.id}`}>
            {(m.replies || []).map((r) => (
              <div key={r.id} className="flex gap-2 items-start mb-2" data-testid={`reply-${r.id}`}>
                <CornerDownRight className="w-3.5 h-3.5 text-forest mt-1 shrink-0" />
                <div className="bg-forest/5 border border-forest/15 rounded-xl px-3 py-2 text-[12px] text-ink/75 flex-1">
                  {r.body}
                  <span className="block text-[10px] text-ink/40 mt-1">You · {timeAgo(r.created_at)}</span>
                </div>
              </div>
            ))}
            <div className="flex gap-2 items-end">
              <textarea
                value={replyDrafts[m.id] || ""}
                onChange={(e) => setReplyDrafts((d) => ({ ...d, [m.id]: e.target.value }))}
                rows={2}
                maxLength={2000}
                placeholder="Write a reply…"
                data-testid={`reply-input-${m.id}`}
                className="flex-1 border border-gray-border rounded-xl px-3 py-2 text-[13px] focus:outline-none focus:border-forest bg-white resize-none"
              />
              <button
                type="button"
                onClick={() => sendReply(m)}
                disabled={sendingReply || !(replyDrafts[m.id] || "").trim()}
                data-testid={`reply-send-${m.id}`}
                className="bg-forest hover:bg-forest-pop text-white p-2.5 rounded-xl transition-colors disabled:opacity-40"
                aria-label="Send reply"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="mt-8 grid lg:grid-cols-2 gap-4" data-testid="inbox-panels">
      {/* Notifications */}
      <div className="bg-cream-card border border-gray-border rounded-3xl overflow-hidden flex flex-col" data-testid="notifications-panel">
        <div className="flex items-center justify-between px-5 pt-5 pb-2">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-forest" />
            <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Notifications</h3>
            {inbox.unread_notifications > 0 && (
              <span className="bg-forest text-white text-[10px] font-black min-w-[18px] h-[18px] rounded-full flex items-center justify-center px-1" data-testid="notifications-unread-badge">
                {inbox.unread_notifications}
              </span>
            )}
          </div>
          {notifications.length > 0 && (
            <button type="button" onClick={() => markAll("notification")} data-testid="notifications-mark-all-btn" className="text-[11px] font-bold text-forest inline-flex items-center gap-1 hover:underline">
              <CheckCheck className="w-3.5 h-3.5" /> Mark all read
            </button>
          )}
        </div>
        {notifications.length === 0 ? (
          <p className="px-5 py-6 text-[13px] text-ink/50" data-testid="notifications-empty">
            No notifications yet — upload a video and your report updates will land here.
          </p>
        ) : (
          <div className="pb-3">{notifications.slice(0, 6).map((m) => <Row key={m.id} m={m} />)}</div>
        )}
      </div>

      {/* Messages */}
      <div className="bg-cream-card border border-gray-border rounded-3xl overflow-hidden flex flex-col relative" data-testid="messages-panel">
        <div className="flex items-center justify-between px-5 pt-5 pb-2">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-forest" />
            <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Messages</h3>
            {inbox.unread_messages > 0 && (
              <span className="bg-forest text-white text-[10px] font-black min-w-[18px] h-[18px] rounded-full flex items-center justify-center px-1" data-testid="messages-unread-badge">
                {inbox.unread_messages}
              </span>
            )}
          </div>
          {!premium && (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-forest">
              <Lock className="w-3 h-3" /> Premium
            </span>
          )}
        </div>

        {premium ? (
          messages.length === 0 ? (
            <p className="px-5 py-6 text-[13px] text-ink/50" data-testid="messages-empty">
              No messages yet — scouts, agents and clubs reach players right here.
            </p>
          ) : (
            <div className="pb-3">{messages.slice(0, 6).map((m) => <Row key={m.id} m={m} canReply />)}</div>
          )
        ) : (
          <div data-testid="messages-locked">
            {messages.length > 0 && (
              <div className="pb-1">{messages.slice(0, 4).map((m) => <Row key={m.id} m={m} canReply />)}</div>
            )}
            <div className="relative">
              <div className="blur-[4px] opacity-50 select-none pointer-events-none pb-3" aria-hidden>
              {FAKE_LOCKED_ROWS.map((f) => (
                <div key={f.name} className="flex gap-3 px-5 py-3 items-start">
                  <span className="w-10 h-10 rounded-full bg-forest/15 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-black text-ink">{f.name}</span>
                    <span className="block text-[12px] text-ink/60 mt-0.5 truncate">{f.text}</span>
                  </span>
                </div>
              ))}
            </div>
            <div className="absolute inset-0 flex flex-col items-center justify-end text-center px-6 pb-5" style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.94) 62%)" }}>
              <span className="w-11 h-11 rounded-2xl bg-forest/10 text-forest flex items-center justify-center mb-2">
                <Lock className="w-5 h-5" />
              </span>
              <b className="text-sm text-ink">Messages from agents, scouts &amp; clubs</b>
              <p className="text-[12px] text-ink/55 mt-1 max-w-[300px]">
                Premium members receive and answer messages directly here.
                {lockedCount > 0 && (
                  <span className="block mt-1 font-black text-forest" data-testid="locked-message-count">
                    {lockedCount} message{lockedCount === 1 ? "" : "s"} already waiting for you.
                  </span>
                )}
              </p>
              <button
                type="button"
                onClick={onUpgrade}
                data-testid="messages-upgrade-btn"
                className="mt-3 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 rounded-full transition-colors"
              >
                Upgrade to Premium
              </button>
            </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
