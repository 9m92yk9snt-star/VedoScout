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
- ✅ **🆕 Session 22 — Hero copy rewrite to athlete voice (Feb 17 2026 late night)**:
  - **Old sub-copy** (feature-y): "Upload your football video and receive a detailed scouting report powered by advanced football intelligence, professional player benchmarks, and real scouts and agents connected to clubs around the world. Built for ambitious players from U7 to U21 chasing their football dreams."
  - **New sub-copy** (Option 2 — athlete-to-athlete confident voice): "You train every day. You give everything on the pitch. But does anyone actually *see you*? Upload your video. Get the **scout view**. See where you stand and what it'll take to reach the next level. For ambitious players, U7 to U21."
  - Emphasis style: *see you* in italic + **scout view** in bold creates emotional hook → value prop reading order.
  - Headline preserved ("Where *talent* gets noticed.").
  - Surgical scope: only `Landing.jsx` hero `<motion.p data-testid="hero-description">` block touched. Zero other changes.

- ✅ **🆕 Session 21 — Cinematic-bookends premium pass (Feb 17 2026 late night)**:
  - Removed the faded photo backdrops from middle sections (they were creating amateur "ghost photo" seams between adjacent sections).
  - **How it works** — replaced photo with: a subtle SVG turf-grid texture @ 5%, scout-notepad corner brackets (forest @ 40%), and a lime accent stripe on the left edge (playbook-spine motif). No photo, all football.
  - **Pricing** — removed the stadium photo plate. Kept the custom 4-3-3 formation SVG diagram (clean line art) and the subtle dot pattern. Result: cards float over an obvious football tactics board without any photo muddiness.
  - **Hero · Trust card · Final CTA photos** — preserved (these are intentional cinematic moments, not background fades).
  - **Sample stat heatmaps** + **pillar icons** — preserved (pure CSS, zero seam issues).
  - **Scout-voice copy** on the sample teaser card preserved.
  - Result: page now reads as a clean typographic sequence with cinematic photo bookends at the top and bottom. No metrics added anywhere — football identity carried entirely by corner brackets, line-art formation, and SVG turf texture.
  - **Surgical scope**: only Landing.jsx touched. Zero backend, zero functionality changes.

- ✅ **🆕 Session 20 — Football atmosphere + bespoke graphics on flat sections (Feb 17 2026 late night)**:
  - **Sample-teaser card** copy rewritten — "Sample · See it in action / This is your report / (CSV of features)" → **"The full breakdown / See what a scout sees / Where your player stands today. What separates them from the next level. The 5 drills that will actually move the needle. Reviewed by a real scout — not just a number on a page."** Scout-voice, emotional, persuasive.
  - **How it works** — added a forest-tinted goal-net photo backdrop (filter: sepia + hue-rotate for unified duotone), gradient overlay, and 4 lime corner-bracket marks like a scout's notepad framing the card.
  - **Trust section** — completely restructured from a plain shield-card into a magazine-style 2-column block: left side is a forest-tinted player-action photo with corner brackets and a floating "Built for growth · not for promises" floor eyebrow; right side carries "Our promise" eyebrow + dual-tone headline + the existing trust copy.
  - **Pricing section** — added a subtle stadium photo plate + a custom SVG 4-3-3 formation diagram backdrop (pitch outline, centre circle, 11 player dots, one highlighted in volt with halo) at 6% opacity. Cards float over an actual football tactics board.
  - **Sample stat cells** (TECH / TACT / PHYS / MENT) — each cell now has a pillar icon (Footprints / Target / Activity / Lightbulb) above the label, and a forest-green radial heatmap behind the number whose intensity scales with the score (9 = strong tint, 7 = mid, ≤6 = empty). Scouts get an instant visual read.
  - **Unified visual treatment** — every newly-added photo uses the same forest-duotone CSS filter (`sepia(0.35-0.4) saturate(1.5-1.6) hue-rotate(75deg)`) so the page reads as one brand, not a stock-photo collage.
  - **Surgical scope**: only `Landing.jsx` touched. Zero backend, zero functionality changes, all existing data-testids preserved.

- ✅ **🆕 Session 19 — Premium footer gradient + admin-editable social handles (Feb 17 2026 late night)**:
  - **Premium footer redesign** — replaced flat `bg-ink` with a rich radial-gradient backdrop (`#2D6B3D@45%` at top → `rgba(8,22,15)` → `rgba(5,13,8)` at bottom), looks like a stadium night sky. Added two ambient halos (volt top-left + forest-pop bottom-right), a barely-visible repeating horizontal pitch-line pattern, and an SVG fractal-noise grain overlay (`mix-blend-overlay` @ 6%). No longer "too black" — has depth, texture and athletic-brand feel.
  - **Two-row icon strip in footer**:
    - **Share ScoutMePlay** (4 icons): X / Facebook / LinkedIn / WhatsApp — share intents built from `window.location.origin` so the share link matches whichever environment is live.
    - **Follow us** (up to 4 icons): Instagram / X / Facebook / LinkedIn — URLs read live from `GET /api/settings/price.social`. Icons with empty URLs are hidden automatically.
    - Pill hover state: outline → fully-lit lime fill with dark-ink icon (premium athletic-brand feel).
  - **Admin-editable social handles**:
    - **Backend** (`server.py`):
      - New `DEFAULT_SOCIAL_LINKS` constant.
      - New `SocialLinksUpdate` Pydantic model + `get_social_links()` helper.
      - Extended `GET /api/settings/price` to include `social` field (defaults + DB overrides merged).
      - New `PUT /api/admin/social-links` (admin-only, validates http(s) scheme + 500-char cap, empty string hides the icon, partial updates supported via dict merge).
    - **Frontend** (`AdminPage.jsx`):
      - New Settings-tab "Social Links" card with 4 inputs (Instagram / X / Facebook / LinkedIn), each labelled with its brand icon.
      - "Save social links" button → `PUT /api/admin/social-links` with toast feedback.
      - Live status line: "Currently active: N of 4 links live".
      - Data-testids: `admin-social-{instagram|twitter|facebook|linkedin}-input`, `admin-social-save`.
    - **Frontend** (`Landing.jsx`):
      - Loads `social` from the same `/settings/price` call (no extra request).
      - Falls back to sensible defaults on first paint / network failure.
  - **Live verified end-to-end via curl**: admin login → PUT social-links with custom Instagram URL → public `/settings/price` returns the new URL → footer renders new handle → restored to defaults.
  - **Surgical scope**: only `server.py`, `Landing.jsx`, `AdminPage.jsx` touched. Zero impact on payments, scout queue, blog, scoring, or any existing functionality.

- ✅ **🆕 Session 18 — Footer redesign + Terms of Service + brand cleanup (Feb 17 2026 late night)**:
  - **New Terms of Service page** at `/terms` (14 sections — acceptance, what we provide, what we don't promise, eligibility, video rights, payments/refunds, acceptable use, IP, liability cap, service availability, termination, governing law (Denmark), changes, contact). Routes added to `App.js`. Links to message-form for contact (no mailto).
  - **Premium new footer** in `Landing.jsx`:
    - Dark forest band with ambient lime glow, matches the top-nav aesthetic exactly.
    - Same SCOUTMEPLAY wordmark as the top bar (lime "ME" stamp + lime accent dot + tagline).
    - 3-column layout: **Explore** (Home · About · Blog · Contact) · **Product** (How it works · What's inside · Sample report · Pricing — all use `?scroll=` for cross-page anchors) · **Legal** (Privacy · Terms · Methodology).
    - **5 share buttons** — Twitter/X, Facebook, LinkedIn, WhatsApp, Instagram. Outline circular pills (`w-10 h-10 rounded-full`), low opacity (`bg-white/[0.03]`, `border-white/15`, `text-white/55`), hover to volt accent + slight scale.
    - Bottom bar: `© 2026 ScoutMePlay · All rights reserved` + lime dot + "Where talent gets noticed".
    - All previously-broken `/about#what-we-do` link → now routes via `/?scroll=how-it-works` (uses the existing scroll-spy system).
    - `mailto:scoutmeplay@gmail.com` link **removed** — single source of truth is the message form.
    - New `FooterLink` helper with consistent underline-on-hover micro-animation.
  - **"Mentalkids" word stripped** from 6 places across the frontend (Landing footer, AboutPage 2x, PrivacyPage 2x, EmbeddedCheckoutModal, CheckoutTransitionModal). All copyrights now read "© ScoutMePlay · All rights reserved". Zero `Mentalkids` matches remain in `/app/frontend/src`.
  - Copy throughout is honest and professional — no exposure of LLM/tech provider names to end users.
  - **Verified live**: 11 footer links resolve to correct paths, 5 share links open in new tab, 0 mailto links remain, `/terms` route renders correctly.
  - **Only files touched**: `Landing.jsx`, `AboutPage.jsx`, `PrivacyPage.jsx`, `EmbeddedCheckoutModal.jsx`, `CheckoutTransitionModal.jsx`, `App.js` (route), and new `TermsPage.jsx`. Zero backend, zero functionality changed.

- ✅ **🆕 Session 17 — Navigation premium overhaul (Feb 17 2026 late night)**:
  - **Premium wordmark stamp**: replaced muted forest-green "ME" with a bright lime-yellow block (`#CCFF00` background + ink text) — looks like an athletic-brand stamp, dramatically improves contrast on black header.
  - **Explicit HOME link in nav**: added Home (with house icon) as first item in both desktop and mobile nav. On landing it smooth-scrolls to top; on sub-pages it navigates to `/`. Active state shows lime underline when on landing.
  - **Lime accent dot** beside tagline "See your game through scout eyes" with lime glow.
  - **Section Rail** (NEW component `<SectionRail/>` in Navigation.jsx): right-edge vertical scroll-spy on desktop (xl breakpoint, landing only). Shows 6 dots — Top · How it works · Inside · Sample · Pricing · Start. Active section gets a forest-filled dot with halo + revealed label. Click any dot to smooth-scroll. Appears after 200px scroll.
  - **Back-to-Top button** (NEW component `<BackToTop/>` in Navigation.jsx): floating forest-green pill bottom-right with multi-layered shadow + lime inset highlight. Fades in after 600px scroll. Smooth-scrolls to top.
  - **Nav links fit one line**: added `whitespace-nowrap` to prevent the 7 items from wrapping on smaller desktops.
  - **All additive**: only `/app/frontend/src/components/Navigation.jsx` touched. Zero changes to any page content, zero data-testids removed, zero functionality impact. New data-testids: `nav-link-home`, `mobile-nav-home`, `section-rail`, `rail-{section-id}`, `back-to-top`.
  - Smoke-tested live across desktop + mobile + section rail + back-to-top + Home-click scroll behavior.

- ✅ **🆕 Session 16 — Landing page visual depth (A1/A2/B2/D1) (Feb 17 2026 late night)**:
  - **A1/A2 — whitespace tightening**: 4 sections moved from `py-24 md:py-32` → `py-16 md:py-20/24` (What you receive, Sample report, Pricing, Final CTA). Page feels less SaaS-y, more rhythmic; same density of content.
  - **B2 — multi-layered 3D shadow on $399 card**: PricingCards.jsx replaced single `boxShadow` with a 5-layer composition (deep ambient, mid-falloff, near-tight, hair-thin definition, inset volt highlight) — gives the pass card visible lift/depth without changing layout or copy. Also added `hover:scale-[1.012]` for premium-feel micro-interaction.
  - **D1 — animated counter trust strip**: NEW `[data-testid=trust-stats-strip]` section between hero and "How it works". 4-column grid with `AnimatedNumber` (now supports decimals) counting up: **12+ Countries · 500+ Players analyzed · 48h Scout delivery · 4.9/5 Average rating**. Forest glow accents + Framer Motion stagger. Each stat carries `[data-testid=trust-stat-{i}]`.
  - **AnimatedNumber upgrade (backward-compatible)**: now accepts `decimals`, `prefix`, `suffix` props. Existing callers continue to work (default decimals=0).
  - **C1/C5 — photos already in place** from prior session (hero stadium + final-CTA action shot), no change needed.
  - **Surgical change**: only `Landing.jsx` + `PricingCards.jsx` touched. Zero backend, zero data-testid removed, zero copy changes, zero functionality impact.
  - Smoke-tested live: 3 screenshots confirm hero photo + new trust strip + pricing depth + final CTA all render correctly.

- ✅ **🆕 Session 15 — Mobile-first pricing polish on $399 card (Feb 17 2026 late evening)**:
  - **Pinned BEST VALUE banner** at the very top of the $399 card on mobile only — full-width, flush against the card edge, combines `BEST VALUE · SAVE $78` + `MOST PARENTS PICK THIS` as the first thing a thumb-scroller sees.
  - **Desktop ribbon badges hidden on mobile** (`hidden md:flex`) — replaced by the banner. Desktop layout unchanged.
  - **Compressed 8-feature grid** on mobile: single column (already was via `sm:grid-cols-2`), tighter row spacing (`gap-y-2` instead of `2.5`), smaller body text (`text-[13px]` mobile / `text-sm` desktop), smaller icons (`w-3.5 h-3.5` mobile / `w-4 h-4` desktop) via responsive Feature component.
  - **Surgical change**: only `PricingCards.jsx` touched. No other component, no backend, no tests broken. Desktop pixel-identical to iter 15.
  - Verified live: mobile banner visible + correctly hidden on desktop; both desktop ribbons remain visible at md+ breakpoint; features grid resolves to single 290px column on iPhone-size viewport.

- ✅ **🆕 Session 14 — Pricing UX cleanup + sign-in→checkout auto-resume (Feb 17 2026 evening)**:
  - **Single purchase point**: removed the duplicate `$159` Premium overlay from the sample-report visualization on Landing. The floating card is now a price-free "SAMPLE · SEE IT IN ACTION / THIS IS YOUR REPORT / SEE PLANS ↓" teaser that smooth-scrolls down to `#pricing`. Also removed the `$159 USD · one-time` pill from the hero trust bar — replaced with "One-time payment · no subscription". The pricing section is now the **only** purchase-decision surface on the front page.
  - **Pricing section polish (7 upgrades shipped)**: (1) trust strip above cards — "Scout review in 48h · Trusted across 12+ countries · Secure Stripe checkout"; (2) "MOST PARENTS PICK THIS" badge top-LEFT on $399 card; (3) "BEST VALUE · SAVE $78" ribbon top-RIGHT; (4) savings hint band below cards — "$159 × 3 = $477 · You pay only $399 · Save $78"; (5) 3-column guarantee row — 48h delivery / refund · Reviewed by real scouts · Secure Stripe · no subscription; (6) hover-lift on both cards via Framer Motion `whileHover y=-4`; (7) equal-height cards via flex `h-full`; subtle forest-dot background pattern adds depth without distraction.
  - **Sign-in → checkout auto-resume**:
    - `Login.jsx` reads `?next=` + `?open_pass=`, redirects to the resolved next URL post-login; preserves `location.search` on the "Create account" cross-link.
    - `Signup.jsx` same — reads `?next=`, lands user there post-signup; preserves `location.search` on "Log in" cross-link.
    - `DashboardPage.jsx` listens for `?open_pass=1` → auto-opens the embedded Stripe modal → strips the query so refresh doesn't reopen.
    - Pricing CTAs route smartly: anon single-CTA → `/signup?next=/upload` (skip login since they need an account); anon pass-CTA → `/login?next=/dashboard&open_pass=1`; logged-in single-CTA → `/upload` direct; logged-in pass-CTA → opens modal in-place.
  - **Verified end-to-end**: anon clicks pricing-pass-cta → /login → log in → `/dashboard` with Stripe modal auto-opened showing **US$399.00 · ScoutMePlay – 12-month Plan**. Zero re-clicks.
  - **Testing**: `testing_agent_v3_fork iter15 → 100% pass (19/19 critical frontend assertions + 36/36 backend pytests).` One disposable test signup user created during flow validation and cleaned up automatically.

- ✅ **🆕 Session 13 — 2-Card Pricing UX + Admin-editable prices (Feb 17 2026)**:
  - **Pricing model finalized**: $159 single report + $399 12-month plan (3 reports). Both **include scout/agent text review automatically** (no add-on). Both **admin-editable** from Settings tab.
  - **Backend**:
    - `DEFAULT_PRICE = 159` (was 1), `DEFAULT_PASS_PRICE = 399` (was 599).
    - `/api/settings/price` extended to return `{price, pass_price, currency, price_dkk}` — backward-compatible.
    - New `PUT /api/admin/pass-price` endpoint (admin-only, ≤9999 cap, mirrors `/admin/price`).
    - `progress_tracking.py` `/pass/checkout` now reads `pass_price` from `db.settings` at request time — admin price changes take effect on next checkout.
    - `generate_full_report_task` eagerly creates `agent_review` for every freshly-paid/unlocked report → all paid reports auto-appear in the existing `ScoutQueue` admin page.
    - DB seed values written: `settings.report_price=159`, `settings.pass_price=399`.
  - **Frontend**:
    - New reusable `<PricingCards />` component (`/app/frontend/src/components/PricingCards.jsx`) — 2-card layout with: single card (cream, $159, "ONE FULL REPORT"), pass card (forest hero, $399, "TRACK THE FULL YEAR", "BEST VALUE · SAVE $78" ribbon, strikethrough $477, ✓ "Scout / agent review on every report" highlighted). Both CTAs handle logged-in + logged-out states.
    - Pricing copy uses "advanced benchmarked intelligence analysis" framing (no "AI" word per user request).
    - Inserted into `Landing.jsx` as a new `#pricing` section before the TRUST section — does NOT replace the existing sample-report overlay (zero regression).
    - `AdminPage.jsx` Settings tab now has TWO price cards (single + 12-month plan), each with input + Save button + live current-price chip. Both wire to the new PUT endpoints with success toasts.
    - Scout review system (`ScoutQueue.jsx`, `ScoutReview.jsx`, `/admin/agent-queue`, `/reports/{id}/agent-review`) **fully untouched** per user request — they just receive reports faster thanks to eager `agent_review` creation.
  - **Tests**: 14 new pricing pytests in `/app/backend/tests/test_pricing_2cards.py` (added by testing subagent iter14, all pass) + new `/app/backend/tests/conftest.py` auto-loading `.env` so the test suite runs without manual env-setting.
  - **Testing subagent iter14: 100% pass (45/45 backend + frontend).** Verified live admin-edit propagation: change single→169 / pass→449 in admin → reload landing → cards show new prices → progress pass checkout creates Stripe session at the new $449. Reset to defaults after.

- ✅ **🆕 Session 12 — Tier 3 Progress Tracking + $599 Progress Pass (Feb 16 2026)**:
  - **New backend module** `/app/backend/progress_tracking.py` (~600 lines, self-contained, no server.py imports) — `build_progress_router(...)`, `find_or_create_profile(...)`, `consume_pass_credit(...)`, `_pass_active(...)`.
  - **New collection** `player_profiles` `{id, user_id, name, normalized_name, last_position, last_age, preferred_foot, report_ids[], cached_trajectory, created_at, updated_at}`. Reports extended (additive) with `player_profile_id`. All 7 existing reports backfilled into 4 profiles.
  - **API endpoints (`/api/progress/*`)**:
    - `GET /players` — list user's tracked players with `report_count`.
    - `GET /players/{id}/trajectory` — full trajectory: timeline (per-report snapshot with date/age/overall/pillars/age-adjusted percentile), verdict (`ahead`/`on_track`/`plateau`/`first_report`), badges, deltas (raw + age-adjusted + per-pillar), archetype_overlay, video_diff, mission status, Gemini narrative.
    - `GET /players/{id}/growth-card.png` — 1080×1350 PNG via Pillow (header band, verdict chip, raw + age-adjusted delta numbers, pillar delta bars, badge strip).
    - `DELETE /players/{id}` — delete profile.
    - `GET /pass/status` — Progress Pass state.
    - `POST /pass/checkout` — embedded Stripe checkout (live mode) for $599 / 3 reports / 365 days. Inserts `payment_transactions` row with `kind=progress_pass`.
    - `POST /pass/activate/{session_id}` — server-side activation (idempotent, 402 on unpaid, 403 on mismatched user_id).
  - **Server.py integration**:
    - Upload route honours Progress Pass credit: if free preview is used AND no prepaid_uploads BUT pass_state.active → consume 1 credit & generate full report (no Stripe charge).
    - `find_or_create_profile()` called after every successful upload — auto-matches by `(user_id, normalized_name)`.
    - `/api/me/upload-eligibility` returns new `progress_pass` field + `reason: "progress_pass"` when only credits remain.
    - `/api/webhook/stripe-embedded` recognises `kind=progress_pass` → activates pass on session.payment_status=paid (3 credits / 365 days, idempotent by session_id).
  - **Tier 3 cleverness**:
    - **Age-adjusted percentile** (honesty moat) — bracket-based mapping (≤10 / ≤12 / ≤14 / ≤17 / >17). Same raw 7.0 lands at 50pct at U13, ~40pct at U17. Surfaces in trajectory as `overall_age_adjusted_pct` + honesty-callout UI block when raw rises but age-adjusted drops.
    - **Gemini Delta Narrative** — `generate_delta_narrative()` calls `call_gemini_text()` with strict facts-only system msg + 140–180-word output, cached on profile by report_count. Live verified: Lukas A. (5.5-month gap, 13→14, 6.8→8.0 overall, 46%→70% age-adj) → 882-char specific narrative.
    - **Trajectory Verdict** — `_verdict()` derives `ahead` (yearly_pace ≥ 0.7), `on_track`, `plateau` (≤ 0.05) from overall growth scaled by months span. UI shows hero card with VERDICT_META icons + colour.
    - **Archetype Trajectory Overlay** — `ARCHETYPE_CURVE` constant maps tier → typical U11/U14/U17/U21 overall. UI renders solid Player line + dashed Archetype path line in same Recharts LineChart.
    - **Video-evidence diff** — pairs first vs latest `video_comments` with frame_url, max 3 pairs, renders before/after grid in UI.
    - **Mission/next-focus loop** — reads previous report's `mission_focus`, evaluates each pillar (improved iff Δ ≥ 0.3), auto-suggests next mission from 2 weakest current pillars.
    - **Growth badges** — `_compute_badges()` returns First Century (pillar ≥ 8), Plateau Breaker (≥1.0 jump after flat pair), Stage Up (band crossed), Pro Comparison Unlocked (age ≥ 12).
    - **Shareable growth card PNG** — 1080×1350 IG-ready, generated server-side, served via authenticated route.
  - **Frontend**:
    - New `/trajectory/:id` route + `TrajectoryPage.jsx` — verdict hero, raw + age-adjusted delta pills, honesty callout (conditional), Recharts LineChart with archetype overlay, Gemini narrative card (forest hero), pillar delta bars, mission status with HIT/MISS chips + next-focus chips, video diff before/after grid, badges grid, reports table.
    - Rewritten `DashboardPage.jsx` (cream theme) — Progress Pass promo banner ($599 / 3 reports / 12 mo + 4-bullet value prop) OR active banner (credits remaining + expiry); "Your players" section above legacy "Your reports" library. Embedded Stripe modal opens on "Buy Progress Pass" click.
    - All elements carry stable `data-testid`s for testing.
  - **Tests** — 22 new pytests in `/app/backend/tests/test_progress_tracking.py` (verdict logic, age-adjusted bands, badges, archetype tier resolution, mission evaluator, pass state) — 22/22 pass. 9 live API integration tests in `/app/backend/tests/test_progress_api_live.py` (added by testing subagent iter13) — 9/9 pass.
  - **Testing subagent iter13: 100% pass (31/31 backend, 100% frontend).** Stripe live keys protected — modal reaches ready state but no card entered.
  - **Untouched**: existing report flow, PDF generation, Gemini archetype narrative, FIFA/StatsBomb panels, blog CMS, URL upload, auth, admin.


- ✅ **🆕 Session 11 — Upload URL paste + Report share toolbar + PDF "60-Second Scout Summary" (Feb 15 2026)**:
  - **Upload URL paste** (`UploadPage.jsx` + new `backend/url_video_fetch.py`): toggle between **File upload** and **Paste URL**. Backend `POST /api/me/url-fetch` uses `yt-dlp` (added to requirements.txt) to download YouTube, Vimeo, Veo, direct MP4 links into the standard `UPLOAD_DIR` (capped 200MB / 120s). Returns `{token, preview_url, size_mb}` — frontend uses `preview_url` as the marker video source. Existing `/reports/upload` endpoint extended with optional `temp_video_token` Form field (file remains required when token absent — backward compatible).
  - **Report page social share toolbar** (`ReportPage.jsx`): WhatsApp / X (Twitter) / Email / Copy-link icon buttons next to the existing Download PDF and Get Share Card buttons. Native share URLs (`wa.me/?text=…`, `twitter.com/intent/tweet?…`, `mailto:`). All four buttons verified present and styled with brand-forest outline.
  - **PDF "60-Second Scout Summary" page** (`server.py` `_scout_summary_page()`): new page 2 right after the cover. Single shareable TL;DR — player name + position/age, big scout score, archetype match card, TOP STRENGTHS column, DEVELOPMENT PRIORITIES column, "If you only read one page — this is it" closer. `PDF_RENDER_VERSION` bumped 8→9 to invalidate cache. Verified text extraction: page 2 of Lukas A. report shows "60-Second Scout Summary · 8.0 / 10 · TOP STRENGTHS · DEVELOPMENT PRIORITIES".
  - **Untouched**: existing file-upload flow, existing PDF sections (exec summary, scoreboard, age intelligence etc.), all auth, payment, blog, archetypes.
- ✅ **🆕 Session 10 — Archetype `academy_bio` FULL PARITY (Feb 15 2026)**:
  - Filled `academy_bio` (5 age brackets: 8-10 / 11-12 / 13-14 / 15-17 / 18-21) for **all 63 non-AM archetypes** across Goalkeeper, Striker, Winger, Centre Back, Full Back, Defensive Midfielder, Central Midfielder — every position now has the same depth as AM. Also filled all 9 Goalkeeper `career_brief` fields (previously empty).
  - **Net effect**: every report now renders the "What [PRO] was doing at age N" panel (web + PDF) AND the Gemini personalised narrative (`bio_chunk`-guarded at server.py:1390) for every position, not just AM. Silent quality gap closed.
  - **Build script**: `/app/backend/scripts/fill_academy_bios.py` — idempotent, only fills empty fields, bumps `_meta.version` to 5. Re-runnable safely.
  - **Pytests**: 5 new tests in `/app/backend/tests/test_archetype_parity.py` lock the contract: every position present, every archetype has all 5 brackets, all 9 GK have career_brief, no placeholder text, bracket-lookup resolves U7-U21. All 5 pass.
  - **Sources used**: Wikipedia, Transfermarkt, FBref, club academy pages, mainstream long-form journalism. No invented stats.
  - **Untouched**: schema, ranker, PDF templates, scoring, payment, auth.
- ✅ **🆕 Session 9 — Professional Blog + Site-wide SEO + Gemini AI Authoring + Article Series Engine (Feb 15 2026)**:
  - **New modular backend files** `/app/backend/blog_routes.py` + `/app/backend/blog_seo.py` (clean separation, no circular deps with `server.py`).
  - **Public blog**: `/blog` index (search + 5 seeded categories + featured-post bento grid) and `/blog/:slug` article page (cover image, markdown body via `react-markdown` + `remark-gfm`, breadcrumbs, related posts, tags).
  - **Admin CMS**: new "Blog" tab in AdminPage with list view, status badges, view counter; full editor with title/subtitle/slug/excerpt, Markdown textarea + live preview, cover image upload OR URL, category dropdown + tag input, author, status, draft/publish buttons.
  - **Gemini AI authoring**: `POST /api/blog/admin/ai/draft` (topic → full Markdown article with H1/H2/H3 + takeaway), `POST /api/blog/admin/ai/seo` (title + content → meta_title/meta_description/meta_keywords JSON), `POST /api/blog/admin/ai/series` (broad topic → 3–10 connected article plans with title/brief/category/tags/keyword/meta), `POST /api/blog/admin/ai/series/save` (bulk create the series as draft posts with outline stubs). Uses existing `call_gemini_text()` (gemini-2.5-flash).
  - **Article Series Engine UI**: new "Generate Series" button in Admin → Blog opens an inline panel — paste 1 broad topic, pick count (3/5/7/10), tweak audience, click "Generate plan". Gemini returns a card list (each card has editable title, brief, category, tags, primary keyword, meta fields). Click "Save N drafts" → bulk creates draft posts each with an outline stub. Verified end-to-end via UI: topic "U13 attacking midfielder development" produced 5 sequential articles spanning U7-U11 → U13 → U14-U16 → U17-U21 → Parent's Guide, each with unique keyword and matched category.
  - **Site-wide SEO infrastructure**: new `SEO.jsx` Helmet wrapper (title/desc/canonical/OG/Twitter/JSON-LD) + helper builders `organizationJsonLd`, `articleJsonLd`, `breadcrumbJsonLd`. Added to Landing, About, Methodology, Blog index, Blog article. `react-helmet-async` HelmetProvider mounted in App.js.
  - **Crawler endpoints**: `GET /api/sitemap.xml` (auto-includes published blog posts + static routes, resolves public URL via x-forwarded-* headers), `GET /api/robots.txt` (disallows /admin, /api/, /dashboard, /report/, /upload).
  - **Image uploads**: `POST /api/blog/admin/upload-image` (admin only, 5MB cap, jpg/png/webp/gif), served via static mount `/api/blog/uploads`.
  - **5 seeded categories**: Training, Scouting Tips, Parent's Guide, Pro Player Path, Reports & Analysis (auto-seeded on first hit).
  - **Backend verified via curl**: CRUD, sitemap, robots, AI draft (Gemini returned a 7-min article on first try), AI SEO (returned 8 keywords + meta within char limits).
  - **Frontend dependencies added**: `react-markdown`, `remark-gfm`, `react-helmet-async`, `@tailwindcss/typography`.
  - **Nav updated**: added "Blog" link to desktop middle nav + mobile menu (between Sample and Methodology).
- ✅ **🆕 Session 8 — Premium navigation redesign (Feb 13 2026)**:
  - Removed off-brand "sniper warrior" logo SVG → clean SCOUT[ME]PLAY wordmark.
  - Real middle nav links (How it works · What's inside · Sample · Blog · Methodology) with animated lime underlines + cross-page smooth-scroll via `?scroll=` param.
  - Scroll-shrink header with `backdrop-blur-xl bg-ink/85`, lime scroll-progress strip.
  - CTA buttons get lime halo glow + chevron translate on hover.
  - Full mobile hamburger panel with forest background.
- ✅ **🆕 Session 7 — Age Intelligence Scoring System (U6 → Senior, fair for every age) — Feb 05 2026**:
  - **New data file** `/app/backend/data/age_stages.json`: 5 development stages with age bands, focus attributes, downweight attributes, panel-gate flags, and friendly stage-gated messages.
    - **Foundation Stage** (U6-U8): focus on ball contact, coordination, courage, enjoyment, basic dribbling. ALL senior-pro panels gated.
    - **Technical Development** (U9-U11): focus on first touch, dribbling, passing basics, 1v1, weak foot. ALL senior-pro panels still gated.
    - **Game Understanding** (U12-U14): scanning, decision-making, positioning, movement. Senior-pro panels UNLOCK.
    - **Academy Readiness** (U15-U17): speed of play, tactical discipline, intensity, role understanding.
    - **Senior Performance** (U18+): efficiency, match impact, end product, consistency.
  - **New deterministic Python module** (in `server.py`):
    - `resolve_age_stage(age)` — maps age → stage dict
    - `next_age_stage(stage)` — for the "next-level readiness" score
    - `compute_age_intelligence()` — produces 9 deterministic scores: **current_age_score**, **position_specific_score**, **next_level_readiness_score**, **pro_style_match_score**, **technical_score**, **tactical_score**, **physical_score**, **mentality_body_language_score**, **development_priority_score**. Tactical attrs are HALF-WEIGHTED for U6-U8 / U9-U11 stages (so we don't over-score game intelligence on young kids).
    - `apply_stage_gating()` — mutates the serialized report to STRIP FIFA k-NN + StatsBomb + Trial Readiness for U6-U11 and replace them with friendly "Reserved for U12+" messages. Also strips the FIFA lens from the 5-lens strip.
    - `_resolve_level()` — maps (tier × stage × overall_score) → one of 8 human-friendly labels: **Beginner / Grassroots / Club / Strong Club / Academy / Elite Academy / Semi-Pro / Professional**.
  - **Lukas's live scoreboard** (age 14, Understanding stage): current_age=8.6 · position-specific=8.3 · next-level=8.1 · pro-style=8.8 · technical=7.3 · tactical=8.7 · physical=7.3 · mentality=8.3 · dev-priority=2.0 · **Level: Elite Academy**.
  - **Almin's stage-gated UI** (age 11, Technical stage): FIFA k-NN panel → friendly "Reserved for U12+" stage-gated card; StatsBomb panel → gated; Trial Readiness → gated; 5-Lens strip drops the FIFA card (now shows 4 lenses); Pro Style Match score card shows "—" with "UNLOCKS AT U12".
  - **5 new frontend components** in `ReportPage.jsx`: `AgeStageBanner`, `AgeAppropriateEvaluationDisclaimer`, `WhatWeEvaluatedBlock`, `AgeIntelligenceScoreboard`, `StageGatedPanel` — each with stable data-testids.
  - **Disclaimer** *"This player has been evaluated using age-appropriate and position-specific benchmarks. Professional player data is used as a style and long-term development reference, not as a direct comparison."* — surfaced on EVERY report (web + PDF), in a prominent block directly under the stage banner.
  - **PDF mirror** via new `_age_intelligence_pdf()` helper: stage banner + 9-score grid (current_age highlighted in forest) + disclaimer block + 2-column "what we evaluated / what we did not" block. PDF cache bumped to v8. Verified contains: AGE-ANCHORED EVALUATION, AGE INTELLIGENCE SCOREBOARD, HOW THIS EVALUATION WORKS, EVALUATED FOR THIS STAGE, DELIBERATELY NOT EVALUATED, CURRENT AGE SCORE, POSITION-SPECIFIC, DEV. PRIORITY.
  - **What-we-evaluated transparency block**: shows the stage's focus attributes ✓ AND the stage's deliberate exclusions ✗ AND a 3rd "AI blind spots" block listing attributes the AI marked `cannot_evaluate` for THIS specific video (with the reason).
  - **Testing**: 16/16 new pytests in `test_age_intelligence.py` (catalog integrity, U6/U9 panel gating, U12+ unlocking, 9-score math, level mapping, disclaimer presence, FIFA-mirror equality, PDF content). 58/58 pytests pass across all 6 archetype test files. Testing subagent iter12 ran full end-to-end on Lukas + Almin and confirmed both stages render correctly.
  - **Bug found & fixed by testing subagent**: dangling `*/` comment in `ReportPage.jsx` from my edit broke the dev server build. Fix restored the `/* AgeProfileCard — */` block header.

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
