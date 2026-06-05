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
