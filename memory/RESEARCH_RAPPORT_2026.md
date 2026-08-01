# ScoutMePlay — Dybde-Research & Produktaudit (Juni 2026)
**Status: KUN RESEARCH — intet er bygget eller ændret.**
Datagrundlag: Gennemgang af hele kodebasen (backend 12.800 linjer + frontend), live UI-audit på desktop & mobil (alle nøglesider screenshots), målte pipeline-tider fra rigtige rapporter i databasen, markedsresearch af 10+ konkurrenter, samt konverteringsforskning.

Nuværende tal: **43 brugere · 51 rapporter · 45 betalte** (test + rigtige). Preview-analyse tager målt **32–100 sekunder**.

---

# EXECUTIVE SUMMARY

ScoutMePlay har et **unikt produkt** — ingen konkurrent i verden kombinerer: telefonvideo-upload uden hardware + ejerverificeret spillertracking + dual-AI evidensbaseret analyse + rigtig scout-review + forældrevenlig rapport. Veo/Trace kræver hardware og er team-fokuserede; aiSCOUT laver slet ikke matchanalyse; små AI-apps mangler trust og evidens.

**Det største problem er IKKE produktet — det er alt rundt om produktet:**
1. **Trust-gabet på forsiden**: En forælder kan ikke se en rigtig rapport, før de har oprettet konto og uploadet. Det er den største konverteringslækage.
2. **Prisforvirring**: 6 prispunkter i USD mod en dansk målgruppe. Paywall siger $129, pricing-sektionen $29,99/md. Forældre kan ikke regne det ud på 5 sekunder.
3. **Teknisk hastighed på mobil**: Ingen code-splitting → hele appen (20+ sider inkl. admin) loades som ét bundle på første besøg. Meta-ads trafik er ~90 % mobil.
4. **Sikkerhedshuller før skalering**: placeholder JWT-secret, CORS `*`, LIVE Stripe-nøgler i preview-miljøet.

**Top-5 anbefalinger efter forventet effekt:**
| # | Anbefaling | Effekt | Kompleksitet |
|---|---|---|---|
| 1 | Interaktiv eksempel-rapport på forsiden (anonymiseret) | 🔥 Høj konvertering | Lav |
| 2 | Dansk sprog + DKK-priser + prisforenkling (3 valg maks) | 🔥 Høj konvertering | Mellem |
| 3 | Code-splitting + billedoptimering (mobil LCP) | Høj (ad-ROI) | Lav |
| 4 | Ventetid som oplevelse: RIGTIGE pipeline-stadier + ETA + edu-indhold | Mellem-høj (trust/completion) | Lav-mellem |
| 5 | Server-side Meta Conversions API (Purchase) | Høj (ad-optimering) | Mellem |

---

# 1. KOMPLET PRODUKTAUDIT — hele brugerrejsen

## 1.1 Homepage (aktiv variant: "minimal")
**Styrker:** Stærkt visuelt hero ("SEE YOUR GAME THROUGH SCOUT EYES"), klar primær CTA over folden på både desktop og mobil (målt: CTA ved y=311px på 390px-skærm), "FREE PREVIEW · NO CARD TO START" risiko-reduktion, mobilbund-navigation, cookie-banner er GDPR-korrekt.

**Fundne problemer:**
- 🔴 **Ingen eksempel-rapport at se.** Sektionen "A REAL SCOUTING DOSSIER" beskriver rapporten, men viser den ikke. Forældre køber ikke en $129-rapport, de aldrig har set. (Den tidligere /sample-side blev fjernet — data taler for et bedre alternativ: en interaktiv, anonymiseret rapport-fremviser direkte på forsiden.)
- 🔴 **Cookie-banneret dækker midten af skærmen** ved hvert sidevisning og skjuler CTA'er/pricing indtil klik. Bør være en lille bund-strip.
- 🟠 **"SEE HOW IT ACTUALLY WORKS"**: kun 2 videoer, titel-stavefejl (**"BAGER 2"**), halvtomt carousel-layout på desktop. Ligner ufærdigt arbejde ved første besøg.
- 🟠 **Ingen ægte social proof**: ingen testimonials med navn/billede, ingen tal ("X rapporter leveret"), ingen klublogoer, ingen forældreudtalelser. "TRUST"-sektionen er generisk tekst.
- 🟠 Alt er på **engelsk med USD** — annoncerne kører mod danske forældre.
- 🟡 `/register` findes ikke som rute (redirect til forsiden) — den rigtige rute er `/signup`. Ad/e-mail-links mod /register mister intention.
- 🟡 og:image er et Unsplash-link (ikke eget brand) og og:locale er en_US.

## 1.2 Signup/Login
- Konto kræves FØR upload (login-mur før værdi). Kombineret med et stramt password-krav (10+ tegn, stort/småt/tal/symbol) er det høj friktion for en mor/far på mobilen.
- Ingen social login (Google/Apple) — ville fjerne 80 % af friktionen her.

## 1.3 Upload
- Chunked upload (24 MB-bidder, 500 MB-loft) er solidt og korrekt implementeret.
- NYT (endnu ikke set af rigtige brugere): trøjenummer-felt + "Same player again?"-chips.
- Mangler: video-trim (allerede i backlog), inline vejledning ("sådan filmer du en god klip" — 3 punkter med eksempler), estimeret analysetid ("typisk klar om ~1 minut" — allerede i backlog).

## 1.4 Spillermarkering (MarkerStudio)
- 10-taps-flowet er produktets **stærkeste differentiator** (identitetsgaranti). 
- Risiko: nye brugere forstår ikke HVORFOR de skal tappe 10 gange. En 15-sekunders forklaring/animation ("derfor rammer vi den rigtige spiller 100 %") ville vende friktion til trust.

## 1.5 Ventetid/processing
- Målt preview-tid: **32–100 sek.** — hurtigere end lovet, det er en gave til UX.
- Nuværende overlay har 5 flotte stadier — MEN de er **tidssimulerede**, ikke koblet til de rigtige pipeline-stadier (som allerede findes i `pipeline_trace`!). Detaljer i afsnit 5.

## 1.6 Rapport (web)
- Premium V2 er flot og dyb: 4 pillarer, benchmarks, pace/sprints, movement map, parent metrics, missions, verification-strip, tvivlskontrol.
- 🟠 Fundet fejl: testrapport viste **"VIDEO PREVIEW UNAVAILABLE ON THIS DEVICE"** — edge case hvor videofilen hverken findes lokalt eller hentes fra R2. Skal reproduceres/overvåges.
- 🟡 Rapporten er på engelsk — dansk oversættelses-option ville øge både forståelse og delbarhed blandt danske forældre/trænere.
- 🟡 Ingen delefunktion (link til bedsteforældre/træner) — oplagt organisk vækstkanal.

## 1.7 Betaling
- Embedded Stripe + Apple Pay/Google Pay/Link/PayPal aktive = stærkt setup.
- 🔴 **Prisarkitekturen er forvirrende**: $129 single · $29,99/md Premium · $49,99/md VIP · $89 ekstra · $59 ekstra · $399 pass = 6 prispunkter. En single rapport koster mere end 4 måneders Premium — det giver beslutningsstress i stedet for et oplagt valg.
- 🔴 **USD til danske forældre** — valutafremmedgørelse er dokumenteret konverteringsdræber i consumer-checkout.
- 🟠 Paywall og pricing-sektion viser forskellige tal ($129 vs $29,99) uden at forklare relationen.

## 1.8 Dashboard
- 🟠 Fundet fejl: bruger med købt premium-rapport ser **"CURRENT PLAN: FREE"** — teknisk korrekt (ingen subscription) men forvirrende og devaluerer købet.
- Statskort + trajectory er godt fundament; "hvad nu?"-vejledning mangler (næste skridt-kort).

## 1.9 Tilbagevendende brugere
- NYT: identity memory + profil-chips (endnu ikke i prod).
- JWT udløber efter 24 timer uden refresh-token → brugeren logges ud hver dag. For et abonnementsprodukt er det unødig friktion.
- Curve-reminders (e-mail) findes. WhatsApp/SMS-notifikation "rapporten er klar" ville øge return-rate markant (e-mail åbnes langsomt).

---

# 2. TEKNISK REVIEW (prioriteret efter impact)

## Kritisk (fix før skalering)
1. **JWT_SECRET_KEY er en placeholder** ("...change-in-prod-2026"). Hvis samme værdi kører i produktion, kan enhver forge tokens. → Roter i prod-env.
2. **Stripe LIVE-nøgler i preview-miljøet** — hver test risikerer rigtige træk. → Testnøgler i preview, live kun i prod.
3. **CORS `*`** med credentials — bør låses til scoutmeplay.com-domæner i prod.

## Høj impact (konvertering/hastighed)
4. **Ingen code-splitting** (0 × React.lazy): ReportPage (3.400 linjer) + AdminPage + 2 landing-varianter + recharts + framer-motion i ét bundle. Førstegangsbesøgende på mobil downloader admin-panelet for at se forsiden. → React.lazy pr. rute = hurtigere LCP = billigere Meta-klik (Meta belønner hurtige landingssider).
5. **Meta Pixel Purchase kun client-side**: iOS/adblock-signaltab typisk 20–35 %. → Server-side Conversions API fra Stripe-webhooken (som allerede er pålidelig) med event-deduplikering.
6. **Ingen DB-indexes på reports** (kun users/tokens har). Fint ved 51 rapporter; ved 5.000+ bliver dashboard/admin trægt. → `reports(user_id, created_at)` + `reports(analysis_status)`.

## Mellem
7. **server.py = 12.800 linjer** — funktionelt sundt, men høj regressionrisiko ved hver ændring (bekræftet flere gange i udviklingshistorikken: fil-korruption ved store redigeringer). → Gradvis opsplitning i routers/moduler, IKKE big-bang.
8. **JWT uden refresh-tokens** (24 t udløb) → daglig genlogin.
9. Preview-pipeline er hurtig (32–100 s) og robust (watchdog 300 s + heartbeats + OOM-fixes) ✅. Fuldrapport ~2–4 min. Concurrency-semaforer på plads ✅.
10. Rate limits (login 5/15 min, signup 5/t), single-use reset-tokens, bcrypt ✅ solid auth-hygiejne.
11. Systemets ffmpeg mangler i miljøet (bundled imageio-ffmpeg bruges — virker, men 43 gamle tests fejler bl.a. derfor; testsuiten trænger til oprydning så regressioner kan opdages).

## SEO/teknisk marketing
12. og:image = Unsplash-URL → eget branded 1200×630-billede.
13. Sprog/hreflang: kun engelsk. Dansk version + `hreflang da` er størst enkeltstående SEO-mulighed mod målgruppen.
14. Blog findes (godt) — mangler intern linkstruktur fra forsiden og sitemap-verifikation.

---

# 3. HOMEPAGE & KONVERTERING

**Forskningsgrundlag:** Consumer-konvertering afgøres af: (a) 3-sekunders klarhed, (b) bevis før løfte, (c) friktionsminimering, (d) risiko-reversering, (e) lokal valuta/sprog.

## De første 3 sekunder (nu: OK, kan blive skarpe)
- Hero svarer på "hvad" (scout-rapport af din video) men ikke tydeligt "for hvem + resultat". 
- Anbefalet retning (dansk): **"Få din søns/datters fodbold vurderet som en rigtig scout gør det."** Undertekst: "Upload 1 klip fra telefonen → få en professionel scoutrapport på under 2 minutter. Fra 10 år og op."
- Cookie-banner → lille bund-strip, så hero + CTA aldrig dækkes.

## Første 10 sekunder / før scroll
- Tilføj **3 mikro-beviser under CTA**: "⚡ Klar på ~90 sek." · "🎯 Din spiller — verificeret med 10 tryk" · "🧠 AI + rigtig scout".
- Autoplay-lydløs 10-sekunders video af en rapport, der scroller (bevis > beskrivelse).

## Før klik på Upload
- **Interaktiv eksempel-rapport** ("Se en rigtig rapport") — anonymiseret, med blur på navn. Dette er den vigtigste enkeltstående tilføjelse på hele sitet.
- Ægte social proof: 3 forældre-citater m. fornavn+by, antal analyserede klip, evt. "som set i…" 

## Før kontooprettelse
- Overvej **guest-flow**: lad upload + markering ske FØR signup, kræv kun e-mail for at få rapporten ("giv os din e-mail, så sender vi rapporten"). Alternativt minimum: social login (Google/Apple) + lempeligere passwordkrav (12+ tegn uden symbolkrav er både sikrere og venligere).

## Før betaling
- **Prisforenkling til 3 valg** i DKK: fx "1 rapport · 199 kr" / "Premium · 229 kr/md (2 rapporter/md)" / "VIP · 379 kr/md (+ rigtig scout)". Sæt månedsprisen som anker med "MEST VALGT".
- Garanti-badge ved købsknappen: "Ikke tilfreds med rapporten? Pengene tilbage inden 14 dage."
- Wallets først (Apple Pay-knap synlig med det samme på iOS).

## Sektioner der bør justeres
| Sektion | Anbefaling |
|---|---|
| Hero | Skarpere målgruppe-løfte + mikro-beviser |
| How it works | Behold — tilføj 10-tap-forklaringen som trust-punkt |
| What's inside | Erstat statiske kort med interaktiv eksempel-rapport |
| Pricing | 3 valg, DKK, anker, garanti |
| Social proof | NY sektion: citater + tal + demovideoer (fix "BAGER 2") |
| FAQ | Tilføj: "Er det sikkert for mit barn?", "Hvem ser videoen?", "Hvad hvis AI'en tager fejl?" (GDPR/tryghed er forældres skjulte indvending) |
| Footer | Dansk virksomhedsinfo (CVR) øger trust |

---

# 4. UPLOAD & DASHBOARD

**Upload:** trim-slider (backlog), inline filmeguide (3 punkter), forventet tid ("~90 sek."), jersey/profil-chips er allerede på plads ✅.

**Dashboard-anbefalinger:**
1. Fix "CURRENT PLAN: FREE" for købere (vis "1 rapport købt" / abonnementsstatus korrekt).
2. "Næste skridt"-kort øverst: "Ny kamp i weekenden? Upload 2. klip og se udviklingskurven."
3. Spillerkort pr. barn (identity memory er bygget — vis den!): billede-crop, seneste score, trend-pil.
4. Progressgraf som centerpiece efter 2+ rapporter (trajectory-siden findes, men er gemt).
5. Abonnementsstyring: synlig plan + skift/opsig (reducerer support og chargebacks).

---

# 5. VENTETIDSOPLEVELSEN (32–100 sekunder)

**Forskning:** "Labor illusion" (Buell & Norton, Harvard): brugere stoler MERE på resultatet og venter gladere, når systemet VISER det arbejde, der udføres. Peak-end-reglen: slut-øjeblikket (rapport-reveal) definerer hele oplevelsen.

**Nuværende:** 5 flotte simulerede stadier. **Guldet ligger i, at backend allerede logger RIGTIGE stadier** (`pipeline_trace`: transcode → anchors → clip → identity → gemini → poster → ready) — de skal bare streames til skærmen.

**Anbefalet oplevelse (rækkefølge = eksisterende pipeline):**
1. ✅ Video modtaget (upload complete)
2. 🎞 Forbereder optagelsen (transcoding)
3. 🔍 Bekræfter indholdet (content gate)
4. 🎯 Låser din spiller fast — "7/7 markeringer verificeret" (identity profile — VIS antallet!)
5. 🧠 Scouten ser hver aktion (Gemini analyse)
6. 🖼 Bygger din rapport (poster/färdig)
+ **ETA baseret på rullende gennemsnit** af de sidste 20 rapporter ("typisk 90 sek. — 40 sek. tilbage").
+ Ved fuldrapport: samme princip + tvivlsmoment-prompten (allerede bygget!) som aktiv del af ventetiden — "hjælp scouten"-øjeblikket er engagement, ikke friktion.

# 6. HOLD FORÆLDRE ENGAGERET I VENTETIDEN
Roterende edu-kort under progress-baren (8–10 sek. pr. kort):
- "Sådan vurderer en scout førsteberøring" (m. mini-illustration)
- "Hvad betyder 'off-ball arbejde'?"
- "Din rapport indeholder: 4 pillarer + topfart + udviklingsplan" (sample-udsnit)
- "Vidste du: spillere vurderes ALTID mod deres egen aldersgruppe her"
- "AI'en gætter aldrig — er der ikke evidens, siger rapporten det ærligt"
Effekt: forælderen ankommer til rapporten FORBEREDT på at forstå den → højere oplevet værdi → højere betalingsvilje. Slut med confetti-reveal (peak-end).

---

# 7. RAPPORT & PDF — hvad forældre virkelig vil vide

Markedsresearch (scouting-templates + forældrefora) viser forældre vil have: **klart sprog, eksempler i klip, udvikling over tid, næste skridt** — ikke jargon. Rapporten dækker allerede: styrker/svagheder, spillestil/arketype, 4 pillarer, benchmarks, pace, parent metrics, træningsplan, missions ✅.

**Reelle gaps (prioriteret):**
1. **Bedste position + alternative positioner** — efterspurgt i alle scouting-templates; findes kun implicit. Tilføj "Primær: RW · Alternativ: AMF (fordi …)".
2. **Dansk oversættelse** af rapport + PDF (øger forståelse + deling).
3. **Share-link** (læse-adgang uden login) — bedsteforældre/træner = organisk vækst.
4. **Progress-side i PDF** efter 2+ rapporter ("siden sidst: +0,4 på teknik").
5. **"Sådan læser du rapporten"** — 5-linjers guide forrest i PDF'en til førstegangskøbere.
6. Confidence-visning pr. score (backend har evidensregler — vis det: "baseret på 14 observerede aktioner").

---

# 8. AI-NØJAGTIGHED — reducér hallucination yderligere

**Allerede bygget (stærkt fundament):** 10-taps ground truth, dual-AI verifikation (GPT-4o ↔ Gemini), farve-veto tracking, tvivlsmoment-kontrol, trøjenummer-check, identity memory, ærlige "not enough evidence"-regler, hedging-scrub, ingen AI-tal i fysiske metrikker.

**Næste niveau (prioriteret):**
1. **Confidence-badges i UI pr. sektion** (data findes allerede internt) — "Høj sikkerhed (12 observationer)" → trust uden ekstra AI-kald.
2. **Minimum-observationskrav pr. score**: hvis < N relevante aktioner set, vis "Ikke nok evidens i dette klip" i stedet for en score. (Delvist implementeret via prompts — gør det til hård regel + UI-state.)
3. **QA-pass på fuldrapporter**: verify_preview_summary findes for preview — udvid med en billig anden-model konsistenstjek af fuldrapporten (fanger selvmodsigelser før publicering).
4. **Admin-stikprøve-kø**: hver 10. rapport flagges til menneskelig kvalitetstjek; fejl kategoriseres → prompt-forbedringer bliver datadrevne.
5. **Offentlig nøjagtighedsside**: udbyg /methodology med "sådan undgår vi at forveksle spillere" (10 tryk + farve-veto + dual-AI + din bekræftelse) — gør jeres største tekniske arbejde til jeres største marketing-aktiv.

---

# 9. INNOVATIVE FEATURES (vurderet: værdi · feasibility · nøjagtighed · moat · abonnementspotentiale)

| Feature | Værdi | Feasibility | Moat | Abo-effekt | Anbefaling |
|---|---|---|---|---|---|
| **Delbar highlight-video m. score-overlay** (auto-klip af top-øjeblikke + branding → Instagram/TikTok) | Meget høj | Mellem (klip findes via timestamps) | Høj — viral loop ingen konkurrent har | Høj (kræver Premium) | ⭐ BYG |
| **Sæson-/multikamp-rapport** (aggregat på tværs af uploads pr. spillerprofil) | Høj | Lav-mellem (identity memory er bygget!) | Høj | Meget høj (abonnements-BEGRUNDELSEN) | ⭐ BYG |
| **Voice pep-talk fra scouten** (planlagt) | Mellem-høj (peak-end wow) | Lav (TTS) | Mellem | Mellem | BYG (billig wow) |
| **Chat med scouten** (rapport-bundet, planlagt) | Høj (forældre-spørgsmål) | Lav-mellem | Mellem | Høj (Premium-perk) | BYG |
| **Træner-invitation** (gratis læseadgang → træneren ser 5 spilleres rapporter → køber til holdet) | Høj (B2B2C-kanal) | Lav | Mellem | Høj | BYG SENERE |
| **Trial-readiness-pakke** (forberedelse til prøvetræning: rapport + fokuspunkter + pep-talk) | Mellem-høj | Lav (ompakning) | Mellem | Engangs-upsell | OVERVEJ |
| Milestone-badges til børn | Mellem | Lav | Lav | Mellem (retention) | OVERVEJ |
| Sammenligning med holdkammerater | – | – | – | – | ❌ FRARÅDES (privacy + toksisk dynamik) |
| Live-analyse under kamp | Lav (urealistisk kvalitet) | Meget høj kompleksitet | – | – | ❌ IKKE NU |

---

# 10. KONKURRENTANALYSE (2026)

| Platform | Model | Styrke | Svaghed (= jeres mulighed) |
|---|---|---|---|
| **Veo** | $67–134/md + kamera-hardware | Markedsleder team-video, poleret økosystem | Dyrt, team-fokus, analytics koster ekstra, INGEN individuel scoutrapport |
| **Trace/PlayerFocus (Hudl)** | $25–35/md pr. familie | Spillerfokuserede highlights, familievenlig | Highlights ≠ analyse; ingen vurdering/score/udviklingsplan; pris skalerer pr. barn |
| **aiSCOUT (ai.io)** | Gratis for spillere, klubber betaler | Scouting-eksponering, kendte klubpartnere | Drill-baseret — analyserer IKKE kampvideo; værdi afhænger af klubadoption |
| **Småapps (AIM, SoccerLogics, LevelUp m.fl.)** | $5–20/md | Billige, mobile | Overfladisk feedback, ingen identitetsverifikation, ingen trust/evidens, ingen menneskelig scout |
| **Hudl/Wyscout/SkillCorner** | B2B | Pro-standard | Slet ikke forældre-tilgængelige |

**Jeres unikke position (ingen har alle fem):**
1. Ingen hardware — bare telefonen. 2. Individuel spiller, ikke hold. 3. Identitetsverificeret tracking (10 tryk + dual-AI) — **ingen konkurrent kan love "vi analyserer garanteret DIT barn"**. 4. Evidensbaseret rapport m. timestamps. 5. AI + rigtig scout hybrid.

**Positioneringssætning:** *"Veo filmer holdet. Trace klipper highlights. ScoutMePlay fortæller dig, hvor god dit barn faktisk er — og hvad næste skridt er."*

Prisbenchmark: Trace $25–35/md er referenceprisen i forældres hoved. Jeres $29,99/md Premium ligger rigtigt — men $129 single skaber forvirring om, hvad produktet "koster". → gør månedsabo til helten.

---

# 11. WEBSITE-STRUKTUR / IA

**Kan en ny bruger på 10 sek. forstå:** Hvad det er ✅ · Hvorfor stole på det 🟠 (mangler bevis) · Hvordan upload virker ✅ · Hvad der sker efter upload 🟠 · Hvad Free vs Premium giver 🟠 (6 prispunkter) · Hvor rapporter bor ✅ · Progress-sammenligning 🟡 (gemt bag trajectory).

**Anbefalet struktur:**
```
Forside (minimal, konverteringsfokus)
├── Sådan virker det  (inkl. 10-tap trust-forklaring)
├── Se en rapport     ⭐ NY — interaktiv anonymiseret eksempelrapport
├── Priser            (3 valg, DKK, garanti)
├── For forældre      ⭐ NY — tryghed: GDPR, hvem ser videoen, alderskalibrering
├── For scouts/klubber (findes)
├── Metode & nøjagtighed (udbygget /methodology)
├── Blog (SEO)
└── Log ind / Kom i gang
```
+ Fix `/register`-redirect → /signup. + Dansk sprogversion med hreflang.

---

# 12. PRIORITERET ROADMAP + FORVENTET EFFEKT

## FASE 0 — Kritiske fixes (1–2 dage)
| # | Tiltag | Hvorfor | Effekt | Kompleksitet |
|---|---|---|---|---|
| 0.1 | Roter JWT-secret i prod + CORS-låsning | Sikkerhed | Risikoeliminering | Triviel |
| 0.2 | Stripe TEST-nøgler i preview | Undgå utilsigtede rigtige træk | Risikoeliminering | Triviel |
| 0.3 | Fix "BAGER 2"-stavefejl + dashboard "FREE"-planvisning + /register-redirect | Poler synlige fejl | Trust | Triviel |

## FASE 1 — Konverteringsmotor (1–2 uger) → forventet største omsætningsløft
| # | Tiltag | Effekt (est.) | Kompleksitet |
|---|---|---|---|
| 1.1 | **Interaktiv eksempelrapport** på forsiden | 🔥 Upload-start +20–40 % (bevis før løfte) | Lav |
| 1.2 | **DKK + prisforenkling (3 valg) + garanti-badge** | 🔥 Checkout-completion +10–25 % | Mellem |
| 1.3 | **Code-splitting + eget og:image** | Mobil-LCP ↓ → lavere CPC, bounce ↓ | Lav |
| 1.4 | **Cookie-banner som bund-strip** | Fjerner CTA-blokering | Lav |
| 1.5 | **Social proof-sektion** (citater, tal, flere demovideoer) | Trust ↑ | Lav |
| 1.6 | **Server-side Meta Conversions API** | +20–35 % attribution → bedre ad-optimering | Mellem |

## FASE 2 — Oplevelse & fastholdelse (2–3 uger)
| # | Tiltag | Effekt | Kompleksitet |
|---|---|---|---|
| 2.1 | Ventetid 2.0: rigtige pipeline-stadier + ETA + edu-kort + reveal | Completion ↑, oplevet værdi ↑ | Lav-mellem |
| 2.2 | Dansk sprogversion (site + rapport-option) | Konvertering i kernemarkedet ↑↑ | Mellem-høj |
| 2.3 | Share-link til rapport + træner-invitation | Organisk vækstloop | Lav-mellem |
| 2.4 | Dashboard: spillerkort + næste-skridt + synlig progress | Retention/abo ↑ | Mellem |
| 2.5 | Social login + lempet passwordpolitik + refresh-tokens | Signup-completion ↑ | Lav-mellem |

## FASE 3 — Differentiering & abonnementsværdi (3–6 uger)
| # | Tiltag | Effekt | Kompleksitet |
|---|---|---|---|
| 3.1 | Delbar highlight-video m. scores (viral) | Ny akvisitionskanal | Mellem |
| 3.2 | Sæsonrapport på tværs af uploads | Abonnements-BEGRUNDELSE | Mellem |
| 3.3 | Voice pep-talk + Chat med scouten | Wow + Premium-perk | Lav-mellem |
| 3.4 | Confidence-badges + admin QA-kø + methodology-udbygning | Trust-moat | Lav-mellem |
| 3.5 | DB-indexes + gradvis server.py-opsplitning | Skalering/stabilitet | Mellem (løbende) |

**Ærlighed om estimater:** Konverterings-procenterne er kvalificerede estimater baseret på branchemønstre — jeres nuværende datamængde (43 brugere) er for lille til statistisk sikre forudsigelser. Netop derfor er rækkefølgen: fix trafik→bevis→pris FØRST, så Meta-pixel-dataene fra Fase 1 kan validere resten.

---
*Rapport udarbejdet juni 2026. Intet i kodebasen er ændret. Afventer godkendelse af roadmap før implementering.*
