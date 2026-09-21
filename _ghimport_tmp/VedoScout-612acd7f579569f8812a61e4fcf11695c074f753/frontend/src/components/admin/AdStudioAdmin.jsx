// AdStudioAdmin — one-click ad campaign generator: 4 angles, per-format compositions, QC + export.
import React, { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Megaphone, Loader2, RefreshCw, Download, Check, X, Pencil,
  ImageIcon, Type, MousePointerClick, ShieldCheck, Star, ClipboardCopy,
} from "lucide-react";
import api, { ASSET_BASE } from "@/lib/api";

const LIME = "#CCFF00";
const ON_LIME = "#0D1512";
const INK = "#0A0F0D";
const CREAM = "#F4EFE6";
const GREEN = "#2D6B3D";

const FORMATS = [
  { key: "ig_feed", label: "Instagram Feed", ratio: "4:5", w: 1080, h: 1350, img: "portrait" },
  { key: "story", label: "Stories / Reels", ratio: "9:16", w: 1080, h: 1920, img: "portrait" },
  { key: "fb_feed", label: "Facebook Feed", ratio: "4:5", w: 1080, h: 1350, img: "portrait" },
  { key: "square", label: "Square", ratio: "1:1", w: 1080, h: 1080, img: "square" },
];

const ANGLE_META = {
  emotional: { label: "Emotional", cls: "bg-rose-100 text-rose-800" },
  direct_response: { label: "Direct response", cls: "bg-amber-100 text-amber-800" },
  problem_solution: { label: "Problem / Solution", cls: "bg-sky-100 text-sky-800" },
  product_value: { label: "Product / Value", cls: "bg-emerald-100 text-emerald-800" },
};

const STAGE_LABEL = {
  copy: "Writing 4 distinct concepts…",
  images: "Shooting the photography…",
  qc: "Running the anti-generic quality check…",
  done: "Done",
};

const imgUrl = (rel) => (rel ? `${ASSET_BASE}${rel}` : null);

/* ── Canvas export ──────────────────────────────────────────────────── */
function loadImg(src) {
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.crossOrigin = "anonymous";
    im.onload = () => resolve(im);
    im.onerror = reject;
    im.src = src;
  });
}

function drawCover(ctx, img, x, y, w, h) {
  const s = Math.max(w / img.width, h / img.height);
  const sw = w / s, sh = h / s;
  ctx.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, x, y, w, h);
}

function wrapLines(ctx, text, maxW) {
  const words = (text || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  words.forEach((w) => {
    const t = line ? `${line} ${w}` : w;
    if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; }
    else line = t;
  });
  if (line) lines.push(line);
  return lines;
}

function drawWordmark(ctx, x, y, color, size = 30) {
  ctx.save();
  ctx.font = `800 ${size}px 'Barlow Condensed', sans-serif`;
  ctx.fillStyle = color;
  const text = "SCOUTMEPLAY";
  let cx = x;
  for (const ch of text) {
    ctx.fillText(ch, cx, y);
    cx += ctx.measureText(ch).width + size * 0.14;
  }
  ctx.fillStyle = LIME;
  ctx.beginPath();
  ctx.arc(cx + size * 0.1, y - size * 0.28, size * 0.14, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawCtaPill(ctx, text, x, y, { bg = LIME, fg = ON_LIME, fs = 32 } = {}) {
  ctx.save();
  ctx.font = `800 ${fs}px 'Barlow Condensed', sans-serif`;
  const padX = fs * 1.15, h = fs * 2.6;
  const w = ctx.measureText(text.toUpperCase()).width + padX * 2;
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, h / 2);
  ctx.fill();
  ctx.fillStyle = fg;
  ctx.textBaseline = "middle";
  ctx.fillText(text.toUpperCase(), x + padX, y + h / 2 + 2);
  ctx.restore();
}

function drawHookBlock(ctx, hook, x, yBottom, { fs = 92, maxW = 900, color = CREAM } = {}) {
  ctx.save();
  ctx.font = `900 ${fs}px 'Barlow Condensed', sans-serif`;
  ctx.fillStyle = color;
  const lines = wrapLines(ctx, (hook || "").toUpperCase(), maxW);
  const lh = fs * 1.02;
  const yStart = yBottom - lh * (lines.length - 1);
  lines.forEach((l, i) => ctx.fillText(l, x, yStart + i * lh));
  ctx.restore();
  return yBottom - (lines.length * fs * 1.02);
}

async function renderFormat(fmt, concept) {
  const rel = concept.images?.[fmt.img] || concept.images?.portrait || concept.images?.square;
  if (!rel) throw new Error("no image");
  const img = await loadImg(imgUrl(rel));
  const c = document.createElement("canvas");
  c.width = fmt.w; c.height = fmt.h;
  const ctx = c.getContext("2d");
  const { hook, sub, cta } = concept;

  if (fmt.key === "ig_feed") {
    drawCover(ctx, img, 0, 0, 1080, 1350);
    let g = ctx.createLinearGradient(0, 620, 0, 1350);
    g.addColorStop(0, "rgba(10,15,13,0)"); g.addColorStop(1, "rgba(10,15,13,0.94)");
    ctx.fillStyle = g; ctx.fillRect(0, 620, 1080, 730);
    g = ctx.createLinearGradient(0, 0, 0, 190);
    g.addColorStop(0, "rgba(10,15,13,0.55)"); g.addColorStop(1, "rgba(10,15,13,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 1080, 190);
    drawWordmark(ctx, 72, 108, CREAM);
    const top = drawHookBlock(ctx, hook, 72, 1050, { fs: 96, maxW: 936 });
    void top;
    ctx.font = "400 34px 'Helvetica Neue', Arial, sans-serif";
    ctx.fillStyle = "rgba(244,239,230,0.85)";
    wrapLines(ctx, sub, 880).slice(0, 3).forEach((l, i) => ctx.fillText(l, 72, 1108 + i * 46));
    drawCtaPill(ctx, cta, 72, 1350 - 88 - 84);
  } else if (fmt.key === "story") {
    drawCover(ctx, img, 0, 0, 1080, 1920);
    let g = ctx.createLinearGradient(0, 1000, 0, 1920);
    g.addColorStop(0, "rgba(10,15,13,0)"); g.addColorStop(1, "rgba(10,15,13,0.95)");
    ctx.fillStyle = g; ctx.fillRect(0, 1000, 1080, 920);
    g = ctx.createLinearGradient(0, 0, 0, 320);
    g.addColorStop(0, "rgba(10,15,13,0.6)"); g.addColorStop(1, "rgba(10,15,13,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 1080, 320);
    drawWordmark(ctx, 72, 290, CREAM, 32);
    drawHookBlock(ctx, hook, 72, 1400, { fs: 110, maxW: 936 });
    ctx.font = "400 38px 'Helvetica Neue', Arial, sans-serif";
    ctx.fillStyle = "rgba(244,239,230,0.85)";
    wrapLines(ctx, sub, 880).slice(0, 3).forEach((l, i) => ctx.fillText(l, 72, 1468 + i * 52));
    drawCtaPill(ctx, cta, 72, 1920 - 310 - 96, { fs: 36 });
  } else if (fmt.key === "fb_feed") {
    drawCover(ctx, img, 0, 0, 1080, 950);
    const g = ctx.createLinearGradient(0, 0, 0, 170);
    g.addColorStop(0, "rgba(10,15,13,0.5)"); g.addColorStop(1, "rgba(10,15,13,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 1080, 170);
    drawWordmark(ctx, 64, 96, CREAM, 26);
    ctx.fillStyle = CREAM; ctx.fillRect(0, 950, 1080, 400);
    ctx.fillStyle = LIME; ctx.fillRect(0, 950, 1080, 8);
    ctx.save();
    ctx.font = "900 68px 'Barlow Condensed', sans-serif";
    ctx.fillStyle = INK;
    wrapLines(ctx, (hook || "").toUpperCase(), 950).slice(0, 2).forEach((l, i) => ctx.fillText(l, 64, 1055 + i * 72));
    ctx.restore();
    ctx.font = "400 30px 'Helvetica Neue', Arial, sans-serif";
    ctx.fillStyle = "rgba(10,15,13,0.72)";
    wrapLines(ctx, sub, 620).slice(0, 2).forEach((l, i) => ctx.fillText(l, 64, 1205 + i * 40));
    ctx.save();
    ctx.font = "800 30px 'Barlow Condensed', sans-serif";
    const w = ctx.measureText((cta || "").toUpperCase()).width + 70;
    drawCtaPill(ctx, cta, 1080 - 64 - w, 1350 - 64 - 78, { bg: GREEN, fg: LIME, fs: 30 });
    ctx.restore();
  } else {
    drawCover(ctx, img, 0, 0, 1080, 1080);
    let g = ctx.createLinearGradient(0, 0, 0, 520);
    g.addColorStop(0, "rgba(10,15,13,0.88)"); g.addColorStop(1, "rgba(10,15,13,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, 1080, 520);
    g = ctx.createLinearGradient(0, 880, 0, 1080);
    g.addColorStop(0, "rgba(10,15,13,0)"); g.addColorStop(1, "rgba(10,15,13,0.85)");
    ctx.fillStyle = g; ctx.fillRect(0, 880, 1080, 200);
    ctx.save();
    ctx.font = "900 88px 'Barlow Condensed', sans-serif";
    ctx.fillStyle = CREAM;
    wrapLines(ctx, (hook || "").toUpperCase(), 900).slice(0, 3).forEach((l, i) => ctx.fillText(l, 72, 150 + i * 92));
    ctx.restore();
    drawWordmark(ctx, 72, 1080 - 150, CREAM, 24);
    drawCtaPill(ctx, cta, 72, 1080 - 72 - 70, { fs: 28 });
  }
  return c;
}

async function exportConcept(concept, campaign) {
  try { await document.fonts.load("900 96px 'Barlow Condensed'"); await document.fonts.load("800 32px 'Barlow Condensed'"); } catch { /* noop */ }
  for (const fmt of FORMATS) {
    const canvas = await renderFormat(fmt, concept);
    await new Promise((res) => canvas.toBlob((blob) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `smp-${campaign.product}-${concept.angle}-${fmt.key}-${fmt.w}x${fmt.h}.jpg`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      res();
    }, "image/jpeg", 0.92));
  }
  const txt = [
    `ScoutMePlay — ${campaign.product_label} — ${ANGLE_META[concept.angle]?.label || concept.angle}`,
    "", `Hook: ${concept.hook}`, `Primary text: ${concept.sub}`, `CTA: ${concept.cta}`, "",
    "Formats: 1080x1350 (IG/FB Feed 4:5), 1080x1920 (Stories/Reels 9:16), 1080x1080 (Square 1:1)",
  ].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], { type: "text/plain" }));
  a.download = `smp-${campaign.product}-${concept.angle}-copy.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

/* ── DOM format previews (scaled approximations of the export) ─────── */
function FormatPreview({ fmt, concept }) {
  const rel = concept.images?.[fmt.img] || concept.images?.portrait;
  const url = imgUrl(rel);
  const ar = `${fmt.w} / ${fmt.h}`;
  const hook = (concept.hook || "").toUpperCase();
  if (!url) {
    return (
      <div className="w-full bg-ink/10 flex items-center justify-center" style={{ aspectRatio: ar }}>
        <ImageIcon className="w-6 h-6 text-ink/30" />
      </div>
    );
  }
  if (fmt.key === "fb_feed") {
    return (
      <div className="w-full relative overflow-hidden" style={{ aspectRatio: ar, background: CREAM }}>
        <div className="absolute inset-x-0 top-0" style={{ height: "70%" }}>
          <img src={url} alt="" className="w-full h-full object-cover" />
          <div className="absolute top-0 inset-x-0 h-8 bg-gradient-to-b from-ink/50 to-transparent" />
          <div className="absolute top-1.5 left-2 text-[6px] font-black tracking-[0.2em]" style={{ color: CREAM }}>SCOUTMEPLAY<span style={{ color: LIME }}> ●</span></div>
        </div>
        <div className="absolute inset-x-0 bottom-0 px-2 pt-1.5" style={{ height: "30%", background: CREAM, borderTop: `2px solid ${LIME}` }}>
          <div className="font-barlow font-black uppercase leading-[1.02] text-[11px] text-ink line-clamp-2">{hook}</div>
          <div className="text-[6.5px] text-ink/70 mt-0.5 line-clamp-2 pr-14">{concept.sub}</div>
          <span className="absolute bottom-1.5 right-2 px-1.5 py-0.5 rounded-full text-[6px] font-black uppercase" style={{ background: GREEN, color: LIME }}>{concept.cta}</span>
        </div>
      </div>
    );
  }
  const isStory = fmt.key === "story";
  const isSquare = fmt.key === "square";
  return (
    <div className="w-full relative overflow-hidden bg-ink" style={{ aspectRatio: ar }}>
      <img src={url} alt="" className="absolute inset-0 w-full h-full object-cover" />
      {isSquare ? (
        <>
          <div className="absolute inset-x-0 top-0 h-[48%] bg-gradient-to-b from-ink/90 to-transparent" />
          <div className="absolute top-2 left-2 right-2 font-barlow font-black uppercase leading-[1.02] text-[13px] line-clamp-3" style={{ color: CREAM }}>{hook}</div>
          <div className="absolute bottom-6 left-2 text-[6px] font-black tracking-[0.2em]" style={{ color: CREAM }}>SCOUTMEPLAY<span style={{ color: LIME }}> ●</span></div>
          <span className="absolute bottom-1.5 left-2 px-1.5 py-0.5 rounded-full text-[6px] font-black uppercase" style={{ background: LIME, color: ON_LIME }}>{concept.cta}</span>
        </>
      ) : (
        <>
          <div className="absolute inset-x-0 bottom-0 h-[55%] bg-gradient-to-t from-ink/95 via-ink/55 to-transparent" />
          <div className="absolute inset-x-0 top-0 h-10 bg-gradient-to-b from-ink/55 to-transparent" />
          <div className={`absolute left-2 text-[6px] font-black tracking-[0.2em] ${isStory ? "top-4" : "top-2"}`} style={{ color: CREAM }}>SCOUTMEPLAY<span style={{ color: LIME }}> ●</span></div>
          <div className={`absolute left-2 right-2 ${isStory ? "bottom-[22%]" : "bottom-[24%]"}`}>
            <div className={`font-barlow font-black uppercase leading-[1.02] line-clamp-3 ${isStory ? "text-[14px]" : "text-[13px]"}`} style={{ color: CREAM }}>{hook}</div>
            <div className="text-[6.5px] mt-1 line-clamp-2" style={{ color: "rgba(244,239,230,0.85)" }}>{concept.sub}</div>
          </div>
          <span className={`absolute left-2 px-1.5 py-0.5 rounded-full text-[6.5px] font-black uppercase ${isStory ? "bottom-[13%]" : "bottom-[8%]"}`} style={{ background: LIME, color: ON_LIME }}>{concept.cta}</span>
        </>
      )}
    </div>
  );
}

/* ── QC panel ───────────────────────────────────────────────────────── */
function QcPanel({ qc }) {
  if (!qc) return <div className="text-xs text-ink/50 italic">Quality check pending…</div>;
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${qc.passed ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
          <ShieldCheck className="w-3 h-3" /> {qc.passed ? "QC passed" : "QC issues"}
        </span>
        {qc.auto_repaired && <span className="text-[10px] uppercase font-bold text-ink/50">auto-improved once</span>}
      </div>
      <div className="grid grid-cols-1 gap-1">
        {(qc.checks || []).map((c) => (
          <div key={c.key} className="flex items-start gap-1.5 text-[11px]">
            {c.pass
              ? <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-[1px]" />
              : <X className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-[1px]" />}
            <span className={c.pass ? "text-ink/60" : "text-rose-700"}>
              {c.label}{!c.pass && c.issue ? ` — ${c.issue}` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Concept card ───────────────────────────────────────────────────── */
function ConceptCard({ concept, campaign, onUpdated }) {
  const [fmt, setFmt] = useState(FORMATS[0]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ hook: "", sub: "", cta: "" });
  const [busy, setBusy] = useState("");
  const meta = ANGLE_META[concept.angle] || { label: concept.angle, cls: "bg-gray-100 text-gray-700" };

  const call = async (label, fn, okMsg) => {
    setBusy(label);
    try { const { data } = await fn(); onUpdated(data); okMsg && toast.success(okMsg); }
    catch { toast.error("Action failed — try again"); }
    finally { setBusy(""); }
  };

  const startEdit = () => { setDraft({ hook: concept.hook, sub: concept.sub, cta: concept.cta }); setEditing(true); };
  const saveEdit = () => call("edit",
    () => api.put(`/admin/ad-studio/campaigns/${campaign.id}/concepts/${concept.id}`, draft),
    "Copy saved").then(() => setEditing(false));
  const regen = (element, msg) => call(element,
    () => api.post(`/admin/ad-studio/campaigns/${campaign.id}/concepts/${concept.id}/regen`, { element }), msg);
  const rerunQc = () => call("qc",
    () => api.post(`/admin/ad-studio/campaigns/${campaign.id}/concepts/${concept.id}/qc`), "QC re-run complete");

  const toggleWinner = async () => {
    try {
      const { data } = await api.post(`/admin/ad-studio/campaigns/${campaign.id}/concepts/${concept.id}/select`);
      onUpdated({ ...concept, selected: data.selected });
      toast.success(data.selected ? "Marked as winner" : "Winner unmarked");
    } catch { toast.error("Could not update"); }
  };

  const doExport = async () => {
    setBusy("export");
    try { await exportConcept(concept, campaign); toast.success("4 formats + copy text downloaded"); }
    catch { toast.error("Export failed — image may still be generating"); }
    finally { setBusy(""); }
  };

  const copyText = () => {
    navigator.clipboard.writeText(`${concept.hook}\n\n${concept.sub}\n\nCTA: ${concept.cta}`);
    toast.success("Copy text on clipboard");
  };

  return (
    <div data-testid={`ad-concept-${concept.angle}`} className={`bg-surface border ${concept.selected ? "border-volt border-2" : "border-gray-border"} flex flex-col`}>
      <div className="flex items-center justify-between px-4 pt-4">
        <span className={`px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${meta.cls}`}>{meta.label}</span>
        <button
          data-testid={`ad-concept-${concept.angle}-winner-btn`}
          onClick={toggleWinner}
          className={`inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider px-2 py-1 transition-colors ${concept.selected ? "bg-volt text-white" : "text-ink/50 hover:text-ink border border-gray-border"}`}
        >
          <Star className={`w-3 h-3 ${concept.selected ? "fill-current" : ""}`} /> {concept.selected ? "Winner" : "Pick winner"}
        </button>
      </div>

      <div className="px-4 mt-3 flex gap-1 flex-wrap">
        {FORMATS.map((f) => (
          <button
            key={f.key}
            data-testid={`ad-format-${concept.angle}-${f.key}`}
            onClick={() => setFmt(f)}
            className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider border transition-colors ${fmt.key === f.key ? "bg-ink text-cream-base border-ink" : "border-gray-border text-ink/50 hover:text-ink"}`}
          >
            {f.label} {f.ratio}
          </button>
        ))}
      </div>

      <div className="px-4 mt-3">
        <div className="max-w-[260px] mx-auto shadow-sm">
          <FormatPreview fmt={fmt} concept={concept} />
        </div>
      </div>

      <div className="px-4 mt-4 space-y-2">
        {editing ? (
          <div className="space-y-2">
            <input data-testid={`ad-edit-hook-${concept.angle}`} value={draft.hook} onChange={(e) => setDraft({ ...draft, hook: e.target.value })}
              className="w-full border border-gray-border px-2 py-1.5 text-sm font-bold bg-cream-base" placeholder="Hook" />
            <textarea data-testid={`ad-edit-sub-${concept.angle}`} value={draft.sub} onChange={(e) => setDraft({ ...draft, sub: e.target.value })}
              className="w-full border border-gray-border px-2 py-1.5 text-xs bg-cream-base" rows={2} placeholder="Supporting line" />
            <input data-testid={`ad-edit-cta-${concept.angle}`} value={draft.cta} onChange={(e) => setDraft({ ...draft, cta: e.target.value })}
              className="w-40 border border-gray-border px-2 py-1.5 text-xs font-bold bg-cream-base" placeholder="CTA" />
            <div className="flex gap-2">
              <button data-testid={`ad-edit-save-${concept.angle}`} onClick={saveEdit} disabled={busy === "edit"}
                className="px-3 py-1.5 bg-volt text-white text-xs font-bold uppercase tracking-wider">
                {busy === "edit" ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
              </button>
              <button onClick={() => setEditing(false)} className="px-3 py-1.5 border border-gray-border text-xs font-bold uppercase tracking-wider text-ink/60">Cancel</button>
            </div>
          </div>
        ) : (
          <div className="relative group">
            <div data-testid={`ad-hook-${concept.angle}`} className="font-barlow font-black uppercase text-xl leading-tight text-ink">{concept.hook}</div>
            <div className="text-sm text-ink/70 mt-1">{concept.sub}</div>
            <div className="mt-1.5 inline-block px-2.5 py-1 rounded-full text-[11px] font-black uppercase" style={{ background: LIME, color: ON_LIME }}>{concept.cta}</div>
            <button data-testid={`ad-edit-btn-${concept.angle}`} onClick={startEdit} title="Edit copy"
              className="absolute top-0 right-0 p-1 text-ink/40 hover:text-ink"><Pencil className="w-3.5 h-3.5" /></button>
          </div>
        )}
      </div>

      <div className="px-4 mt-3 flex flex-wrap gap-1.5">
        {[
          { el: "image", icon: ImageIcon, label: "New photo", msg: "New photos generated + QC re-run" },
          { el: "hook", icon: Type, label: "New hook", msg: "New hook written + QC re-run" },
          { el: "copy", icon: Type, label: "New text", msg: "New supporting line + QC re-run" },
          { el: "cta", icon: MousePointerClick, label: "New CTA", msg: "New CTA + QC re-run" },
        ].map(({ el, icon: Icon, label, msg }) => (
          <button
            key={el}
            data-testid={`ad-regen-${el}-${concept.angle}`}
            onClick={() => regen(el, msg)}
            disabled={!!busy}
            className="inline-flex items-center gap-1 px-2 py-1 border border-gray-border text-[10px] font-bold uppercase tracking-wider text-ink/60 hover:text-ink disabled:opacity-40"
          >
            {busy === el ? <Loader2 className="w-3 h-3 animate-spin" /> : <Icon className="w-3 h-3" />} {label}
          </button>
        ))}
        <button data-testid={`ad-rerun-qc-${concept.angle}`} onClick={rerunQc} disabled={!!busy}
          className="inline-flex items-center gap-1 px-2 py-1 border border-gray-border text-[10px] font-bold uppercase tracking-wider text-ink/60 hover:text-ink disabled:opacity-40">
          {busy === "qc" ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Re-run QC
        </button>
      </div>

      <div className="px-4 mt-4 pb-4 border-t border-gray-border pt-3 flex-1">
        <QcPanel qc={concept.qc} />
      </div>

      <div className="px-4 pb-4 flex gap-2">
        <button data-testid={`ad-export-${concept.angle}`} onClick={doExport} disabled={!!busy || !concept.images?.portrait}
          className="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2.5 bg-ink text-cream-base text-xs font-black uppercase tracking-wider hover:bg-volt transition-colors disabled:opacity-40">
          {busy === "export" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Export 4 formats
        </button>
        <button data-testid={`ad-copy-text-${concept.angle}`} onClick={copyText} title="Copy ad text"
          className="px-3 py-2.5 border border-gray-border text-ink/60 hover:text-ink"><ClipboardCopy className="w-4 h-4" /></button>
      </div>
    </div>
  );
}

/* ── Main panel ─────────────────────────────────────────────────────── */
export default function AdStudioAdmin() {
  const [products, setProducts] = useState([]);
  const [product, setProduct] = useState("");
  const [language, setLanguage] = useState("da");
  const [campaigns, setCampaigns] = useState([]);
  const [campaign, setCampaign] = useState(null);
  const [generating, setGenerating] = useState(false);
  const pollRef = useRef(null);

  const loadCampaigns = useCallback(() => {
    api.get("/admin/ad-studio/campaigns").then(({ data }) => setCampaigns(data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    api.get("/admin/ad-studio/products").then(({ data }) => {
      setProducts(data || []);
      if (data?.length) setProduct(data[0].key);
    }).catch(() => {});
    loadCampaigns();
    return () => clearInterval(pollRef.current);
  }, [loadCampaigns]);

  const openCampaign = useCallback(async (cid) => {
    try {
      const { data } = await api.get(`/admin/ad-studio/campaigns/${cid}`);
      setCampaign(data);
      if (data.status === "generating") startPoll(cid);
    } catch { toast.error("Could not load campaign"); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startPoll = (cid) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/admin/ad-studio/campaigns/${cid}`);
        setCampaign(data);
        if (data.status !== "generating") {
          clearInterval(pollRef.current);
          setGenerating(false);
          loadCampaigns();
          if (data.status === "ready") toast.success("Campaign ready — 4 concepts, QC complete");
          else toast.error(`Generation failed: ${data.error || "unknown error"}`);
        }
      } catch { /* keep polling */ }
    }, 4000);
  };

  const generate = async () => {
    if (!product) return;
    setGenerating(true);
    try {
      const { data } = await api.post("/admin/ad-studio/generate", { product, language });
      toast.info("Building your campaign — copy, photography and QC take ~2-3 minutes…");
      await openCampaign(data.campaign_id);
      startPoll(data.campaign_id);
    } catch {
      setGenerating(false);
      toast.error("Could not start generation");
    }
  };

  const onConceptUpdated = (updated) => {
    setCampaign((prev) => prev && ({
      ...prev,
      concepts: prev.concepts.map((c) => (c.id === updated.id ? { ...c, ...updated } : c)),
    }));
  };

  const selectedProduct = products.find((p) => p.key === product);

  return (
    <div data-testid="ad-studio-panel" className="space-y-8">
      <div className="bg-surface border border-gray-border p-6">
        <div className="flex items-center gap-2 mb-1">
          <Megaphone className="w-5 h-5 text-volt" />
          <h2 className="font-barlow font-black uppercase text-2xl tracking-tight">Ad Studio</h2>
        </div>
        <p className="text-sm text-ink/60 max-w-2xl">
          Pick a product → get 4 genuinely different, QC-checked ad concepts with authentic football photography.
          Every concept exports as 4 finished, ready-to-upload files: IG Feed 4:5, Stories 9:16, FB Feed 4:5 and Square 1:1 — plus the ad text for Meta Ads Manager.
        </p>

        <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {products.map((p) => (
            <button
              key={p.key}
              data-testid={`ad-product-${p.key}`}
              onClick={() => setProduct(p.key)}
              className={`text-left px-3 py-2.5 border text-xs font-bold uppercase tracking-wider transition-colors ${product === p.key ? "bg-ink text-cream-base border-ink" : "border-gray-border text-ink/60 hover:text-ink"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {selectedProduct && (
          <p className="mt-3 text-xs text-ink/50 max-w-3xl italic">Allowed claims: {selectedProduct.facts}</p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <div className="flex border border-gray-border">
            {[{ v: "da", l: "Dansk" }, { v: "en", l: "English" }].map(({ v, l }) => (
              <button key={v} data-testid={`ad-lang-${v}`} onClick={() => setLanguage(v)}
                className={`px-4 py-2 text-xs font-bold uppercase tracking-wider ${language === v ? "bg-volt text-white" : "text-ink/60 hover:text-ink"}`}>
                {l}
              </button>
            ))}
          </div>
          <button
            data-testid="ad-generate-btn"
            onClick={generate}
            disabled={generating || !product}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-volt text-white text-sm font-black uppercase tracking-wider hover:bg-volt-hover transition-colors disabled:opacity-50"
          >
            {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Megaphone className="w-4 h-4" />}
            {generating ? "Generating…" : "Generate campaign"}
          </button>
        </div>
      </div>

      {campaign?.status === "generating" && (
        <div data-testid="ad-generating-state" className="bg-surface border border-gray-border p-8 text-center">
          <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
          <div className="mt-3 font-barlow font-black uppercase text-lg">{campaign.product_label}</div>
          <div className="text-sm text-ink/60">{STAGE_LABEL[campaign.stage] || "Working…"}</div>
          <div className="mt-3 flex justify-center gap-2">
            {["copy", "images", "qc"].map((s, i) => {
              const order = { copy: 0, images: 1, qc: 2, done: 3 };
              const cur = order[campaign.stage] ?? 0;
              return <div key={s} className={`w-16 h-1 ${i < cur ? "bg-volt" : i === cur ? "bg-volt/50 animate-pulse" : "bg-ink/10"}`} />;
            })}
          </div>
        </div>
      )}

      {campaign?.status === "error" && (
        <div data-testid="ad-error-state" className="bg-rose-50 border border-rose-200 p-6 text-sm text-rose-800">
          Generation failed: {campaign.error}. Hit "Generate campaign" to try again.
        </div>
      )}

      {campaign?.status === "ready" && (
        <div>
          <div className="flex items-baseline justify-between mb-4">
            <h3 className="font-barlow font-black uppercase text-xl tracking-tight">
              {campaign.product_label} — 4 concepts <span className="text-ink/40 text-sm normal-case font-normal">({campaign.language === "da" ? "Dansk" : "English"})</span>
            </h3>
          </div>
          <div data-testid="ad-concepts-grid" className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {(campaign.concepts || []).map((c) => (
              <ConceptCard key={c.id} concept={c} campaign={campaign} onUpdated={onConceptUpdated} />
            ))}
          </div>
        </div>
      )}

      {campaigns.length > 0 && (
        <div className="bg-surface border border-gray-border p-6">
          <h3 className="font-barlow font-black uppercase text-lg tracking-tight mb-3">Recent campaigns</h3>
          <div className="divide-y divide-gray-border">
            {campaigns.map((c) => (
              <button
                key={c.id}
                data-testid={`ad-campaign-row-${c.id}`}
                onClick={() => openCampaign(c.id)}
                className={`w-full flex items-center justify-between py-2.5 text-left hover:bg-cream-base/60 px-2 -mx-2 ${campaign?.id === c.id ? "bg-cream-base/60" : ""}`}
              >
                <div>
                  <span className="text-sm font-bold text-ink">{c.product_label}</span>
                  <span className="ml-2 text-[10px] uppercase font-bold text-ink/40">{c.language === "da" ? "DA" : "EN"}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-[10px] font-black uppercase px-2 py-0.5 ${c.status === "ready" ? "bg-emerald-100 text-emerald-800" : c.status === "error" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>
                    {c.status}
                  </span>
                  <span className="text-[11px] text-ink/40">{(c.created_at || "").slice(0, 16).replace("T", " ")}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
