import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Loader2, Send, Clock, CheckCircle2, MessageSquare, ChevronDown, ChevronUp,
} from "lucide-react";
import api, { ASSET_BASE } from "@/lib/api";

function formatRelative(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export default function ScoutQueue() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [drafts, setDrafts] = useState({});
  const [sending, setSending] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/agent-queue");
      setItems(data);
    } catch (err) {
      toast.error("Failed to load scout queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const setDraft = (id, key, val) =>
    setDrafts((d) => ({ ...d, [id]: { ...(d[id] || {}), [key]: val } }));

  const deliverReview = async (reportId) => {
    const d = drafts[reportId] || {};
    const text = (d.review_text || "").trim();
    if (text.length < 10) {
      toast.error("Review must be at least 10 characters");
      return;
    }
    setSending((s) => ({ ...s, [reportId]: "deliver" }));
    try {
      await api.put(`/admin/reports/${reportId}/agent-review`, {
        review_text: text,
        agent_name: (d.agent_name || "Elite Scout Team").trim(),
      });
      toast.success("Review delivered to user");
      setDrafts((dd) => ({ ...dd, [reportId]: { ...(dd[reportId] || {}), review_text: "" } }));
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not deliver review");
    } finally {
      setSending((s) => ({ ...s, [reportId]: null }));
    }
  };

  const sendMessage = async (reportId) => {
    const d = drafts[reportId] || {};
    const text = (d.reply || "").trim();
    if (!text) return;
    setSending((s) => ({ ...s, [reportId]: "reply" }));
    try {
      await api.post(`/admin/reports/${reportId}/agent-messages`, { text });
      setDrafts((dd) => ({ ...dd, [reportId]: { ...(dd[reportId] || {}), reply: "" } }));
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not send message");
    } finally {
      setSending((s) => ({ ...s, [reportId]: null }));
    }
  };

  if (loading) {
    return (
      <div className="text-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-surface border border-gray-border p-12 text-center">
        <p className="text-ink/55 uppercase tracking-widest text-sm font-bold">No paid reports yet — queue is empty.</p>
      </div>
    );
  }

  const pendingCount = items.filter((it) => it.agent_review?.status === "pending").length;
  const deliveredCount = items.length - pendingCount;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-px bg-cream-soft/40 border border-gray-border">
        <div className="bg-deepnavy p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-3.5 h-3.5 text-volt" />
            <span className="text-[10px] uppercase tracking-widest font-bold text-ink/50">Pending reviews</span>
          </div>
          <div className="font-barlow font-black text-3xl text-volt">{pendingCount}</div>
        </div>
        <div className="bg-deepnavy p-4">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-volt" />
            <span className="text-[10px] uppercase tracking-widest font-bold text-ink/50">Delivered</span>
          </div>
          <div className="font-barlow font-black text-3xl text-ink">{deliveredCount}</div>
        </div>
      </div>

      <div className="space-y-3">
        {items.map((it) => {
          const r = it.agent_review;
          const isPending = r.status === "pending";
          const isOpen = !!expanded[it.report_id];
          const draft = drafts[it.report_id] || {};
          const send = sending[it.report_id];

          return (
            <div
              key={it.report_id}
              data-testid={`scout-queue-item-${it.report_id}`}
              className={`border ${isPending ? "border-volt/30" : "border-gray-border"} bg-surface`}
            >
              {/* Card header */}
              <button
                type="button"
                onClick={() => setExpanded((e) => ({ ...e, [it.report_id]: !e[it.report_id] }))}
                className="w-full flex items-center gap-4 p-4 hover:bg-cream-soft transition-colors text-left"
              >
                {it.poster_url ? (
                  <img
                    src={`${ASSET_BASE}${it.poster_url}`}
                    alt=""
                    className="w-16 h-10 object-cover border border-gray-border flex-shrink-0"
                  />
                ) : (
                  <div className="w-16 h-10 bg-deepnavy border border-gray-border flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-barlow font-black uppercase text-ink text-lg leading-tight truncate">
                    {it.player_name}
                  </div>
                  <div className="text-[11px] text-ink/55 truncate">
                    {it.player_position} · {it.user_email}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  {isPending ? (
                    <span className="bg-volt text-white text-[10px] uppercase tracking-widest font-black px-2 py-1 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 bg-deepnavy rounded-full animate-pulse" /> Pending
                    </span>
                  ) : (
                    <span className="border border-gray-border text-ink/70 text-[10px] uppercase tracking-widest font-bold px-2 py-1">
                      Delivered
                    </span>
                  )}
                  {r.messages?.length > 0 && (
                    <span className="flex items-center gap-1 text-[10px] uppercase tracking-widest font-bold text-volt">
                      <MessageSquare className="w-3 h-3" />
                      {r.messages.length}
                    </span>
                  )}
                  {isOpen ? <ChevronUp className="w-4 h-4 text-ink/50" /> : <ChevronDown className="w-4 h-4 text-ink/50" />}
                </div>
              </button>

              {/* Expanded content */}
              {isOpen && (
                <div className="border-t border-gray-border p-5 space-y-5">
                  {/* Video & marker preview */}
                  <div className="grid md:grid-cols-2 gap-3">
                    {it.video_url && (
                      <video
                        src={`${ASSET_BASE}${it.video_url}`}
                        poster={it.poster_url ? `${ASSET_BASE}${it.poster_url}` : undefined}
                        controls
                        playsInline
                        preload="metadata"
                        className="w-full aspect-video bg-black border border-gray-border"
                      />
                    )}
                    {it.marker_url && (
                      <div>
                        <div className="text-[10px] uppercase tracking-widest font-bold text-volt mb-1">
                          User-marked player
                        </div>
                        <img
                          src={`${ASSET_BASE}${it.marker_url}`}
                          alt="Marked player"
                          className="w-full aspect-video object-contain bg-black border border-gray-border"
                        />
                      </div>
                    )}
                  </div>

                  {/* PENDING — deliver form */}
                  {isPending && (
                    <div className="space-y-3">
                      <label className="text-[10px] uppercase tracking-widest font-bold text-volt block">
                        Your scout review (delivered to the user)
                      </label>
                      <input
                        type="text"
                        value={draft.agent_name || ""}
                        onChange={(e) => setDraft(it.report_id, "agent_name", e.target.value)}
                        placeholder="Your name (default: Elite Scout Team)"
                        data-testid={`scout-queue-agent-name-${it.report_id}`}
                        className="w-full bg-deepnavy border border-gray-border px-3 py-2 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                      />
                      <textarea
                        value={draft.review_text || ""}
                        onChange={(e) => setDraft(it.report_id, "review_text", e.target.value)}
                        rows={6}
                        placeholder="Write a personal, honest scout review for this player. Speak directly to them and their family."
                        data-testid={`scout-queue-review-text-${it.report_id}`}
                        className="w-full bg-deepnavy border border-gray-border px-3 py-2 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-none"
                      />
                      <button
                        type="button"
                        onClick={() => deliverReview(it.report_id)}
                        disabled={send === "deliver"}
                        data-testid={`scout-queue-deliver-${it.report_id}`}
                        className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 disabled:opacity-50 flex items-center gap-2 transition-colors"
                      >
                        {send === "deliver" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                        Deliver review
                      </button>
                    </div>
                  )}

                  {/* DELIVERED — show review + chat */}
                  {!isPending && (
                    <>
                      <div>
                        <div className="text-[10px] uppercase tracking-widest font-bold text-volt mb-2">
                          Your review (delivered {formatRelative(r.delivered_at)})
                        </div>
                        <div className="bg-cream-card/90 border-l-2 border-volt p-4">
                          <p className="text-ink text-sm leading-relaxed whitespace-pre-line">{r.review_text}</p>
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] uppercase tracking-widest font-bold text-volt mb-2">
                          Conversation ({r.messages?.length || 0})
                        </div>
                        <div className="space-y-2 max-h-72 overflow-y-auto bg-cream-soft p-3 border border-gray-border">
                          {(!r.messages || r.messages.length === 0) && (
                            <p className="text-xs text-ink/50 text-center py-4">No messages yet.</p>
                          )}
                          {r.messages?.map((m, i) => {
                            const isAgent = m.sender === "agent";
                            return (
                              <div key={i} className={`flex ${isAgent ? "justify-end" : "justify-start"}`}>
                                <div className={`max-w-[80%] px-3 py-2 text-xs ${isAgent ? "bg-volt text-white" : "bg-deepnavy border border-gray-border text-white"}`}>
                                  <div className={`text-[9px] uppercase tracking-widest font-bold mb-0.5 ${isAgent ? "text-ink/70" : "text-volt"}`}>
                                    {isAgent ? "You (scout)" : "User"} · {formatRelative(m.created_at)}
                                  </div>
                                  <div className="whitespace-pre-line">{m.text}</div>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <div className="mt-3 flex gap-2">
                          <textarea
                            value={draft.reply || ""}
                            onChange={(e) => setDraft(it.report_id, "reply", e.target.value)}
                            rows={2}
                            placeholder="Reply to the user..."
                            data-testid={`scout-queue-reply-${it.report_id}`}
                            className="flex-1 bg-deepnavy border border-gray-border px-3 py-2 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-none"
                          />
                          <button
                            type="button"
                            onClick={() => sendMessage(it.report_id)}
                            disabled={send === "reply" || !(draft.reply || "").trim()}
                            data-testid={`scout-queue-send-${it.report_id}`}
                            className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 disabled:opacity-40 flex items-center gap-2 transition-colors"
                          >
                            {send === "reply" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
