import React from "react";
import { Link } from "react-router-dom";
import Navigation from "@/components/Navigation";
import SEO from "@/components/SEO";
import { ChevronLeft } from "lucide-react";

/* ScoutMePlay methodology — public page + appendix on every PDF.
   Strictly aligned with UEFA youth-development pillars; never claims certification. */

const PILLARS = [
  {
    name: "Technical",
    body: "Skills with the ball — first touch, ball control, passing, dribbling, shooting, weak-foot use, 1v1.",
  },
  {
    name: "Tactical",
    body: "Decisions without the ball — positioning, off-ball movement, scanning, decision-making, timing of runs, game understanding.",
  },
  {
    name: "Physical",
    body: "Athletic foundation — acceleration, speed, balance, agility, intensity (90-minute), body control.",
  },
  {
    name: "Mental",
    body: "Habits and character — confidence, work rate, courage in duels, response to mistakes, competitive mindset, focus.",
  },
];

const TIERS = [
  {
    key: "elite_academy",
    label: "Elite Academy",
    body: "Top-end Category-1 academies of national associations (e.g. La Masia, Clairefontaine, Cobham-level). Roughly the top 1–3% of an age group.",
  },
  {
    key: "pro_academy",
    label: "Pro Academy",
    body: "Strong regional or national pro-club academies. Trial-ready for serious competitive pathways. Roughly the top 10–15%.",
  },
  {
    key: "strong_club",
    label: "Strong Club",
    body: "Higher-level competitive club football — best teams in the region, talent centres, district selections. Roughly the top 30%.",
  },
  {
    key: "standard_club",
    label: "Standard Club",
    body: "Mainstream club football where most players develop. The baseline for organised youth football.",
  },
];

const AGE_BRACKETS = [
  { key: "U11",     body: "Foundation — coordination, ball mastery, basic decision-making." },
  { key: "U13",     body: "Build phase — scanning habits, positional discipline, both-footed development." },
  { key: "U15",     body: "Performance phase — match impact, pressing intensity, tactical role clarity." },
  { key: "U17",     body: "Specialisation — position-specific excellence, physical maturity, mental resilience." },
  { key: "U19",     body: "Pre-professional — match management, leadership, consistency across 90 minutes." },
  { key: "U21",     body: "Professional threshold — high-performance habits, durability, decision quality at speed." },
];

export default function MethodologyPage() {
  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <SEO
        title="Methodology — How ScoutMePlay grades players"
        description="A transparent look at the methodology behind ScoutMePlay reports: UEFA youth-development pillars, age-bracketed benchmarks, FIFA k-NN twin matching, and StatsBomb percentile calibration."
        url="/methodology"
      />
      <Navigation />
      <main className="container mx-auto px-4 py-12 max-w-4xl">

        <Link
          to="/"
          data-testid="methodology-back-link"
          className="inline-flex items-center gap-2 text-sm uppercase tracking-[0.18em] font-bold text-forest mb-6 hover:text-forest-pop transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Back
        </Link>

        {/* Header */}
        <header className="mb-12">
          <div className="text-[10px] uppercase tracking-[0.3em] font-bold text-forest mb-3">Methodology</div>
          <h1 className="font-barlow font-black uppercase text-4xl sm:text-5xl lg:text-6xl text-ink leading-[0.95]">
            How ScoutMePlay scores
          </h1>
          <p className="mt-5 text-base sm:text-lg text-ink/75 leading-relaxed max-w-2xl">
            Every report is built around the same four player-development pillars used across European
            Category-1 youth academies. This page explains exactly how we evaluate, benchmark, and tier players —
            so coaches, scouts, and parents can understand and trust the numbers.
          </p>
          <p className="mt-3 text-xs uppercase tracking-[0.22em] font-bold text-ink/40">
            Aligned with UEFA youth-development pillars · Not certified or endorsed by UEFA
          </p>
        </header>

        {/* Pillars */}
        <section data-testid="methodology-pillars" className="mb-14">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-5">The four pillars</h2>
          <div className="grid sm:grid-cols-2 gap-px bg-gray-border">
            {PILLARS.map((p) => (
              <div key={p.name} className="bg-surface p-6">
                <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest mb-2">{p.name}</div>
                <p className="text-sm text-ink/80 leading-relaxed">{p.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-ink/50 italic">
            Every sub-skill maps to one of these four pillars — the same framework used across European elite-youth coaching curricula.
          </p>
        </section>

        {/* Tier ladder */}
        <section data-testid="methodology-tiers" className="mb-14">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-5">The four-tier ladder</h2>
          <p className="text-sm text-ink/70 leading-relaxed mb-5 max-w-2xl">
            Each sub-skill is scored 1–10 and then placed into one of four tiers, calibrated to the player's
            age bracket and position. The tier shows <em>where this player sits today</em>, not where they
            might end up.
          </p>
          <div className="space-y-px bg-gray-border">
            {TIERS.map((t) => (
              <div key={t.key} className="bg-surface p-5 flex items-start gap-5">
                <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest min-w-[7rem] pt-0.5">{t.label}</div>
                <p className="text-sm text-ink/80 leading-relaxed">{t.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Age brackets */}
        <section data-testid="methodology-ages" className="mb-14">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-5">Age brackets</h2>
          <p className="text-sm text-ink/70 leading-relaxed mb-5 max-w-2xl">
            A 7/10 for first touch means something different at U11 than at U17. We calibrate every score
            against the typical milestone for the age bracket and position.
          </p>
          <div className="grid sm:grid-cols-2 gap-px bg-gray-border">
            {AGE_BRACKETS.map((a) => (
              <div key={a.key} className="bg-surface p-5">
                <div className="font-barlow font-black uppercase text-lg text-forest mb-1">{a.key}</div>
                <p className="text-sm text-ink/80 leading-relaxed">{a.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Position adjustments */}
        <section data-testid="methodology-positions" className="mb-14">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-5">Position adjustments</h2>
          <p className="text-sm text-ink/80 leading-relaxed max-w-2xl">
            Each attribute is weighted by position. A centre-back's tier ladder emphasises aerial duels,
            positioning, and 1v1 defending. A central midfielder's emphasises scanning, passing range,
            and press-resistance. A winger's emphasises acceleration, 1v1 dribbling, and final-ball delivery.
            Two players with the same overall score can sit in different tiers depending on their position.
          </p>
        </section>

        {/* Confidence */}
        <section data-testid="methodology-confidence" className="mb-14">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-5">Confidence scoring</h2>
          <p className="text-sm text-ink/80 leading-relaxed max-w-2xl mb-4">
            Every score carries a confidence level based on how many clear observations were available in the footage:
          </p>
          <ul className="space-y-2 text-sm text-ink/80">
            <li><span className="font-bold text-forest">High confidence</span> — 6 or more clear observations of the skill</li>
            <li><span className="font-bold text-forest">Medium confidence</span> — 3–5 observations</li>
            <li><span className="font-bold text-forest">Low confidence</span> — 1–2 observations; treat as directional</li>
            <li><span className="font-bold text-forest">Need more footage</span> — skill not observable in the clip; we mark it as such rather than guess</li>
          </ul>
        </section>

        {/* What we don't claim */}
        <section data-testid="methodology-disclaimer" className="mb-12 bg-cream-card border-l-4 border-forest p-6">
          <h2 className="font-barlow font-black uppercase text-xl text-ink mb-3">What we don't claim</h2>
          <ul className="space-y-2 text-sm text-ink/80">
            <li>· We are not UEFA-certified. We align with the same pillars used in UEFA elite-youth coaching education — that's it.</li>
            <li>· We don't publish childhood scores of professional players. Stylistic archetype comparisons describe <em>style</em>, not factual youth data.</li>
            <li>· We don't guarantee selection, signing, or progression to any club or academy.</li>
            <li>· Set-pieces from open play, off-camera defensive work, and goalkeeping moments are not assessable from outfield clips.</li>
          </ul>
        </section>

        {/* Data sources & calibration */}
        <section data-testid="methodology-data-sources" className="mb-12">
          <h2 className="font-barlow font-black uppercase text-2xl text-ink mb-3">
            Data sources &amp; calibration
          </h2>
          <p className="text-sm text-ink/70 leading-relaxed max-w-2xl mb-6">
            Every comparison and tier in this report is anchored against publicly verifiable senior-pro data —
            never against pure curated guesses. Three open datasets do the heavy lifting:
          </p>

          <div className="space-y-3">
            {/* StatsBomb */}
            <div data-testid="methodology-source-statsbomb" className="bg-surface border border-gray-border p-5">
              <div className="flex items-start gap-4">
                <div className="shrink-0 w-16 text-center">
                  <div className="font-barlow font-black text-3xl text-forest leading-none">SB</div>
                  <div className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/45 mt-1">
                    Source 1
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-barlow font-black uppercase text-lg text-ink leading-tight">
                    StatsBomb Open Data · UEFA Euro 2024
                  </h3>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-forest mt-0.5 mb-2">
                    51 matches · 493 unique players · 179 with ≥270 minutes
                  </div>
                  <p className="text-sm text-ink/75 leading-relaxed">
                    Used to calibrate the &quot;Pro Calibration&quot; panel on every report. For each player position,
                    we pre-computed per-90 percentiles (p25 / p50 / p75 / p90) of: pass completion, progressive
                    passes, key passes, xG, goals, dribbles completed, duels won, pressures, interceptions, ball
                    recoveries. The player&apos;s scores are then anchored to these distributions — so &quot;8/10
                    passing&quot; literally means &quot;top 25% of Euro 2024 starters at this position.&quot;
                  </p>
                  <p className="mt-2 text-xs text-ink/55">
                    <a
                      href="https://github.com/statsbomb/open-data"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-forest underline hover:text-forest-pop"
                    >
                      github.com/statsbomb/open-data
                    </a>{" "}
                    · License: CC BY-NC-SA 4.0 (StatsBomb Open Data terms) · Updated annually.
                  </p>
                </div>
              </div>
            </div>

            {/* FIFA */}
            <div data-testid="methodology-source-fifa" className="bg-surface border border-gray-border p-5">
              <div className="flex items-start gap-4">
                <div className="shrink-0 w-16 text-center">
                  <div className="font-barlow font-black text-3xl text-forest leading-none">FIFA</div>
                  <div className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/45 mt-1">
                    Source 2
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-barlow font-black uppercase text-lg text-ink leading-tight">
                    EA Sports FIFA · 7,473 senior pros
                  </h3>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-forest mt-0.5 mb-2">
                    22 attributes · 8 positions · normalised to a 0-10 scale
                  </div>
                  <p className="text-sm text-ink/75 leading-relaxed">
                    Used by the &quot;FIFA Data Twin&quot; panel to run a real k-nearest-neighbour similarity
                    search across senior pros. We pre-process the public Kaggle FIFA dataset into a slim
                    runtime file, map every FIFA attribute (ball control, dribbling, short-passing, vision,
                    composure, acceleration, balance, etc.) onto the same 0-10 scale we use for the player,
                    then compute per-attribute Euclidean RMSE.
                    <span className="block mt-1 font-semibold text-ink">
                      The reported similarity is hard-capped at 92%
                    </span>{" "}
                    — a youth player&apos;s scoring vector should never report 99% match to a peak-career pro;
                    capping it keeps the figure honest.
                  </p>
                  <p className="mt-2 text-xs text-ink/55">
                    Source: Kaggle FIFA 22 complete dataset (Stefano Leone) · attribute ratings © EA Sports,
                    used in a derived non-republished form for similarity matching only.
                  </p>
                </div>
              </div>
            </div>

            {/* FBref */}
            <div data-testid="methodology-source-fbref" className="bg-surface border border-gray-border p-5">
              <div className="flex items-start gap-4">
                <div className="shrink-0 w-16 text-center">
                  <div className="font-barlow font-black text-3xl text-forest leading-none">FBR</div>
                  <div className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/45 mt-1">
                    Source 3
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-barlow font-black uppercase text-lg text-ink leading-tight">
                    FBref &amp; Transfermarkt · career snapshots
                  </h3>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-forest mt-0.5 mb-2">
                    27 archetype career briefs · pre-computed offline
                  </div>
                  <p className="text-sm text-ink/75 leading-relaxed">
                    Powers the &quot;Career snapshot&quot; block on every archetype card — career appearances,
                    trophies, FBref per-90 stats (e.g. <em>&quot;Modric career pass completion ~88% across 13 La
                    Liga seasons&quot;</em>). All numbers are researched offline and shipped in
                    <code className="text-xs text-forest font-mono mx-1">archetypes.json</code>; we never
                    scrape FBref at runtime to respect Sports Reference&apos;s terms of service.
                  </p>
                  <p className="mt-2 text-xs text-ink/55">
                    Career data cross-referenced against FBref career-totals, Transfermarkt player profiles,
                    and the player&apos;s Wikipedia infobox at build time. Annual refresh.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <p className="mt-5 text-xs text-ink/55 italic leading-relaxed max-w-2xl">
            <span className="not-italic font-bold text-ink/65">Why pre-compute everything offline?</span>{" "}
            Runtime web scraping is fragile, slow, and legally grey. Every dataset above is licensed for the
            use described, processed into a slim runtime file at build time, then cited verbatim in the report
            — so a scout or parent can independently verify any number we cite.
          </p>
        </section>

        <footer className="text-xs text-ink/50 italic">
          Methodology version 1.1 — last updated Feb 2026 · Added StatsBomb Euro 2024 calibration + FIFA k-NN + FBref career snapshots.
        </footer>
      </main>
    </div>
  );
}
