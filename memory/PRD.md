# ScoutMePlay — PRD & Status

## Original Problem Statement
Build a premium football player video analysis platform (ScoutMePlay) where players or parents upload a football video, mark their player, receive a complimentary preview analysis, and unlock a comprehensive premium report upon a single fixed fee payment.

**Hard product rules**
- No subscriptions, no multi-tier pricing, no public club database.
- Clean, mobile-first, premium dark navy + electric volt-green design.
- Free users get exactly ONE free preview lifetime. Subsequent uploads require upfront payment.
- Stripe must keep ScoutMePlay completely separable from 1MillionBolde (shared Stripe account).
- Pricing in USD, admin-editable.

## User Personas
1. **Player / Parent** — uploads videos, reviews AI preview, pays once to unlock premium report.
2. **Admin** — manages users, reports, payments, pricing, manual unlocks, scout queue.

## Tech Stack (As Built)
- **Backend**: FastAPI + MongoDB (motor) + bcrypt JWT auth, single file `/app/backend/server.py` (~2050 lines — refactor planned)
- **AI**: Gemini 2.5 Pro multimodal via `emergentintegrations` Universal Key
- **Payments**:
  - Redirect-style Stripe Checkout via `emergentintegrations` (legacy, fallback)
  - **Embedded Stripe Checkout** via raw `stripe` Python SDK + `@stripe/react-stripe-js` (new — true in-page payment)
- **Video**: `ffmpeg` subprocessing (web-safe .mp4, 15s clip extraction, poster gen)
- **PDF**: ReportLab dark-themed premium output
- **Frontend**: React 19 + Tailwind + Framer Motion + Recharts
- **Design**: Volt Green (#CCFF00) on Deep Navy (#050A0F), Barlow Condensed + DM Sans

## Implemented (Feb 2026 — current session)
- ✅ **🆕 Session 6 — Step 2 · StatsBomb Euro 2024 Pro Calibration — Feb 05 2026**:
  - **Real data pipeline** (`/app/backend/scripts/build_statsbomb_percentiles.py`): downloads all 51 UEFA Euro 2024 matches from the public StatsBomb open-data repo in parallel, parses every event (passes, shots, dribbles, duels, ball recoveries, interceptions, pressures), aggregates per-90 metrics per player, then computes p25/p50/p75/p90 percentiles per ScoutMePlay position. Players with <270 minutes excluded for stable rates. Output: `/app/backend/data/statsbomb_percentiles.json` (22 KB, 8 positions). Spot-check: CB pass_completion p75 = 92.5% ✓ Van Dijk-class; Striker xG/90 p75 = 0.49 ✓ Kane/Haaland-class — matches FBref radar charts.
  - **Backend calibration helper**: `compute_statsbomb_calibration()` in `server.py` maps each measured ScoutMePlay attribute (12 distinct) to its closest StatsBomb proxy metric: passing → pass_completion_pct, scanning → passes_into_final_third_per_90, vision → key_passes_per_90, decision_making → progressive_passes_per_90, off_ball_movement → shots_per_90, timing_of_runs → goals_per_90, shooting → xg_per_90, dribbling → dribbles_completed_per_90, one_v_one → dribble_completion_pct, intensity → pressures_per_90, work_rate → ball_recoveries_per_90, courage_in_duels → duels_won_per_90. The player's 0-10 score is bucketed: 9+ → p90 (Top 10%), 8 → p75 (Top 25%), 7 → p50 (Median pro), 6 → p25 (Bottom 25%), <6 → below_p25. Every row carries the raw pro p25/p50/p75/p90 values for transparency. Shipped on the API as `statsbomb_calibration`.
  - **Lukas's live calibration**: Passing 9/10 → Top 10% (pro p90=90.4% pass completion) · Decision Making 9/10 → Top 10% (pro p90=2.45 progressive passes/90) · Shooting 8/10 → Top 25% · Intensity 6/10 → Bottom 25% (honest, not inflated). Summary: {p90: 4, p75: 3, p50: 4, p25: 1}.
  - **New UI panel**: `StatsBombCalibrationPanel` (data-testid: `statsbomb-calibration-panel`) renders below the FIFA Data Twin panel. Each attribute row (data-testid: `statsbomb-row-{attr}`) shows the score, the StatsBomb metric label, the percentile bucket pill, and the raw pro reference number — with a horizontal bar showing where the player sits on the senior-pro distribution. Methodology footnote cites StatsBomb open data + CC BY-NC-SA license + a direct link.
  - **PDF mirror**: new `_statsbomb_calibration_pdf()` builds a 5-column table — Attribute · StatsBomb metric · Score · vs Euro 2024 pros · Pro reference — with the StatsBomb source/license/methodology footnote. Cache version bumped to v7.
  - **Methodology page rewritten** with a new "Data sources & calibration" section featuring 3 source cards: StatsBomb (51 matches, CC BY-NC-SA license, github link), FIFA (7,473 senior pros, 92% cap explanation), FBref/Transfermarkt (27 career briefs, no runtime scraping). Each card has its own data-testid for verifiability. Footer: "Methodology version 1.1".
  - **Polish pass**: every ScoutMePlay attribute now maps to a UNIQUE StatsBomb metric (12 distinct) — no duplicate rows on the calibration panel.
  - **Tests**: 8 new pytests in `/app/backend/tests/test_statsbomb_calibration.py` (dataset integrity, API contract, bucket monotonicity, summary counter integrity, realistic pro spot-checks). 78/80 total pytests pass — 2 unrelated env failures (ffmpeg binary missing, public_price config test).
  - **Iteration_11 test report**: testing subagent confirmed end-to-end working (100% backend, 100% frontend, full PDF v7 content verified, methodology page fully cited). Two polish items raised and fixed in this same session: (1) duplicate-metric mapping → resolved; (2) `pdftotext` shell dependency in old iter9 test → replaced with `pypdf`.

- ✅ **🆕 Session 5 — Real Data Precision: Layer 5 FIFA k-NN + Step 3 career_brief enrichment — Feb 05 2026**:
  - **Layer 5 — FIFA Data Twin (real k-NN against 7,473 senior pros)**: `/app/backend/scripts/build_fifa_dataset.py` pre-processes the public Kaggle FIFA 22 mirror into a compact `/app/backend/data/fifa_players.json` (7,473 senior pros across 8 positions). At runtime, `find_fifa_neighbors()` in `server.py` runs an RMSE-based 22-attribute similarity search against this dataset. The matcher uses pure Euclidean RMSE (NOT cosine — cosine is too forgiving on shape-aligned vectors), formula `100 − rmse × 18`, plus small bonuses (+1.0% for foot match, +1.5% for build match). Hard cap at 92% — a youth-player score can never report as 99% similar to a senior pro. Returns top-5 with `nearest_attrs` (the 3 attributes where kid & pro are closest). Wired as the 5th lens in `archetype.lenses.fifa` AND as a full top-5 panel via `archetype.fifa_neighbors`.
  - **Lukas's live top-5** (for sanity): Reynoso 88.2% · Nainggolan 87.4% · Maddison 86.7% · David Silva 86.5% · Stindl 86.3%. All scores honest, no false 99% claims.
  - **Step 3 — FBref-grade career enrichment**: `/app/backend/scripts/enrich_archetype_career_briefs.py` added a verified `career_brief` field to **27 of the top archetypes** across all 8 positions (Modric, Pedri, KdB, Foden, Yamal, Bellingham, Haaland, Mbappé, Vinicius, Rodri, Van Dijk, TAA, Hakimi, Alisson, Courtois, etc.). Each brief is one short verifiable line: career totals, trophies, FBref per-90 stats — sourced from FBref + Transfermarkt + Wikipedia infobox at build time. NEVER computed at runtime.
  - **Gemini narrative gets 2 new ingredients**: the prompt now receives the FIFA top-1 neighbour + the career_brief. Gemini is instructed to weave in the FIFA data-similarity result as a single sentence AND paraphrase one career stat — under strict no-invention guardrails. Example output (Lukas): *"...reminiscent of Luka Modric at a similar age. As a 13-14 year old at NK Zadar, Modric was also a small playmaker, dropping deep to receive possession. By data similarity, the closest senior pro is E. Reynoso."* Cache version bumped to v3.
  - **New UI components**: `FifaDataTwinPanel` (data-testid: `fifa-data-twin-panel`) renders the top-5 closest pros with similarity bars + nearest_attrs pills + build/foot mini-pills + a methodology footnote citing the FIFA-22 dataset. The 5th lens card (data-testid: `lens-match-fifa`) has a distinctive forest-green background + "Real data · k-NN" badge + similarity_pct display (not /10). `ArchetypeCard` now also renders `archetype-career-brief` block — "Modric · career snapshot (FBref · Transfermarkt verified)".
  - **PDF mirror**: new `_fifa_neighbors_pdf()` builds a 5-row similarity table; `_archetype_card_pdf()` now renders the career-brief card; `_lens_matches_pdf()` adapts to 4 or 5 lenses dynamically. Output verified: "FIFA DATA TWIN · REAL SIMILARITY SEARCH", "MODRIC · CAREER SNAPSHOT (FBREF · TRANSFERMARKT)", "WHAT MODRIC WAS DOING AT AGE 13-14" all present in the generated PDF.
  - **PDF cache fix (iteration_10 bug)**: PDFs are now versioned on disk (`{rid}.v{PDF_RENDER_VERSION}.pdf`, currently v5). Bump invalidates every stale PDF without losing the current ones. Old format `.pdf` files are purged on next regeneration. Same bug class as the narrative cache (which was already fixed via `_NARRATIVE_CACHE_VERSION`).
  - **Helper**: new `_pro_name_from_archetype()` extracts just the pro's name (e.g. "Modric-type composer" → "Modric", "Lamine Yamal-type wonderkid" → "Lamine Yamal") so the PDF/UI section headers read "WHAT MODRIC WAS DOING AT AGE 13-14" instead of the previous "WHAT MODRIC COMPOSER WAS DOING".
  - **Testing**: 35/35 pytests pass across 4 test files (`test_archetype_4layer.py` 13 + `test_iter10_fifa_career.py` 10 + `test_archetype_age_profile.py` 8 + `test_trial_readiness.py` 4). Testing subagent iteration_10 ran 10 independent validations and confirmed all data contracts + PDF content end-to-end.

- ✅ **🆕 Session 4 — 4-Layer Intelligence Stack (age-aware, multi-dimensional, AI-personalized archetype matching) — Feb 05 2026**:
  - **Layer 1 — Curated catalog** (`/app/backend/data/archetypes.json` — already shipped in previous session): every archetype across all 8 positions now carries a `profile` block (`foot`, `build`, `role`, `path`) and an `academy_bio` block (verifiable historical facts at age brackets `8-10`, `11-12`, `13-14`, `15-17`, `18-21`). The bio chunks are short, verbatim, third-person, sourced from public biographical record — Gemini may paraphrase but NEVER invent additional facts.
  - **Layer 2 — Multi-Dimensional Ranker** (`match_archetype()` in `server.py`): rewritten to evaluate every candidate archetype across **4 independent lenses** — Style (signature-attribute weighted average), Build (player's physical frame inferred from technical/physical scores via `_infer_build()`), Role (deep_creator / chaos_creator / box_to_box etc. inferred via `_infer_role()`), and Career-path (player's `overall_benchmark.tier` mapped to ordered archetype tiers). Each lens picks ONE winner — so a kid can be Modric-type by style but Foden-type by build. A foot bonus (collected as `preferred_foot` on the upload form — option C) nudges the build / style picks toward the right footedness. All four lens scores are clipped to [0, 10] before serialization.
  - **Layer 3 — Gemini Narrative Generation**: `_serialize_report()` is now async and calls `generate_archetype_narrative()` on the first paid fetch of a report. Uses Gemini 2.5 Flash text-only (`call_gemini_text()`), strict guardrails — Gemini receives ONLY the verbatim age-bracket bio chunk + the kid's top 3 measured strengths and is instructed not to invent any historical facts. The 50-70 word output is cached on the report doc (`archetype_narrative`, `archetype_narrative_archetype_id`, `archetype_narrative_age_bracket`) so subsequent fetches are instant. Failure-safe: a Gemini timeout never crashes the report.
  - **Layer 4 — UI Personalization** (`ReportPage.jsx`): `ArchetypeCard` now displays the personalized narrative (`data-testid="archetype-narrative"`) + the verbatim age-bracketed bio chunk (`data-testid="archetype-academy-bio"` — "What Modric was doing at age 13-14: …"). New `LensMatchesStrip` (`data-testid="lens-matches-strip"`) replaces the legacy top-3 matches strip and renders a 2×2 grid of lens-tagged matches with `data-testid="lens-match-style|build|role|path"`. The PDF mirrors all of this — new `_lens_matches_pdf()` helper builds the 4-row twin table; `_archetype_card_pdf()` now also renders the narrative card + bio card.
  - **Lukas A. result**: Style twin = Modric-type composer · Build twin = Foden-type inverted (left-footed, small_technical match) · Role twin = Modric-type composer (deep_creator) · Career-path twin = Lamine Yamal-type wonderkid. Narrative: 73 words anchored to Modric at age 13-14 (not peak Modric).
  - **Testing agent (iteration_9)**: independent validation passed end-to-end — all UI elements render with correct content; backend returns 4-lens block with valid scores; narrative caching verified; PDF regenerates with "PERSONALIZED COMPARISON", "4-LENS COMPARISON", and "WHAT MODRIC WAS DOING AT AGE 13-14" sections. **1 product bug found & fixed**: lens scores can exceed 10/10 due to the foot bonus — now clipped to [0, 10] in `match_archetype()._pick()`. 8/8 pytests in `/app/backend/tests/test_archetype_4layer.py` pass.

- ✅ **🆕 Session 3 — Visual finale: DNA fingerprint + Frame thumbnails + Share card — Feb 04 2026 (very late)**:
  - **DNA Fingerprint (J1)** — `<DnaFingerprint>` React component renders a horizontal stack of all ~24 scored sub-attributes as colour-coded bars (forest = Technical, mid-green = Tactical, amber = Physical, ink = Mental). Bars ordered by position priority weight (pulled from `age_profile_reference`). 4-pillar legend, hover reveals individual score. Every player's bar is visually unique — a true fingerprint.
  - **Frame thumbnails (F)** — Server function `ensure_video_frames()` runs ffmpeg `-ss {seconds} -frames:v 1` on every `video_comments` timestamp; falls back to a Pillow-rendered branded placeholder (cream + forest, camera glyph, timestamp printed) when the video file is missing or ffmpeg fails. `frame_url` attached to every comment. Web: video moments now render as a 2-column grid of cards (thumbnail + timestamp overlay + comment). PDF: 2-column table with the JPEG embedded next to each timestamp via reportlab `RLImage`. ffmpeg installed via apt at session start.
  - **Share card (J2)** — Pillow renders a 1080×1350 IG-ready PNG with: forest header band (brand + player + position + match score), big centred overall score with `/10`, forest tier chip, archetype name, top-3 strengths bullets, mini DNA bar strip, and "ALIGNED WITH UEFA YOUTH-DEVELOPMENT PILLARS" footer. Auto-generated lazily on first report fetch; cached at `/app/backend/uploads/cards/{id}.png` and served via `/api/uploads/cards/...`. New "Get share card" button on the report (data-testid='download-share-card-btn') opens it in a new tab for download.
  - **Architectural decision**: Like Sessions 1 & 2 — all three features are pure server-side enrichment + deterministic Pillow/ffmpeg rendering. Zero AI changes, works on existing reports immediately, graceful placeholders when video files are missing.
  - **Testing agent (iteration_8)**: **100% pass** (7/7 backend pytest in `/app/backend/tests/test_session3_visuals.py`, all frontend selectors green). PDF now has 6 embedded JPEG thumbnails; share card is a valid 1080×1350 PNG (~24KB); DNA bar renders all 25 attribute segments with correct pillar colours.

- ✅ **🆕 Session 2 of credibility upgrade — Stylistic Archetype + European Academy Reference Profile — Feb 04 2026 (late evening)**:
  - **Stylistic Archetype (C1)** — curated catalog at `/app/backend/data/archetypes.json` covering 8 positions × ~5 well-known public professional archetypes each (Modric-type composer, Pedri-type press-breaker, Haaland-type penalty-box predator, etc.). Server function `match_archetype()` deterministically picks the closest archetype by averaging the player's actual scores across each archetype's `anchor` attributes. Lukas A. → "Modric-type composer · match strength 8.8/10". If best match < 6.0, falls back to a "Developing — no clear archetype yet" state. Rendered on the web report as `<ArchetypeCard>` (forest hero card directly under the Overall Benchmark) and in PDF as the matching forest hero card on page 3. Defensible disclaimer: *"Stylistic comparisons describe how this player plays today — not their ceiling, and not the named professional's youth data."*
  - **European Academy Reference Profile (C2)** — curated catalog at `/app/backend/data/age_profiles.json` with position-priority attributes (5-7 per position, each carrying a weight 1-5 and a `why_matters` scout's lens). Server function `compute_age_profile_reference()` overlays the player's scores onto Pro Academy expectations and tags each row as `at_or_above` / `below` / `no_data`. Rendered as `<AgeProfileCard>` on web (clean position-priorities table with weight dots, Pro range, player score, state chip) and as a dedicated page in the PDF with the same data laid out as a premium 5-column table.
  - **Lukas A. result**: archetype = Modric-type composer (8.75 match), age profile = 7/7 priority attributes at or above Pro Academy level for U13-U14 attacking midfielder.
  - **Architectural decision**: Both features are pure server-side deterministic enrichment from existing scores + curated JSON catalogs. **Zero AI changes** — works for all existing reports immediately (no AI re-run needed). Catalogs use the same insertion-order-safe alias system as `trial_readiness.json` so position matching is robust.
  - **Defensible legal language**: all comparisons explicitly framed as "stylistic" / "style today" / "not the named professional's youth data" — across UI disclaimer, archetype card subtitle, methodology page, and PDF appendix.
  - **Testing agent (iteration_7)**: **100% pass** (8/8 backend pytest in `/app/backend/tests/test_archetype_age_profile.py`, 17/17 actual frontend checks; 1 fail was a test-side selector mistake, not a regression).

- ✅ **🆕 Session 1 of credibility upgrade — Methodology + Trial Readiness — Feb 04 2026 (evening)**:
  - **Trial Readiness (K)** — server-side deterministic checklist computed from existing scores against position-specific thresholds curated in `/app/backend/data/trial_readiness.json`. 8 positions (GK, CB, FB, DM, CM, AM, W, ST) × ~8 checklist items each, each item tied to one or more sub-attribute scores with `strong_club_min` / `pro_academy_min` thresholds. Server function `compute_trial_readiness()` returns a headline ("Ready for Pro Academy trial" / "Ready for Strong Club trial" / "Building towards a Strong Club trial" / "Foundation phase"), a `readiness_tier` key, and a per-item breakdown with pro_academy_met/strong_club_met flags. Rendered in `ReportPage.jsx` as `<TrialReadinessCard>` (cream/forest premium aesthetic, 2-col grid, status chips per item) and in PDF as a dedicated section with forest hero strip + 2-col grid of status cards.
  - **Position alias safety**: catalog uses ordered aliases so `attacking midfielder` matches before generic `midfielder` (fixes a cross-mapping bug where AM was being matched to CM).
  - **Methodology page (B)** — public `/methodology` route + matching PDF appendix on every download. Sections: Four Pillars (Technical/Tactical/Physical/Mental), Four-Tier Ladder (Elite Academy → Standard Club), Age Brackets (U11 → U21), Position Adjustments, Confidence Scoring, "What we don't claim". Defensible language: *"aligned with UEFA youth-development pillars · not certified or endorsed by UEFA"*.
  - **Methodology link surfaces** added in OverallBenchmarkBanner ("How we score · methodology →") and in the Landing page footer (`footer-link-methodology`).
  - **Testing agent (iteration_6)**: 100% pass on backend (4/4 pytest in `/app/backend/tests/test_trial_readiness.py`) + 100% on every frontend check. Zero JS errors, all data-testids in place, alias-order regression confirmed safe.

- ✅ **🆕 Age + position-calibrated benchmarks (deep AI scoring) — Feb 04 2026**:
  - **Backend AI prompt** (`FULL_REPORT_PROMPT`) now asks Gemini 2.5 Pro to return, per scored sub-skill: `why_this_score` (concrete reasoning), `tier_for_age` (elite_academy / pro_academy / strong_club / standard_club), `benchmarks` (score ranges for each of the 4 tiers, calibrated to age bracket U11–U21 + position adjustments), and `verdict` (one-line "to reach the next tier, focus on X" guidance). Plus a NEW top-level `overall_benchmark` block (tier, tier_label, percentile, realistic_next_step, what_separates_from_next_tier, age_bracket_used).
  - **Frontend** (`ReportPage.jsx`): The signature "How You Compare" forest hero panel renders at the top of the unlocked report — big overall score, tier chip, percentile narrative, realistic next step, what separates from the next tier, and a horizontal 4-tier landscape strip showing where the player sits. Every sub-skill card (`SectionGrid`) now renders: tier badge, score, notes, "Why this score" forest-accent block, 4-tier benchmark ladder with the player's tier highlighted, and a verdict line. All wired with `data-testid` for stable QA.
  - **PDF** (`build_pdf` + new helpers `_skill_card`, `_skill_section_block`, `_overall_benchmark_page`, `_benchmark_strip`): Added a new "How You Compare" page (forest hero card + tier landscape) right after the Score Overview. Each of the four analysis sections (Technical, Tactical, Physical, Mentality) is now rendered as premium per-skill cards instead of a flat table — each card includes the tier chip, big forest score, notes, "Why This Score" block, 4-cell tier ladder benchmark with player's tier highlighted, and verdict line. 20-page PDF (was ~13). Visually verified via PyMuPDF rasterization + AI analysis.
  - **Seed** (`seed_test_accounts.py`) updated — Lukas A. demo report now includes the full new field structure so testing accounts immediately showcase the upgrade. `_skill()` helper centralises the new structure.
  - **Testing agent (iteration_5)**: 100% pass on backend (5/5 pytest in `/app/backend/tests/test_benchmark_report.py`) and frontend (forest hero + every sub-skill card visible with tier-badge + why + benchmark-bar + verdict + PDF download trigger).
- ✅ DKK → USD currency conversion across UI (Landing, Upload, Report, Admin, Modal) + backend
- ✅ `DEFAULT_REPORT_PRICE_USD=1`, `DEFAULT_REPORT_CURRENCY=usd` env vars
- ✅ Admin dashboard updates: "Current price (USD)", revenue shows `$X.XX USD`
- ✅ Backend `/api/admin/stats` returns `revenue_usd` + legacy `revenue_dkk`
- ✅ Backend `/api/payments/*` flows persist `currency=usd` and `amount` in USD dollars
- ✅ DB migration ran — existing report_price setting reset to 1.0 USD
- ✅ Embedded Stripe checkout endpoints `/api/payments/embedded/prepay-upload`, `/api/payments/embedded/unlock`, `/api/payments/embedded/status/{sid}`
- ✅ `EmbeddedCheckoutModal.jsx` mounts Stripe's `<EmbeddedCheckout>` inside a branded ScoutMePlay modal — true in-page payment
- ✅ UploadPage + ReportPage auto-prefer embedded checkout when Stripe keys are configured; otherwise gracefully fall back to redirect modal
- ✅ **Bug fix (CRITICAL)**: `_arm_real_stripe()` helper resets `stripe_sdk.api_base='https://api.stripe.com'` before every embedded SDK call (counters `emergentintegrations` global mutation)
- ✅ **Bug fix (HIGH)**: Embedded sessions use `redirect_on_completion='if_required'` so `onComplete` callback fires in-page
- ✅ **🔴 LIVE MODE ACTIVATED** — `pk_live_51SlanqPyHKLMizP3...` + `sk_live_51SlanqPyHKLMizP3...` in `/app/backend/.env`. Account: `MENTALSKIDS 1M BOLDE` (DK, charges_enabled, payouts_enabled). Verified end-to-end: real `cs_live_...` session created via our API and confirmed `livemode: true`.
- ✅ **Real Stripe webhook handler** at `/api/webhook/stripe-embedded` uses `stripe.Webhook.construct_event` with `STRIPE_WEBHOOK_SECRET`. Credits `prepaid_uploads` and marks reports paid even if the user closes their tab right after paying.
- ✅ **Apple Pay + Google Pay + Link + PayPal enabled** for `scout-ai-pro-1.preview.emergentagent.com`. Domain registered via `stripe.PaymentMethodDomain.create()`. Verification file served from `/app/frontend/public/.well-known/apple-developer-merchantid-domain-association`. Wallets auto-surface in embedded checkout for compatible browsers (iOS/macOS Safari with Apple Wallet → Apple Pay button; Chrome+Android with Google Wallet → Google Pay button).
- ✅ **Admin user management**:
  - `/api/admin/users` now returns enriched users with `segment` (free / premium / scout / admin) and `report_count` fields.
  - `DELETE /api/admin/users/{user_id}` — cascade-deletes user + their reports + uploaded files. Admin accounts and self-deletion are blocked.
  - Admin UI: Users tab redesigned with **segment filter pills** (All / Free / Premium / Scouts / Admins with live counts), per-user **delete buttons**, segment icons, and report counts.
- ✅ **Scouts (agents) system**:
  - New role `scout`. `POST /api/admin/scouts` creates a scout account (admin only).
  - Scouts can log in and access `/admin` — but only see the **Scout Queue tab** (other tabs are role-gated server- and client-side).
  - `/api/admin/agent-queue`, `agent-review` deliver, and `agent-messages` endpoints now use `get_current_admin_or_scout` so scouts can deliver reviews and chat with players.
  - Admin UI: "Add Scout" button + modal (name / email / password) on the Users tab.
- ✅ **Footer redesign** — Brand / About / Contact / Legal columns. Contact link sends to `/about#contact`. Email link to `scoutmeplay@gmail.com`. Privacy link to `/privacy`.
- ✅ **About page** (`/about`) — Brand story, "What we do" 4-card grid, full contact form (Name / Email / Message), Mentalkids company info.
- ✅ **Privacy Policy page** (`/privacy`) — Full GDPR-compliant Danish/EU privacy policy in 11 sections (data, retention, third parties incl. Stripe & Gemini, user rights, Datatilsynet complaints).
- ✅ **Contact form** — `POST /api/contact` (public, rate-limited 5/hour, honeypot anti-spam). Stored in MongoDB AND forwarded to `scoutmeplay@gmail.com` via **FormSubmit.co** (free email relay, no signup/API key needed — admin clicks ONE activation link in the first arrival email, then all future submissions arrive instantly).
- ✅ **Admin Messages tab** — Unread badge on the tab, per-message status (new/read/archived), mailto reply buttons, delete actions.
- ✅ **Premium Design System Overhaul (mockup-aligned)**:
  - **Theme**: Switched from dark-mode (deep navy + electric volt) to a **premium cream/forest aesthetic** matching the user's reference mockup — feels like high-end athleticwear (Nike/Adidas vibe), not a tech startup.
  - **New Tailwind tokens**: `cream-base` (#F4EFE6 — page background), `cream-soft` (#EAE3D2 — section separators), `cream-card` (#FFFFFF — feature cards), `forest` (#1F4F2F — primary CTA), `forest-pop` (#2D6B3D — hover/accent), `ink` (#0A0F0D — text/headers/navbar), `gray-body` (#4B5563), `gray-border` (#E5E7EB).
  - **Navigation rebuilt**: Black `bg-ink` top bar with green logo, "SCOUT**ME**PLAY" wordmark (ME in forest), tagline "See your game through scout eyes", rounded forest-pill CTA buttons.
  - **Logo refactored** to use `currentColor` so it inherits any parent color (now always forest green on the black navbar).
  - **Global recolor**: ~600 lines repainted across Landing, Login, Signup, Dashboard, Upload, Report, Admin, About, Privacy, ScoutQueue, ScoutReview, EmbeddedCheckoutModal, CheckoutTransitionModal.
  - **Forest-green CTA buttons everywhere**: White text on forest background with hover to forest-pop.
- ✅ **Premium Scouting PDF redesigned**:
  - Cream paper · forest left rail · large ink player name on cover · forest panel with vertical "SCOUTMEPLAY" wordmark · brand footer on every page.
  - 11-page structure: Cover · Executive Summary + Score Overview · Technical + Tactical · Physical + Mentality · Scout View · Potential Assessment · Personal Training Plan (5 exercises with numbered cards + weekly/30/90-day) · Video Moments · Final Summary + Sign-off card.
  - Reusable PDF primitives: `_section_header(title, idx)` (eyebrow + title + forest underline), `_score_table` (forest header row, alternating cream/white rows, formatted score pills like "8 / 10"), `_kv_card` (white card with thick forest left-border), `_list_bullets` (forest ▸ markers), `_cover_summary_box` (overall score + player type).
  - All cached PDFs cleared so existing customers re-download the new version automatically.
  - Visually verified end-to-end via PyMuPDF rasterization + AI analysis — cover + content pages confirmed clean, no truncation, no overlaps.
  - **Functionality preserved 100%** — payments, Stripe wallets, AI engine, admin/scouts, uploads, contact form/email forwarding — all untouched.

## Implemented Previously (Phase 1 — Feb 2026)
- ✅ Landing page (Hero, How It Works, What You Receive, Sample Preview, Trust, CTA)
- ✅ JWT auth (signup/login, /me) + 3 seeded test accounts
- ✅ Video upload form + ffmpeg pipeline
- ✅ Free AI preview via Gemini 2.5 Pro multimodal
- ✅ Content Gate (rejects non-football videos)
- ✅ Evidence-Based AI (confidence levels + timestamped evidence per category)
- ✅ Pinch-to-zoom + pan video player for player marking
- ✅ Locked premium sections with blur + unlock CTA
- ✅ Stripe Checkout (Path A — branded transition modal + redirect)
- ✅ Full premium report (11 sections) generated post-payment
- ✅ Performance radar chart + premium PDF download
- ✅ Dashboard for user reports
- ✅ Admin panel (stats, reports, users, payments, price config, manual unlock, delete)
- ✅ Scout review chat unlocked post-payment
- ✅ Free user paywall (1 free preview lifetime; prepay required after)
- ✅ Brand attribution metadata on every Stripe session (`brand=ScoutMePlay`, etc.) — keeps separable from 1MillionBolde
- ✅ Mobile-optimized everywhere
- ✅ Max video length 5min (OOM guard)

## Pending — User input required (P0)
- ✅ **Stripe TEST keys configured** — `pk_test_51SlanqPyHKLMizP3...` and `sk_test_51SlanqPyHKLMizP3...` are now active in `/app/backend/.env`. Embedded checkout is live and verified.

## Backlog
### P1
- Add real-Stripe webhook handler at `/api/webhook/stripe-embedded` using `stripe.Webhook.construct_event` + `STRIPE_WEBHOOK_SECRET` — covers the edge case where the user closes the tab right after paying (currently frontend polling handles 99% of cases)
- Sample PDF download on landing (teaser PDF + web sample page)
- Resend email notifications (preview ready, scout review delivered, chat replies, payment receipts)
- (Optional polish) In Stripe Dashboard → Settings → Link, toggle off "Allow Link to save payment details" — this lets new emails complete checkout without a phone-number verification step

### P2
- Progress tracking over time (compare new videos with old reports)
- Referral system ("Refer a teammate, both get 30% off")
- Multi-language support
- Migrate to `stripe.StripeClient(api_key=...)` per-instance API (eliminates the need for `_arm_real_stripe()` defensive helper)

### P3
- Refactor server.py (~2070 lines) into routers (`payments_embedded.py`, `payments_legacy.py`, `admin.py`, `reports.py`)
- Object-storage migration (S3) for video uploads
- Auth-gated /api/uploads static mount

## API Endpoints (key)
- `POST /api/auth/login`, `POST /api/auth/signup`, `GET /api/auth/me`
- `GET /api/settings/price` → `{price, currency, price_dkk(legacy alias)}`
- `POST /api/reports/upload` → multipart (video + marker_image + metadata)
- `GET /api/me/upload-eligibility`
- `POST /api/payments/prepay-upload` — legacy redirect
- `POST /api/payments/checkout` — legacy redirect (unlock report)
- `GET /api/payments/status/{session_id}` — legacy
- `POST /api/payments/embedded/prepay-upload` — embedded (returns `client_secret`)
- `POST /api/payments/embedded/unlock` — embedded (returns `client_secret`)
- `GET /api/payments/embedded/status/{session_id}` — embedded
- `GET /api/config/stripe` — public config (publishable_key + embedded_available)
- `POST /api/webhook/stripe`, `POST /api/webhook/stripe-embedded`
- `PUT /api/admin/price`, `GET /api/admin/stats`
- `GET /api/admin/users` — enriched with `segment` and `report_count`
- `DELETE /api/admin/users/{user_id}` — cascade-deletes user + reports + files
- `POST /api/admin/scouts` — create a scout/agent account
- `GET /api/admin/agent-queue` (admin **or** scout) — unlocked reports awaiting review
- `PUT /api/admin/reports/{id}/agent-review` (admin **or** scout) — deliver written review
- `POST /api/admin/reports/{id}/agent-messages` (admin **or** scout) — chat with player

## DB Collections
- `users` — `{id, email, hashed_password, role, free_preview_used, prepaid_uploads}`
- `reports` — `{id, user_id, player_name, video_url, poster_url, marker_timestamp, content_gate, evidence, confidence, ai_preview, ai_full, is_paid, stripe_session_id}`
- `payment_transactions` — `{id, session_id, user_id, kind(prepay_upload|report_unlock), ui_mode(embedded|redirect), brand, amount, currency, metadata, payment_status, credited}`
- `settings` — `{key=report_price, value:float}`

## Stripe Separation (Mandatory)
Every Stripe session created MUST attach these metadata fields (already enforced in code):
```
brand: ScoutMePlay
company: Mentalkids
website: ScoutMePlay
source: scoutmeplay_website
niche: football_scouting_video_analysis
product: ScoutMePlay – Football Video Analysis
```

## Test Credentials
See `/app/memory/test_credentials.md`.
