# ScoutMePlay — FEATURE INVENTORY (opdateret 8. aug 2026)
Formål: komplet liste over ALT der allerede findes, så nye forslag aldrig gentager eksisterende features.

## Kerneprodukt
- Video-upload (chunked, baggrund) + spiller-markering (tap/zoom/lock) + spillerdetaljer (navn, alder, position, land, foto KRÆVET)
- Analyse-pipeline (Gemini video + GPT-4o vision identity cross-check), dual-pass observationer, identity-evidens filtrering, kategori/varigheds-validering
- Gratis analyse → Free Preview (låst) → Premium rapport (køb/abonnement/manuel unlock)
- Rapport V2: hero, Scout's First Impression (tidl. Parent Summary), samlet score, match stats, alderssammenligning, SNAPSHOT 2×2 (frames+timestamps+annoteringer), top strengths (frames), udviklingsprioriteter, action timeline, roadmap, træningsplan, parent tips, video highlight, coach notes, scout outlook, FIFA player twin, development curve, movement map, score-forklaring, Grow Your Game, printables (mission card + ugeplan), diplom
- Cinematic intro: film-åbning ved første rapport-visning (mørk scene → bedste frame + navn + moment-linje → score-count-up), skip altid, lyd fra default, replay-knap, demo-badge på sample (jun 2026)
- Proof mini-player: alle timestamp-klik åbner bottom-sheet videoafspiller (seek ts−6s) — INGEN scroll-hop; demo viser taktisk frame + premium-note; mobil "SEE THE PROOF"-pills på top strengths (jun 2026)
- Intro share clip: delbar 1080×1920 story-MP4 af cinematic-introen (server-genereret, cached) m. "Share intro clip"-knap i rapport-header — demo public + premium auth (jun 2026)
- Free preview: cinematic intro (potential 84/100 count-up → "UNLOCK THE FULL STORY") + proof-player (ægte video på åbent snapshot/key moment, låste kort → locked sheet m. unlock-CTA) (jun 2026)
- Social feature-consent (GDPR): valgfrit "get featured"-samtykke på upload + Dashboard-toggle + admin Featured Clips-liste m. klip-download + privacy-sektion 9 (jun 2026)
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

## Player Dashboard 2.0 + Dashboard Hub (2026-08-09)
- Nyt dashboard-layout (Free + Premium/VIP) efter godkendte mockups; scoutmeplay.com-header; radar erstattet med animerede SkillBars
- Free: FREE-medlemsbånd, Scout Preview-upsell (demo-tagget), låste beskeder m/ FOMO-tæller, INGEN Trials & Opportunities
- Premium: Performance HQ (overall-ring + skill bars fra seneste premium-rapport), rigtige beskeder, Trials & Opportunities
- Admin-tab "Player Dashboard": netværkstal (demo-FOMO, kan slås fra), besked/notifikations-komponist (all/free/premium/vip eller enkelt email, sender-type scout/agent/club/admin), opportunities CRUD

## Dashboard extras (2026-08-09)
- Auto-notifikation på dashboard når preview/premium-rapport er klar (idempotent, system-afsender)
- Header-badges (klokke + kuvert m/ lime-tal) i topmenu, scroller til indbakken; også i mobilmenu
- Visningstæller "Profile views" (ægte data fra spillerdatabase-åbninger, dedupe 6t, selv-visninger tælles ikke) — låst for free
- Premium kan svare på scout/agent/klub-beskeder fra dashboardet; admin ser svar i Player Dashboard-tabben
- Scout Library-synlighed er nu PREMIUM-privilegium (403 for free) + tydelig free-besked: uploads ses ikke af scouts, kun social media hvis opt-in

## Admin messaging & trials 2.0 (2026-08-09)
- "Send besked"-knap på hver bruger i admin Users-listen → composer prefilled med deres email
- Email-alarm: scout/agent/klub-beskeder udløser email til berettigede medlemmer (aldrig free)
- Trial-ansøgning: Premium trykker "I'm interested" → admin ser ansøgerliste pr. trial
- Live library-tal: admin ser ægte antal synlige spillere og kan vælge live-tal eller fiktive pr. Network-sektionen

## Direct-to-Stripe guest checkout (2026-08-09)
- Premium/VIP/Single-kort for ikke-indloggede går direkte til Stripe (ingen signup-væg) — alle steder på sitet
- /welcome-side efter betaling: konto auto-oprettes fra Stripe-email, køber vælger kun adgangskode og logges ind
- Single-køb giver 1 prepaid premium-rapport og sender køberen til /upload
- Eksisterende konto med samme email får købet koblet på automatisk
