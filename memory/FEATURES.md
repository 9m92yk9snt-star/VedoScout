# ScoutMePlay — FEATURE INVENTORY (opdateret 8. aug 2026)
Formål: komplet liste over ALT der allerede findes, så nye forslag aldrig gentager eksisterende features.

## Kerneprodukt
- Video-upload (chunked, baggrund) + spiller-markering (tap/zoom/lock) + spillerdetaljer (navn, alder, position, land, foto KRÆVET)
- Analyse-pipeline (Gemini video + GPT-4o vision identity cross-check), dual-pass observationer, identity-evidens filtrering, kategori/varigheds-validering
- Gratis analyse → Free Preview (låst) → Premium rapport (køb/abonnement/manuel unlock)
- Rapport V2: hero, Scout's First Impression (tidl. Parent Summary), samlet score, match stats, alderssammenligning, SNAPSHOT 2×2 (frames+timestamps+annoteringer), top strengths (frames), udviklingsprioriteter, action timeline, roadmap, træningsplan, parent tips, video highlight, coach notes, scout outlook, FIFA player twin, development curve, movement map, score-forklaring, Grow Your Game, printables (mission card + ugeplan), diplom
- Cinematic intro: film-åbning ved første rapport-visning (mørk scene → bedste frame + navn + moment-linje → score-count-up), skip altid, lyd fra default, replay-knap, demo-badge på sample (jun 2026)
- Proof mini-player: alle timestamp-klik åbner bottom-sheet videoafspiller (seek ts−6s) — INGEN scroll-hop; demo viser taktisk frame + premium-note; mobil "SEE THE PROOF"-pills på top strengths (jun 2026)
- PDF-rapport (reportlab, 7+ sider, inkl. SNAPSHOT-side, cache m. PDF_RENDER_VERSION)
- Sample/demo-rapport (/sample-report, seedet, DEMO_VERSION-styret) m. demo-note
- Snapshot-deling: branded 1080×1350 PNG pr. snapshot-kort (demo public + premium auth) m. share/download-knap
- FIFA-style spillerkort PNG (story-format deling)
- Free Preview: hero m. potentiale, preview insights, SNAPSHOT-teaser (1 ægte + 3 låste), key moment, missing-list, pricing tiers, share-to-unlock exit-modal (én ekstra score-story)
- Progress curve / spiller-trajectories (flere rapporter over tid), curve reminder email
- Scout Database fase 1: spillerprofil-synlighed (opt-in), /players-database til scouts, scout-adgang (is_paid_scout), scout queue i admin
- Video-deling m. forældre-samtykke toggle (permanent link)
- Rapport-deling (share tokens)

## Betaling & priser
- Stripe: enkeltrapport-køb, VIP/abonnementer (tiers), Progress Pass, dynamiske priser fra admin (ny Stripe Price + deaktivering af gammel)
- Rabat-infrastruktur (highest-wins): rapport-niveau 48h auto-tilbud, bruger-niveau exit-intent claim + referral credit, globale kampagner
- Manual Campaign (admin): navn, %, timer, aktiv/deaktiver
- Auto-discount % (admin-indstilling, 48h-mail)
- Moms/tax-admin (TaxAdmin)

## Growth & konvertering
- Exit-intent tilbud (landing): admin-styret popup (enabled/%, countdown, valid_hours, headline), preview i admin, claim→attach→auto-rabat ved checkout, stats (claims/attached)
- Teammate referral: personligt link (?ref=), begge sider får % på næste rapport, dashboard invite-kort m. kopiér/del + inviterede-liste, admin: settings + fuld hvem-invited-hvem-tabel
- Sticky mobile CTA (landing, admin-redigerbar under Settings)
- Landing: hero, demo-rapport showcase (interaktiv), trust strip, How it works (mobil-swipe), What's inside (mobil-swipe), image strip, pricing tiers m. dynamisk værdiberegning, reviews strip, social follow, FAQ, blurred report teaser paywall
- Landing-varianter (minimal/full, admin-skiftbar)
- Cookie-banner kompakt (mobil over bottom-nav) + genåbnings-chip

## Emails (Gmail SMTP + send/open/click-log)
- Velkomst, aktivering 24h/72h (uden upload), conv-serie: 24h numbers-waiting → 48h rabat → 72h discovery, abandoned checkout (~1h), kampagnetilbud, rapport-klar, købskvittering, curve reminder, bulk email CMS, admin salgs-notifikation
- Email-hub i admin: alle 11 typer m. navn/hvornår + "Send test" til rigtig mail
- Klik-tracking m. sikker redirect, open-pixel, pr.-bruger email-log i admin

## Blog & SEO
- Blog-studio (AI-genererede artikler m. R2 covers), seed-artikler, publicering
- SEO-dashboard (first-party: organisk/referral-signaler, artikel-keywords, keyword-forslag)
- SEO-komponent (meta/OG/JSON-LD), robots.txt, sitemap(?)

## Analytics & tracking
- First-party analytics (GDPR-let, ingen Google): sessions, pageviews, CTA/funnel, scroll/tid, UTM, device, exits/konverteringer → admin-dashboard
- Meta pixel-init (pixels.js)

## Admin (faner)
- Reports/payments (manuel unlock, delete), users, priser (Stripe-sync), settings (sticky CTA, landing-variant, auto-discount), Growth (kampagner + exit-offer + referral), Email (hub + bulk CMS + log), SEO, Analytics, Blog-studio, Marketing/Instagram-carousel (config-gated), scouts-kø, tax
- Admin kan sende testmails, preview exit-popup, se referrals

## Auth
- JWT email/password (signup/login/reset via mail), honeypot, rate-limit på signup
- Google-login FJERNET (Emergent-branding) — AuthCallback-kode bevaret til evt. egen OAuth senere
- Ens topbar/Navigation på login/signup/upload

## Andet
- ManyChat-guide (memory), Instagram-funnel plan (memory), guide-PDF lead magnet + guide-emails
- Mobil: ingen horisontal overflow-garanti (testet 320-430px), bottom-nav

## IKKE bygget endnu (godkendte idéer til senere)
- Live social proof toasts ("X fik netop sin rapport")
- Før/efter-historier sektion
- Snapshot email-teaser i rapport-klar-mail
- Instagram story-format (1080×1920) share-billede
- Trustpilot-anmodningsmail
- Familie/søskende-bundle
- VIP-rabat via referral (kræver Stripe coupons)
- Rapport-repeatability (P0 fra tidligere — stadig åben)
