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
      text: `Dual-AI identity check · ${stats.verified || 0}/${stats.checked} images confirmed`,
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
