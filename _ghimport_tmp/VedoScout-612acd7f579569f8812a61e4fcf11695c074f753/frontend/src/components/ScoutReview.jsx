import React, { useEffect, useState, useRef } from "react";
import { toast } from "sonner";
import {
  ShieldCheck, MessageSquare, Send, Loader2, Clock, User as UserIcon, Sparkles,
} from "lucide-react";
import api from "@/lib/api";

function daysAgo(iso) {
  if (!iso) return 0;
  const ms = Date.now() - new Date(iso).getTime();
  return Math.max(0, ms / (1000 * 60 * 60 * 24));
}

function formatRelative(iso) {
  if (!iso) return "";
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

export default function ScoutReview({ reportId }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState("");
  const messagesEndRef = useRef(null);

  const fetchReview = async () => {
    try {
      const { data } = await api.get(`/reports/${reportId}/agent-review`);
      setReview(data);
    } catch (err) {
      // 402 / 403 just means not authorized — silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId]);

  // Auto-scroll messages to bottom
  useEffect(() => {
    if (messagesEndRef.current && review?.messages?.length) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [review?.messages?.length]);

  const handleSend = async (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      await api.post(`/reports/${reportId}/agent-messages`, { text });
      setDraft("");
      await fetchReview();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not send message");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-surface border border-gray-border p-6 md:p-8 flex items-center gap-3">
        <Loader2 className="w-5 h-5 animate-spin text-volt" />
        <span className="text-ink/65 text-sm uppercase tracking-widest font-bold">Loading scout review...</span>
      </div>
    );
  }
  if (!review) return null;

  /* =================== PENDING STATE =================== */
  if (review.status === "pending") {
    const daysSince = daysAgo(review.created_at);
    const daysLeft = Math.max(0, 5 - daysSince);
    const progressPct = Math.min(100, Math.max(0, (daysSince / 5) * 100));

    return (
      <div data-testid="scout-review-pending" className="bg-surface border border-volt/30 p-6 md:p-8 relative overflow-hidden">
        <div className="absolute -top-32 -right-32 w-64 h-64 bg-volt/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-volt" />
            <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Bonus included</span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95] text-ink">
            Your scout review is in progress
          </h3>
          <p className="mt-3 text-ink/70 text-sm md:text-base max-w-2xl leading-relaxed">
            On top of your player report, a real scout from our team is now reviewing your video personally. You'll receive their
            written feedback here within <span className="text-volt font-bold">5 days</span>, and you'll be able to chat
            with them directly to ask follow-up questions.
          </p>

          <div className="mt-7 grid sm:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border max-w-2xl">
            <div className="bg-deepnavy p-4">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="w-3.5 h-3.5 text-volt" />
                <span className="text-[10px] uppercase tracking-widest font-bold text-ink/50">Status</span>
              </div>
              <div className="font-barlow font-black text-volt text-xl uppercase">In review</div>
            </div>
            <div className="bg-deepnavy p-4">
              <div className="text-[10px] uppercase tracking-widest font-bold text-ink/50">Submitted</div>
              <div className="font-barlow font-black text-ink text-xl">
                {daysSince < 1 ? "Today" : `${Math.floor(daysSince)}d ago`}
              </div>
            </div>
            <div className="bg-deepnavy p-4">
              <div className="text-[10px] uppercase tracking-widest font-bold text-ink/50">Estimated arrival</div>
              <div className="font-barlow font-black text-ink text-xl">
                {daysLeft < 1 ? "Today / soon" : `≤ ${Math.ceil(daysLeft)} days`}
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mt-5 max-w-2xl">
            <div className="h-1.5 bg-cream-soft/40 overflow-hidden">
              <div className="h-full bg-volt transition-all duration-500" style={{ width: `${progressPct}%` }} />
            </div>
            <div className="flex justify-between mt-2 text-[10px] uppercase tracking-widest font-bold text-ink/50">
              <span>Day 0</span>
              <span>Day 5</span>
            </div>
          </div>

          <div className="mt-7 flex items-start gap-3 text-xs text-ink/65 max-w-2xl">
            <ShieldCheck className="w-4 h-4 text-volt flex-shrink-0 mt-0.5" />
            <p>
              The scout watches the video personally and writes a human review tailored to your player. Once delivered,
              you can ask questions and they'll reply in this thread.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* =================== DELIVERED STATE — review + chat =================== */
  return (
    <div data-testid="scout-review-delivered" className="bg-surface border border-gray-border">
      {/* Header strip */}
      <div className="bg-cream-card/90 border-b border-gray-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-volt flex items-center justify-center">
            <UserIcon className="w-4 h-4 text-ink" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-barlow font-black uppercase text-ink leading-tight">{review.agent_name || "Elite Scout Team"}</div>
            <div className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-volt rounded-full animate-pulse" /> Your dedicated scout
            </div>
          </div>
        </div>
        <span className="hidden sm:inline text-[10px] uppercase tracking-widest font-bold text-ink/50">
          Delivered {formatRelative(review.delivered_at)}
        </span>
      </div>

      {/* Review body */}
      <div className="p-6 md:p-8">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="w-4 h-4 text-volt" />
          <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Human scout review</span>
        </div>
        <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95] text-ink">
          What the scout said
        </h3>
        <div className="mt-5 bg-cream-card/90 border-l-2 border-volt p-5">
          <p className="text-ink text-base md:text-[17px] leading-[1.7] whitespace-pre-line">
            {review.review_text}
          </p>
        </div>

        {/* Chat thread */}
        <div className="mt-8">
          <div className="flex items-center gap-2 mb-4">
            <MessageSquare className="w-4 h-4 text-volt" />
            <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Conversation</span>
            <span className="text-[10px] uppercase tracking-widest font-bold text-ink/50 ml-auto">
              {review.messages?.length || 0} message{(review.messages?.length || 0) === 1 ? "" : "s"}
            </span>
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
            {(!review.messages || review.messages.length === 0) && (
              <div className="bg-cream-soft border border-gray-border p-4 text-center">
                <p className="text-xs text-ink/55 leading-relaxed">
                  Have a question for your scout? Send them a message below and they'll reply here.
                </p>
              </div>
            )}
            {review.messages?.map((m, i) => {
              const isUser = m.sender === "user";
              return (
                <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
                    <div
                      className={`px-4 py-3 text-sm leading-relaxed ${
                        isUser
                          ? "bg-volt text-white"
                          : "bg-deepnavy border border-gray-border text-ink"
                      }`}
                    >
                      {!isUser && (
                        <div className="text-[10px] uppercase tracking-widest font-bold text-volt mb-1">
                          {m.agent_name || review.agent_name || "Scout"}
                        </div>
                      )}
                      <div className="whitespace-pre-line">{m.text}</div>
                    </div>
                    <span className="text-[10px] uppercase tracking-widest font-bold text-ink/40 px-1">
                      {formatRelative(m.created_at)}
                    </span>
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Compose */}
          <form onSubmit={handleSend} className="mt-5 flex gap-2" data-testid="scout-compose">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Write to your scout..."
              rows={2}
              data-testid="scout-compose-text"
              className="flex-1 bg-deepnavy border border-gray-border px-4 py-3 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-none"
            />
            <button
              type="submit"
              disabled={sending || !draft.trim()}
              data-testid="scout-compose-send"
              className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Send
            </button>
          </form>
          <p className="mt-2 text-[10px] uppercase tracking-widest font-bold text-ink/40">
            Refresh to see new replies from your scout.
          </p>
        </div>
      </div>
    </div>
  );
}
