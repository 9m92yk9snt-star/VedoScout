// Identity verification trust strip — shows HOW the player identity was locked.
import React from "react";
import { ShieldCheck, Fingerprint, Crosshair, ScanEye, Shirt } from "lucide-react";

export function VerifiedIdentityStrip({ verification }) {
  const v = verification || {};
  if (!v.anchors) return null;
  const stats = v.identity_stats || {};
  const chips = [
    { icon: Fingerprint, text: `Marked by owner · ${v.anchors} tap${v.anchors > 1 ? "s" : ""}`, testid: "v2-verified-anchors" },
  ];
  if (v.tracked) chips.push({ icon: Crosshair, text: "Optical tracking locked", testid: "v2-verified-tracking" });
  if (stats.checked > 0) {
    chips.push({
      icon: ScanEye,
      text: `Dual identity check · ${stats.verified || 0}/${stats.checked} images confirmed`,
      testid: "v2-verified-dualai",
    });
  }
  if (v.jersey_number) {
    chips.push({
      icon: Shirt,
      text: v.jersey_check === "confirmed" ? `Shirt #${v.jersey_number} confirmed on video` : `Shirt #${v.jersey_number} on file`,
      testid: "v2-verified-jersey",
    });
  }
  return (
    <div
      data-testid="v2-verified-strip"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 bg-[#12402A] rounded-[12px] px-4 py-3"
    >
      <span className="inline-flex items-center gap-2 text-[#CCFF00]">
        <ShieldCheck className="w-4 h-4" />
        <span className="text-[10px] font-extrabold tracking-[0.16em] uppercase">Identity locked</span>
      </span>
      {chips.map(({ icon: Icon, text, testid }) => (
        <span
          key={testid}
          data-testid={testid}
          className="inline-flex items-center gap-1.5 bg-[#0D2818] text-white/85 text-[10.5px] font-bold px-2.5 py-1 rounded-full"
        >
          <Icon className="w-3 h-3 text-[#CCFF00]" />
          {text}
        </span>
      ))}
    </div>
  );
}

/**
 * Publication completeness and observed evidence are different authorities.
 * A report can be ready for display while only some source windows have been
 * analyzed. Never turn a partial video into complete-match statistics.
 */
export function EvidenceCoverageNotice({ report }) {
  const canonical = report?.canonical_events;
  const verified = report?.full_report?.verified_stats;
  const status = verified?.coverage_status;
  const hasPartialCanonical = canonical?.coverage_complete === false;
  const hasPartialVerified = status === "PARTIAL" || status === "INCOMPLETE";
  if (!hasPartialCanonical && !hasPartialVerified) return null;
  return (
    <div role="status" data-testid="v2-partial-source-coverage"
      className="mb-4 rounded-lg border border-[#CBD8C7] bg-[#F5F8F2] px-4 py-3 text-xs font-semibold text-[#26432E]">
      <span className="font-extrabold">Partial video coverage.</span>{" "}
      This report summarizes observed actions in the analyzed footage.
      It does not establish complete-match totals. Unresolved actions are not counted as verified.
    </div>
  );
}
