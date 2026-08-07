import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { ASSET_BASE } from "@/lib/api";
import PremiumReportV2 from "@/components/report-v2/PremiumReportV2";
import SEO from "@/components/SEO";
import { Loader2, ArrowRight, Eye } from "lucide-react";

export default function DemoReportPage() {
  const [report, setReport] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
    api.get("/demo-report")
      .then(({ data }) => setReport(data))
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-ink/70 text-sm">The sample report isn't available right now.</p>
        <Link to="/" className="text-forest font-bold text-sm underline" data-testid="demo-report-home-link">Back to the front page</Link>
      </div>
    );
  }
  if (!report) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-forest" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F4F1E8]" data-testid="demo-report-page">
      {/* Sticky sample banner */}
      <div className="sticky top-0 z-50 bg-ink text-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap" data-testid="demo-report-banner">
        <div className="flex items-center gap-2.5 min-w-0">
          <Eye className="w-4 h-4 text-[#CCFF00] shrink-0" />
          <p className="text-[12.5px] leading-snug">
            <span className="font-black uppercase tracking-wider text-[#CCFF00]">Sample report</span>
            <span className="text-white/70"> — fictional player. This is exactly what your family receives.</span>
          </p>
        </div>
        <Link
          to="/upload"
          data-testid="demo-report-upload-cta"
          className="shrink-0 inline-flex items-center gap-1.5 bg-[#CCFF00] text-ink font-black text-[12px] uppercase tracking-wider px-4 py-2 hover:bg-white transition-colors"
        >
          Get this for your player <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      <PremiumReportV2 report={report} assetBase={ASSET_BASE} />

      {/* Bottom conversion strip */}
      <div className="bg-ink px-6 py-12 text-center" data-testid="demo-report-bottom-cta">
        <p className="text-[#CCFF00] text-[11px] font-black uppercase tracking-[0.3em] mb-3">Your player deserves this</p>
        <h2 className="text-white font-black text-2xl sm:text-3xl uppercase tracking-tight mb-4">Start with a free preview</h2>
        <p className="text-white/60 text-sm max-w-md mx-auto mb-7">Upload a short clip, tap your player, and see a free preview before you decide anything.</p>
        <Link
          to="/upload"
          data-testid="demo-report-bottom-upload"
          className="inline-flex items-center gap-2 bg-[#CCFF00] text-ink font-black text-[13px] uppercase tracking-wider px-8 py-4 hover:bg-white transition-colors"
        >
          Upload your clip <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}
