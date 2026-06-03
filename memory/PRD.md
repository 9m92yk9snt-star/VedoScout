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
- ✅ DKK → USD currency conversion across UI (Landing, Upload, Report, Admin, Modal) + backend
- ✅ `DEFAULT_REPORT_PRICE_USD=1`, `DEFAULT_REPORT_CURRENCY=usd` env vars
- ✅ Admin dashboard updates: "Current price (USD)", revenue shows `$X.XX USD`
- ✅ Backend `/api/admin/stats` returns `revenue_usd` + legacy `revenue_dkk`
- ✅ Backend `/api/payments/*` flows persist `currency=usd` and `amount` in USD dollars
- ✅ DB migration ran — existing report_price setting reset to 1.0 USD
- ✅ NEW: Embedded Stripe checkout endpoints `/api/payments/embedded/prepay-upload`, `/api/payments/embedded/unlock`, `/api/payments/embedded/status/{sid}`
- ✅ NEW: `EmbeddedCheckoutModal.jsx` mounts Stripe's `<EmbeddedCheckout>` inside a branded ScoutMePlay modal — true in-page payment
- ✅ NEW: UploadPage + ReportPage auto-prefer embedded checkout when Stripe keys are configured; otherwise gracefully fall back to redirect modal
- ✅ **Real Stripe TEST keys configured** in `/app/backend/.env` — embedded checkout fully functional (verified via testing agent: 14 real js.stripe.com iframes mounted inside our branded modal showing "MENTALKIDS · SCOUTMEPLAY SECURE CHECKOUT · US$1.00")
- ✅ **Bug fix (CRITICAL)**: Added `_arm_real_stripe()` helper that resets `stripe_sdk.api_base='https://api.stripe.com'` before every embedded SDK call. Required because `emergentintegrations` silently mutates the global `stripe.api_base` to its proxy URL, which would otherwise poison subsequent embedded calls in the same worker
- ✅ **Bug fix (HIGH)**: Embedded sessions now use `redirect_on_completion='if_required'` so Stripe's `onComplete` callback fires in-page (instead of redirecting). 3DS auth flows still redirect when needed
- ✅ Backend tested 7/8 green (1 intentional skip) — both previously-failing bug-repro tests now PASS

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
- `POST /api/payments/embedded/prepay-upload` — NEW embedded (returns `client_secret`)
- `POST /api/payments/embedded/unlock` — NEW embedded (returns `client_secret`)
- `GET /api/payments/embedded/status/{session_id}` — NEW
- `GET /api/config/stripe` — NEW public config (publishable_key + embedded_available)
- `POST /api/webhook/stripe`
- `PUT /api/admin/price`, `GET /api/admin/stats`, etc.

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
