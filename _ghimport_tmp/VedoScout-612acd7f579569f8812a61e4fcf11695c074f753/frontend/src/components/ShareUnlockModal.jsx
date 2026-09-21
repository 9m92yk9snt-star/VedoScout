// ShareUnlockModal — exit-intent "share to unlock one more story" for the free preview.
// Any completed share action permanently unlocks one extra REAL score story.

import React, { useEffect, useState, useCallback } from "react";
import { X, Share2, Copy, Download, Gift, Check, Loader2, Sparkles } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const LIME = "#CCFF00";
const INKG = "#0B1F14";
const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";

function WaIcon() {
  return <span className="font-black text-[13px]">WA</span>;
}
function FbIcon() {
  return <span className="font-black text-[13px]">f</span>;
}

export default function ShareUnlockModal({ open, onClose, report, onUnlocked }) {
  const [shareInfo, setShareInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [done, setDone] = useState(false);
  const pd = report?.player_details || {};
  const first = String(pd.player_name || "your player").split(" ")[0];

  useEffect(() => {
    if (!open || shareInfo || !report?.id) return;
    setLoading(true);
    api.post(`/reports/${report.id}/teaser-share`)
      .then(({ data }) => setShareInfo(data))
      .catch(() => toast.error("Could not prepare the share card — try again."))
      .finally(() => setLoading(false));
  }, [open, report?.id, shareInfo]);

  const unlock = useCallback(async () => {
    if (done || unlocking) return;
    setUnlocking(true);
    try {
      const { data } = await api.post(`/reports/${report.id}/share-unlock`);
      setDone(true);
      onUnlocked?.(data?.bonus || null);
      toast.success(`One more of ${first}'s stories is now open 🎉`);
    } catch {
      toast.error("Could not unlock — try again.");
    } finally {
      setUnlocking(false);
    }
  }, [done, unlocking, report?.id, first, onUnlocked]);

  const shareText = shareInfo?.text || `${first}'s football story — discovered on video. See it here:`;
  const shareUrl = shareInfo?.share_url || "";

  const nativeShare = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: `${first} on ScoutMePlay`, text: shareText, url: shareUrl });
        unlock();
      } else {
        copyLink();
      }
    } catch { /* user cancelled — no unlock */ }
  };
  const openAndUnlock = (url) => {
    window.open(url, "_blank", "noopener");
    unlock();
  };
  const copyLink = async () => {
    const full = `${shareText} ${shareUrl}`;
    try {
      await navigator.clipboard.writeText(full);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = full;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch { /* best effort */ }
      document.body.removeChild(ta);
    }
    toast.success("Link copied — paste it anywhere");
    unlock();
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" data-testid="share-unlock-modal">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-[440px] rounded-[22px] overflow-hidden shadow-2xl" style={{ background: INKG }}>
        <button
          type="button"
          onClick={onClose}
          data-testid="share-modal-close"
          className="absolute top-3 right-3 z-10 w-9 h-9 rounded-full bg-white/10 flex items-center justify-center text-white/80 hover:bg-white/20"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="p-6 pb-5 text-center">
          <span className="w-12 h-12 rounded-2xl mx-auto flex items-center justify-center" style={{ background: "rgba(204,255,0,0.14)", border: `1px solid ${LIME}55` }}>
            <Gift className="w-6 h-6" style={{ color: LIME }} />
          </span>
          {done ? (
            <>
              <h3 className="font-barlow font-black uppercase text-white text-[22px] leading-tight mt-3">
                One more of <span style={{ color: LIME }}>{first}&rsquo;s</span> stories is open
              </h3>
              <p className="text-white/70 text-[13px] mt-2">Scroll down — it&rsquo;s waiting in his numbers. Thank you for sharing his journey.</p>
              <button
                type="button"
                onClick={onClose}
                data-testid="share-modal-done-btn"
                className="mt-4 inline-flex items-center gap-2 rounded-full px-8 py-3 font-barlow font-black uppercase text-[13px]"
                style={{ background: LIME, color: INKG }}
              >
                <Sparkles className="w-4 h-4" /> Show me
              </button>
            </>
          ) : (
            <>
              <h3 className="font-barlow font-black uppercase text-white text-[22px] leading-tight mt-3">
                Share {first}&rsquo;s card — unlock <span style={{ color: LIME }}>one more story</span>
              </h3>
              <p className="text-white/70 text-[13px] mt-2 leading-relaxed">
                We made a card of {first} from your own tap. Share it with the family — and one more of his real score stories opens right now.
              </p>
            </>
          )}
        </div>

        {!done && (
          <>
            <div className="px-6">
              {loading ? (
                <div className="h-56 rounded-xl bg-white/5 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-white/60" />
                </div>
              ) : shareInfo?.card_feed_url ? (
                <img
                  src={`${ASSET_BASE}${shareInfo.card_feed_url}`}
                  alt={`${first}'s share card`}
                  data-testid="share-card-preview"
                  className="w-full max-h-[280px] object-contain rounded-xl border border-white/10"
                />
              ) : null}
            </div>

            <div className="p-6 pt-4">
              <button
                type="button"
                onClick={nativeShare}
                disabled={loading}
                data-testid="share-native-btn"
                className="w-full rounded-full py-3.5 font-barlow font-black uppercase tracking-[0.06em] text-[14px] flex items-center justify-center gap-2 active:scale-[0.98] transition-transform disabled:opacity-50"
                style={{ background: LIME, color: INKG }}
              >
                <Share2 className="w-4 h-4" /> Share {first}&rsquo;s card
              </button>
              <div className="grid grid-cols-4 gap-2 mt-3">
                <button type="button" data-testid="share-wa-btn" disabled={loading}
                  onClick={() => openAndUnlock(`https://wa.me/?text=${encodeURIComponent(`${shareText} ${shareUrl}`)}`)}
                  className="rounded-xl py-2.5 bg-white/8 border border-white/15 text-white flex flex-col items-center gap-1 hover:bg-white/15 disabled:opacity-50" style={{ background: "rgba(255,255,255,0.08)" }}>
                  <WaIcon /><span className="text-[9px] font-bold text-white/60">WhatsApp</span>
                </button>
                <button type="button" data-testid="share-fb-btn" disabled={loading}
                  onClick={() => openAndUnlock(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`)}
                  className="rounded-xl py-2.5 border border-white/15 text-white flex flex-col items-center gap-1 hover:bg-white/15 disabled:opacity-50" style={{ background: "rgba(255,255,255,0.08)" }}>
                  <FbIcon /><span className="text-[9px] font-bold text-white/60">Facebook</span>
                </button>
                <button type="button" data-testid="share-copy-btn" disabled={loading} onClick={copyLink}
                  className="rounded-xl py-2.5 border border-white/15 text-white flex flex-col items-center gap-1 hover:bg-white/15 disabled:opacity-50" style={{ background: "rgba(255,255,255,0.08)" }}>
                  <Copy className="w-4 h-4" /><span className="text-[9px] font-bold text-white/60">Copy link</span>
                </button>
                <a href={shareInfo?.card_story_url ? `${ASSET_BASE}${shareInfo.card_story_url}` : "#"} download={`${first}-scoutmeplay.png`}
                  data-testid="share-download-btn" onClick={() => !loading && unlock()}
                  className="rounded-xl py-2.5 border border-white/15 text-white flex flex-col items-center gap-1 hover:bg-white/15" style={{ background: "rgba(255,255,255,0.08)" }}>
                  <Download className="w-4 h-4" /><span className="text-[9px] font-bold text-white/60">Story / TikTok</span>
                </a>
              </div>
              <p className="text-white/40 text-[10.5px] text-center mt-3 flex items-center justify-center gap-1.5">
                <Check className="w-3 h-3" /> Instagram, Messenger &amp; TikTok: use Share or download the card
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
