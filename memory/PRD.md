# Elite Football AI Scout Platform — PRD & Status

## Original Problem Statement
Build a premium football player video analysis platform where players or parents upload a football video, receive a free AI preview, and unlock a comprehensive premium report upon a single fixed payment (399 DKK, admin-configurable).

Core flow: Land → Sign up → Upload video + details → Free AI preview → Locked premium sections → Pay → Full report + PDF download.

## User Personas
1. **Aspiring Player / Parent** — uploads videos, reviews AI feedback, pays once to unlock premium report.
2. **Admin** — manages users, reports, payments, pricing, manual unlocks.

## Tech Stack (As Built)
- **Backend**: FastAPI + MongoDB (motor) + bcrypt JWT auth, single file `/app/backend/server.py`
- **AI**: Gemini 2.5 Pro multimodal via `emergentintegrations` Universal Key (analyzes uploaded videos)
- **Payments**: Stripe Checkout via `emergentintegrations.payments.stripe.checkout`
- **PDF**: ReportLab generates premium dark-themed PDF
- **Frontend**: React 19 + Tailwind + lucide-react + framer-motion + recharts
- **Design**: Volt Green (#CCFF00) on Deep Navy (#050A0F), Barlow Condensed + DM Sans

## Architecture
- Local file storage in `/app/backend/uploads/` served via FastAPI static mount.
- MongoDB collections: `users`, `reports`, `payment_transactions`, `settings`.
- JWT bearer auth; admin role seeded on startup.
- Stripe payment flow: backend-controlled amount; polling on success URL; idempotent updates.

## Implemented (Phase 1 — MVP, Feb 2026)
- ✅ Landing page with Hero, How It Works, What You Receive (8 cards), Sample Preview (blurred premium), Trust, Final CTA
- ✅ JWT auth (signup/login, /me)
- ✅ Video upload form (player_name, age, position, foot, club, video_type, description)
- ✅ Free AI preview via Gemini multimodal
- ✅ Locked premium sections with blur + "Unlock Full Premium Report" CTA
- ✅ Stripe Checkout integration (399 DKK default, server-controlled, polled status)
- ✅ Full premium report generation post-payment (11 sections including technical, tactical, physical, mentality, scout view, training plan, video comments, scores)
- ✅ Performance radar chart on premium report
- ✅ PDF download (premium dark theme via ReportLab)
- ✅ Dashboard for user reports
- ✅ Admin panel (stats, reports, users, payments, price config, manual unlock, delete)
- ✅ Responsive across mobile/tablet/desktop
- ✅ Disclaimer text throughout

## Backlog / Next Items (Phase 2)
- P0: Backend testing pass (in progress)
- P1: Resumable / chunked uploads for large video files (>200MB)
- P1: Background-task full report generation with progress UI (replace synchronous wait)
- P2: Email confirmation on payment success
- P2: Refund handling in admin panel
- P2: Multi-language support (Danish UI given DKK pricing)
- P2: Account/profile settings page (change password)
- P3: Object storage migration (S3) for scale

## Test Credentials
See `/app/memory/test_credentials.md`
