// ReviewPrompt — dashboard card where a user leaves a short review (stars + 2 lines).
import React, { useEffect, useState } from "react";
import { Star, Send, Check } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function ReviewPrompt() {
  const [stars, setStars] = useState(5);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState(null);

  useEffect(() => {
    api.get("/reviews/mine").then(({ data }) => {
      if (data?.review) {
        setMine(data.review);
        setStars(data.review.stars);
        setText(data.review.text);
      }
    }).catch(() => {});
  }, []);

  const submit = async () => {
    if (!text.trim()) { toast.error("Write a line or two first"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/reviews", { stars, text: text.trim() });
      setMine(data?.review || { stars, text });
      toast.success("Thank you — your words help other families find us");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save the review");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-10 bg-white rounded-3xl border border-gray-border p-6" data-testid="review-prompt">
      <div className="flex items-center gap-2 text-[10px] font-extrabold tracking-[0.2em] uppercase text-[#5C7A00]">
        {mine ? <Check className="w-3.5 h-3.5" /> : <Star className="w-3.5 h-3.5" />}
        {mine ? "Your review — shown on the front page" : "Share your experience"}
      </div>
      <h3 className="font-barlow font-black uppercase text-[20px] text-ink mt-1">
        {mine ? "Thank you for the words" : "What did you discover about your player?"}
      </h3>
      <div className="flex gap-1.5 mt-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <button key={i} type="button" data-testid={`review-star-${i}`} onClick={() => setStars(i)}>
            <Star className="w-7 h-7 transition-transform hover:scale-110" style={{ color: i <= stars ? "#B9CE00" : "#D8D3C4", fill: i <= stars ? "#B9CE00" : "none" }} />
          </button>
        ))}
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, 180))}
        rows={2}
        maxLength={180}
        data-testid="review-text-input"
        placeholder="Two lines about what the analysis meant for your player…"
        className="mt-3 w-full bg-[#FBF9F3] border border-[#E5DFCE] rounded-xl px-4 py-3 text-sm text-ink focus:outline-none focus:border-forest resize-none"
      />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[11px] text-ink/40">{text.length}/180</span>
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          data-testid="review-submit-btn"
          className="inline-flex items-center gap-2 rounded-full px-6 py-2.5 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-[11px] disabled:opacity-50"
        >
          <Send className="w-3.5 h-3.5" /> {mine ? "Update review" : "Publish review"}
        </button>
      </div>
    </section>
  );
}
