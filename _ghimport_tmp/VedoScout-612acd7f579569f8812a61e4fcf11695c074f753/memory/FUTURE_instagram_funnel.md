# FUTURE: Instagram Growth Funnel — STATUS OPDATERET Aug 5, 2026

## ON HOLD (user: "Vi afventer med denne opsætning for nu")
- **Fase 2 (Meta token-opsætning)**: BYGGET og klar — "Post to Instagram"-knap + connect-kort ligger i Admin → Marketing → Carousel Studio. Venter KUN på at brugeren laver Meta Business-opsætningen. Komplet trin-for-trin token-guide (Graph API Explorer → extend token → me/accounts page-token + instagram_business_account id) blev leveret i chatten Aug 5 — genbrug den når brugeren er klar. Backend: instagram_publish.py (verificeret mod Meta API).
- **Fase 3 (ManyChat)**: Guide + DM-tekster leveret og gemt i /app/memory/MANYCHAT_GUIDE.md. Brugeren har ikke sat det op endnu.

## FÆRDIGBYGGET (Fase 1, Aug 5) — venter kun på brugerens brug
- Carousel Studio, gratis PDF-guide, /guide side, funnel-emails (rabatkoder skal sættes på trinnene før de sender), rabatkodesystem (live Stripe promotion codes).

## Åbne punkter når brugeren genoptager
1. Meta Business-opsætning → token + konto-ID → Connect i admin → test-post demo-carousellen
2. ManyChat Pro opsætning (guide klar)
3. Opret første rabatkoder + sæt dem på funnel-trinnene
4. Evt.: planlagt auto-post (schedule), guide-link på forside/footer, betalt udvidet PDF-bog (paid_guide step er default OFF)


User's goal: Instagram carousel posts → comment keyword → auto-DM → email → free PDF → follow-up offers → sales.
Everything below was confirmed feasible and the user chose ALL offers, admin-controlled. DO NOT build until user says go.

## Fase 1 — buildable in ScoutMePlay with no Meta setup
1. **Carousel Studio (admin)**: AI generates 6-8 slide images (1080x1080, dark cinematic football style with text overlay, like user's reference screenshot: hook slide → MISTAKE #1..#5 slides → CTA slide "COMMENT 5 & I'll send it to your DMs"). Warm ScoutMePlay tone rules apply (no "AI", no "percentile", no promises). Download as PNGs for manual posting.
2. **Free PDF lead magnet**: e.g. "The 5 Things Every Football Parent Gets Wrong" — branded PDF (title not final; user was asked, never confirmed).
3. **/guide landing page**: email capture → instant PDF email via existing Gmail SMTP (email_service.py).
4. **Email funnel (all 4 offers, sequenced, ADMIN-CONTROLLED on/off + prices + texts)**:
   - free PDF (immediate)
   - discount on single Scout Report for new users (start price suggestion $99 vs $129 — user never confirmed)
   - Premium/VIP membership discount for new members
   - paid extended PDF/book (start price $9 or $19 — user never confirmed)
5. **Discount code system (admin)**: user creates codes (% or fixed), valid for subscriptions AND/OR single reports, expiry date, redeemed in existing Stripe checkout flows.

## Fase 2 — requires user's Meta setup (~30 min, guided)
- "Post to Instagram" button in Carousel Studio admin → auto-publish carousel to user's own IG account via Instagram Graph API content publishing.
- Requirements user must do: switch IG to Business account (free), link to their Facebook Page, create Meta Developer app + long-lived access token for own account (works in dev mode for own account, no full App Review needed for own-account publishing). Images must be publicly hosted (R2/static exists).
- MUST call integration_expert for Instagram Graph API playbook before implementing.

## Fase 3 — ManyChat (user's own setup, we provide content)
- Comment "5" → auto-DM automation runs in ManyChat (~$15/mo), which already has Meta approval. User connects IG Business to ManyChat; we write all DM texts + click-by-click guide. DM links to /guide page so funnel connects.
- Honest constraint told to user: a regular (personal) IG account can NEVER do auto-DM; unofficial bot tools risk account ban — never recommend.

## Open questions to re-ask when resumed
- PDF guide title/topic confirmation
- Paid PDF price ($9/$19?), report discount price ($99?)
- Whether user completed Business-account + FB Page link
