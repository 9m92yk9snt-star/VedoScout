# Gates i analyseforløbet: formål, rækkefølge og live-blokeringer

Undersøgt 4. oktober 2026 UTC / 5. oktober dansk tid. Supplerer
[pipeline-auditten](ANALYSIS_PIPELINE_AUDIT.md). Ingen produktrettelser,
merge/deploy, nye modelkald eller produktionswrites i denne udvidelse.

## Hovedkonklusion

Mange gates er nødvendige: adgang, korrekt medietid, samme spiller, samme
bold, målretning, keeperrolle og kanonisk deduplikering løser forskellige
problemer. Antallet alene siger ikke, om systemet er godt. Flere gates
genbruger desuden samme evidens; de er ikke flere uafhængige beviser.

Den vigtigste arkitektoniske svaghed er, at krav til **publicerbart bevis**
også styrer **adgangen til afklarende undersøgelse**. Identitets-/holdhuller
kan derfor forhindre et målreview, der kunne levere ny udfaldsevidens.
Det er ikke en absolut cirkel: fysisk kontakt kan findes uden GLOBAL_TARGET,
jersey-review kan bruge unresolved touches med et enkelt track-ID, og
okklusionsrecovery findes. Men disse hjælpere har egne selektionskrav og
reparerer ikke automatisk alle tidligere usikre frames/kontakter.

I live-rapporten kørte FIX10A/B og FIX11. Alle 56 gemte beslutninger om
målreview er reproduceret præcist fra strikes/touch graph: **15 tilladt,
41 blokeret**. Slutgates for retning og boldbevis ændrer ingen af de 56
gemte udfald, fordi ingen har verificeret mållinjepassage. De er således
ikke stedet, hvor verificerede mål forsvandt i den gemte live-evidens.
Et review, der ikke blev kørt, ville ikke nødvendigvis have bevist et mål.

## Grundlag og grænser

- `main`: `f051fa11c6d73eccb0e15a643c57b6d7c5f9fccd`.
- Draft PR #21 før denne udvidelse: `f1db23dd188aa0c43a39fca60ddb6cd31a587e35`.
- De 15 autoritative live-traces er kontrolleret mod Mongo-manifestets
  ukomprimerede SHA-256 og gzip-størrelser. Rå mediefiler, links og
  credentials lægges ikke i repository.
- Den præcise deployed commit og alle live-miljøindstillinger er ikke
  verificeret. Tal i kodekolonnen nedenfor er kodekontrakter/defaults,
  ikke en aflæsning af produktionskonfigurationen.
- Auditten følger den analyserelaterede kaldesti og dens specialistmoduler,
  frontend, upload, recovery, modeladapters og publicering. Den er ikke en
  linje-for-linje verifikation af alle øvrige produktfunktioner.
- De 40 rækker er **gatefamilier**, ikke et optalt antal `if`-sætninger.
  Mange af dem har flere underkrav og alternative proof lanes.
- Scriptet kører faktisk kode i checkoutet. Live-eligibility og de to
  slutgates er uændrede mellem det undersøgte `main` og PR #21.
  PR #21 har allerede draftændringer til tracking, kit-modellen,
  goal-framevalg og dækning. De må ikke beskrives som deployed.

## Gatekort fra upload til rapport

| ID | Gatefamilie og kode | Hvad den styrer | Nytte og vurdering |
| --- | --- | --- | --- |
| G01 | Auth, ejerskab og betaling: `server.py`, `chunked_upload.py` | Upload, læsning, oplåsning og start | Bevar. Betaling er adgang til fuld analyse, ikke fodboldbevis; admin tæller som betalt. |
| G02 | Inputkrav: `UploadPage.jsx::handleSubmit`, uploadendpoint | Fil, marker, spillerdata, land og foto | Nogle krav er produktvalg. Manglende foto/land siger intet om boldkontakt; vis dem som formularfejl. |
| G03 | Fil/session/chunks/URL: `chunked_upload.py`, `url_video_fetch.py`, uploadendpoint | 500 MiB samlet, 32 MiB per chunk, chunk-ejerskab og alle dele; URL-download maks. 200 MiB/120 s, Veo-linkafvisning og temp-token; direkte upload MIME-kontrol | Bevar transport- og integritetskrav. URL og fil har forskellige caps. Temp-fil skal findes eller kunne hentes fra R2; tokenfejl kommer før modellen. |
| G04 | Varighed/ffprobe: upload og `analyze_preview_task` | Kamp mindst 30 s, andet mindst 15 s; maks. 305 s med afrundingsbuffer | Bevar decode/metadata-kontrol. Minimum er produktpolitik og bør ikke kaldes et evidenskrav. |
| G05 | Anchors: `_build_original_anchor_payloads`, FIX00A, valid anchor-filtrering | Original tid/boks og brugbare seeds; original anchorlimit 13 | Bevar originalerne og provenance. En mislykket crop må ikke slette brugerens tap. 11 originaltaps findes i live-rapporten. |
| G06 | Web-/LLM-rendition: `_ensure_analysis_video`, medietidsmoduler | Afkodning og payloadstørrelse; default 45 MiB før ekstra LLM-komprimering | Nødvendigt for transport. Tracking/proof bruger canonical web-video; LLM kan få en anden komprimeret rendition. Gem begge hashes og tidbaser. |
| G07 | Content gate: `run_content_gate`, `gate_rejection_message` | Gratis previews: fodbold, watchability og markeret spiller synlig | Betalt/admin springer over. Exceptions er fail-open med syntetisk `good/clear`; markér `skipped/error/unknown`, ikke målt god kvalitet. Ikke live-scoringsårsagen. |
| G08 | Identitetsprofil/previewkontekst: `analyze_preview_task`, `identity_verify.py` | Profil fra originalcrops og eventuel tidligere profil | Hjælp til modelsøgning; timeout/fejl er ikke et nyt identitetsbevis. Tidligere profiler skal have provenance og må ikke erstatte aktuelle pixels. |
| G09 | Preview-verifikation/retry: `server.py` | Høj negativ identitetslæsning kan give ét nyt preview og lav confidence | Nyttig korrektur. Preview er kun ca. 15 s omkring marker og dokumenterer ikke fuld videodækning. |
| G10 | Start/genbrug/recovery: `generate_full_report_task` | Betalt upload autostarter; eksisterende body/ready kan genbruges eller kun finaliseres | Skeln frisk analyse, genbeskrivelse og nye evidensbilleder. `regenerate-evidence` finder ikke manglende mål. Jobstart skal være atomisk. |
| G11 | FIX09-preparation: `server.py`, `player_identity_timeline.py` | `IDENTITY_TIMELINE_ENABLED`, valid anchors, timeline `ok`, preparation `prepared` | Mangler kan vælge legacy FIX08; FIX10A/FIX11 følger da ikke med. Log eksplicit valgt pipeline og skipped stages per run. |
| G12 | FIX04 tracking: `player_tracking.py`, feature/recovery-hjælp i `cv_shadow.py` | Seed, appearance match, farveveto, misses, drift og sceneskift | Bevar beskyttelse mod spillerbytte. Kamera-/overlapmodeller skal repareres før generel sænkning af thresholds. |
| G13 | FIX09A/fusion: `player_identity_timeline.py`, `unified_identity_authority.py` | Multi-frame identitet, margin, bevægelse, source agreement, unresolved barrierer | Bevar tvivl og scenegrænser. Defaults bl.a. 5 Hz, similarity 0.45, margin 0.10. Huller skal udløse afklaring, ikke forsvinde fra dækningsregnskabet. |
| G14 | All-player graph/hold: `football_scene_graph.py`, `cv_detect.py` | Detektion/MOT, ball ambiguity, target mapping og kit/team-clustering | Lokal CV, ikke LLM. Samme farve er støtte for hold, ikke identitet. Usikker holdklassifikation skal kunne undersøges før målreview afvises. |
| G15 | Sequence-plan: `football_sequence_intelligence.py` | Aktive targetspans, tidsvinduer, overlap, refinement, scene cuts | Sparer kontekst og begrænser historier. Aktive spans er identitetsafhængige; refinement er en ekstra lane, ikke garanti for fuld recall i huller. |
| G16 | Model-JSON/coverage: `call_gemini_with_video`, `unified_analysis_engine.py` | Parse, window IDs, antal actions og komplet kontrakt; én bounded coverage-retry | Bevar kontraktvalidering. JSON-retry og coverage-retry er to lag. En ufuldstændig sekvens kan blokere hele den fysiske lane. |
| G17 | Action-normalisering: `football_sequence_intelligence.py` | Typer, window/start/end/contact, antal og gyldige evidenstider | Nødvendigt mod hallucinerede/misplacerede tidspunkter. Rejection-reasons skal bevares; fjernede observationer må ikke ligne en komplet negativ scan. |
| G18 | Kanonisk actor/kausalitet: `canonical_event_resolver.py` | Entydig target, receiver/hold, samme scene og bevist årsagskæde | Bevar før publicering. Afvist GOAL/ASSIST må ikke generelt slette en separat verificeret PASS/SHOT. Modelord alene er ikke bevis. |
| G19 | Fysisk runtime-start: `fix10a_runtime.run` | Unified `ok` og sequence `coverage_complete=true` | Reproduceret all-or-nothing-kobling. Undersøg fysisk behandling af sikkert afgrænsede delvinduer uden at kalde det komplet dækning. |
| G20 | FIX11 recall: `full_video_event_recall.py` | Target possession/relation triggers; før 1.4 s, efter 5.6 s, maks. 8 s og cuts | Semantikuafhængig, men graph-lane kræver VERIFIED/HYPOTHESES med track-ID. Bevar cuts; tilføj en begrænset lane til usikre relevante aktioner. |
| G21 | Dense body mapping: `dense_replay.py`, `dense_track_refinement.py` | Hver kildeframe i valgte vinduer, association, ambiguity, ID-skift og tapbinding | Bevar entydighed. Dense vinduer er ikke en fuld dense scan af hele videoen. PR #21 har endnu ikke deployed recoveryændringer. |
| G22 | Boldbane/provenance: `ball_trajectory.py`, `motion_compensation.py`, `video_timebase.py` | Aktiv bold, measured/predicted, faktisk PTS, reacquisition og spare-ball-afvisning | Kritisk. En predicted box må gerne skabe en kandidat, men må ikke automatisk blive fysisk kontaktbevis. |
| G23 | Kontakt: `ball_contact_engine.py` | Lower-bodyafstand, begge sider, dynamics/possession, continuity, association og proof | Bevar fysik. Default afstand ≤0.58 spillerhøjde, sidevindue 180 ms, samlet confidence ≥0.62. `CONTACT_TIME_NOT_EXACT_PROOF` blander tid og bold-proof. |
| G24 | Kort okklusion: `short_occlusion_contact_recovery.py` | Målt bold før/efter, flow/reacquisition, actor-path, tap og scenebarrierer | En reel recoverylane; 14 kontakter genoprettet live. Mulige kontakter skal beholdes til afklaring; prediction alene er stadig utilstrækkelig. |
| G25 | Touch graph/binding: `touch_graph.py` | Sammenlægning 160 ms, actor/status, target og lokale holdprøver | Nyttig deduplikering. Reproduceret: VERIFIED og CANDIDATE_OCCLUDED får separate grupper; en svag kontakt forgifter ikke automatisk den stærke. |
| G26 | Contact role: `contact_role_resolver.py` | RELEASE mod RECEIVE_CONTROL, separation, quick recontact, Step3 recovery | Nødvendigt: modtagelse er ikke aflevering/skud. Repeated measured separation er en alternativ afklaring; ingen generel promotion fra en modelhistorie. |
| G27 | Jersey-udvælgelse/budget: `jersey_consensus.py`, `fix10a_vision_providers.py` | Involved tracks med ID, ikke HYPOTHESES body association, bboxareal ≥0.008, afstand 120 ms; op til 5 crops | Kan selektere usikre touches med enkelt ID, men ikke alle tvetydige bodies. Default 24 reads gælder per provider-kald/vindue, ikke hele rapporten. Prioritering skal være auditerbar. |
| G28 | Jersey-konsensus/handoff: `jersey_consensus.py`, `unified_identity_authority.py` | To high/medium enige reads, vægtandel ≥0.70, margin ≥0.25; yderligere tap-/body-/touchkrav | Kommentar om minimum tre frames stemmer ikke med faktisk konsensus: to kan verify. Vægtandelen er ikke kalibreret sandsynlighed. Handoff kræver verificeret kontakt og reparerer ikke alle tidligere frames. |
| G29 | Strike-opbygning: `shot_outcome_engine.py` | Verificeret release; særskilt target scoring-control lane | Nødvendigt mod at alle touches tælles som skud. Fysisk strike kan findes uden targetejerskab; target kræves først i andre beslutninger. |
| G30 | Adgang til målreview: `physical_match_reconstruction.py::_goal_review_eligibility` | Targetkontakt eller verificeret holdkammeratrelease inden 5200 ms efter targetpass i samme scene; holdconfidence ≥0.70 | Dokumenteret flaskehals: 35 ingen prior targetrelease + 6 usikkert hold. Flyt relevante uafklarede kandidater til afklaringsreview; behold strenge krav til tilskrivning/publicering. |
| G31 | Intervention/keeper: `post_strike_intervention.py`, supporting role reader | Krop + selvstændig boldændring; separat rolleklassifikation | Bevar. Markspillerintervention er ikke keeperredning. Default role-budget 4 tracks × 4 frames per vindue, mindst to enige high/medium-læsninger. |
| G32 | Målreader/budget/frames: `fix10a_vision_providers.py`, `fix10a_goal_direction.py` | Key/SDK/video, mindst 2 frames, maks. 12 billeder, cache og default 16 reviews per rapport | Ingen gemt budget-exhaustion live. Cache er window-ID/tid; overlappende vinduer kan bruge flere reviews på samme fysiske aktion. På main kan head-slicing af 12 frames miste 2.2/2.6 s sen kontekst; draft PR #21 ændrer valget. |
| G33 | Hele bolden over linjen: `shot_outcome_engine.py`, `fix10a_occluded_goal.py` | Geometri, boldradius, samme bold, tider; measured, structured visual eller stramt afgrænset occluded lane | Bevar. Mållinjegeometri, jubel eller `crossed=true` beviser ikke hele bolden. Struktureret visuelt bevis kan passere uden detector-boldrows. |
| G34 | Retning: `fix10a_goal_direction.py::apply_direction_gate` | Kun VERIFIED independent crossing; playable field side → goal side | Bevar. Beskytter mod bold ud af nettet/fejlretning. Alle 56 gemte live-udfald er uændrede ved reapplication; ingen havde VERIFIED crossing. |
| G35 | Bold-proof: `fix10a_ball_proof_gate.py` | Kun VERIFIED crossing; faktisk PTS/proof på målinger eller certificeret alternativ lane | Bevar. Beskytter mod predicted/spare-ball-bevis. Alle 56 gemte live-udfald er uændrede; gaten forklarer ikke de manglende scorerforslag. |
| G36 | SAVE: `shot_outcome_engine.py` | Verificeret intervention, keeper, tilstrækkeligt non-crossing og catch/stop/away | Bevar. UNRESOLVED crossing beviser ikke, at bolden ikke krydsede linjen. Live: 37 rejected, 19 unresolved saves. |
| G37 | FIX10B registrering: `fix10b_reconciliation.py` | Scorer, target, causal ball lineage, teammate, cuts, dedup; direct receive/shot/goal-horisonter | Bevar final truth. Defaults 2.4/4.2/5.2 s er policy/kausale bounds, ikke universelle fodboldlove. Evaluer længere kæder uden at registrere holdkammeratens mål som #15's mål. |
| G38 | Output/statistik/tekst: `canonical_output_authority.py`, `verified_stats.py`, rapportprompt | Kanonisk timeline/counts, begrænset evidensudvalg, scores, GYG og narrative claims | Bevar én eventmyndighed. Højst 8 native evidence rows er en visningsgrænse, ikke event-detection cap. PARTIAL skal give ufuldstændige totaler, ikke sikre nul. Modelstyrke/tekstkontrol er ikke objektiv 100%-proof. |
| G39 | Billeder/klip/identitet: `_persist_video_frames`, FIX00B/FIX03/FIX05 | Faktisk frame-tid, proof, event-ID, entydig boks; legacy identity-reader; clip-edge/shrink | Bevar præcise bevisbilleder. Canonical locked frames kan gå direkte uden endnu et LLM-kald. Manglende billede skal forklares separat fra manglende event. |
| G40 | READY/watchdog/polling: `_finalize_full_report`, `_sweep_stuck_full_reports`, `ReportPage.jsx` | Færdig jobtilstand, retries, heartbeat, ventetid og UI-fejl | Driftsgates giver mening, men tidligere audit reproducerer fejl. READY betyder finaliseret, ikke perfekt recall; færdige tomme canonical responses kan være ready. |

## Hvad modellerne faktisk hjælper med

| Modelvej | Rolle og grænse | Betydning for gates |
| --- | --- | --- |
| Gemini 2.5 Pro: content gate og preview | Gratis content gate; kort preview med brugeranchors | Kan afvise input/rette preview. Betalt/admin går uden om content gate. |
| OpenAI gpt-4o: identitetsprofil og legacy frame-verifikation | Identitet fra crops/context; høj negativ læsning kan udløse korrektur | Støtte til identitet, ikke bold-/målbevis. Profilfejl må ikke kaldes verificeret fravær. |
| Gemini 2.5 Pro: sequence intelligence | Whole-video input med planlagte windows og struktureret action-kontrakt | Udleder kandidater. Windowplan/normalisering og senere fysisk/kanonisk bevis bestemmer, hvad der accepteres. |
| OpenAI gpt-4o: jersey og intervention role | Pixelbaseret nummer/keeperlæsning på udvalgte frames | Kan kun hjælpe med de requests, selektionsgates faktisk leverer. Readeren må ikke få forventet #15 eller ønsket udfald som facit. |
| OpenAI gpt-4o: goal geometry/whole-ball review | Kronologiske billeder, mållinje, samme bold, crossing og struktureret proof | Kaldes først efter eligibility. Separate field-side reads hjælper retning; to reads er ikke nødvendigvis statistisk uafhængige. |
| Gemini: fuld rapport, legacy discovery/verifikation og korrektiv genbeskrivelse | Formulerer rapport og betjener fallback/recoveryveje | Canonical projection ejer events/tal. Genbeskrivelse af samme canonical bundle genskaber ikke et tidligere uopdaget mål. |

Default timeouts er bl.a. 420 s på sequence-video-call, 60 s på jersey/role
og 90 s på goal/field-side vision. Begrænset parallelisme og budgets
beskytter drift/omkostninger; de dokumenterer ikke korrekt videoforståelse.
Gemte votes er ikke et regnskab over alle fakturerede API-requests. Modelnavne
og flags er konfigurerbare, og præcise live-værdier skal snapshots per run.

Sequence-loopens op til to kontraktforsøg og video-wrapperens JSON-retry er
to forskellige niveauer: en inkomplet kontrakt kan medføre et ekstra
window-retry, og hver wrapper kan selv lave en parse-retry. Beskriv derfor
ikke denne vej som ubetinget ét faktureret modelkald. FPS-tal i prompten er
heller ikke dokumentation for udbyderens faktiske videoframesampling.

CV/person/ball/flow/kit og de deterministiske gates er lokale beregninger,
ikke LLM-kald. Dense replay gennemgår hver kildeframe i udvalgte vinduer.
At alle planlagte vinduer blev eksekveret, viser derfor ikke, at alle reelle
aktioner i hele videoen blev undersøgt eller bevist.

## Præcis kontrol af live-rapportens blokeringer

`backend/scripts/audit_analysis_gates.py --trace-dir <privat lokal mappe>`
læser kun de filer, manifestet opregner, kontrollerer hashes/størrelser og
kører de faktiske eligibility-/slutgatefunktioner. Resultat:

| Kontrol | Resultat |
| --- | --- |
| Manifestvaliderede traces | 15 af 15 |
| Eligibility genberegnet identisk med gemt beslutning | 56 af 56 |
| Review tilladt | 15: 5 targetreleases, 3 target scoring contacts, 7 teammate-releases |
| Review blokeret | 41: 35 uden prior targetrelease, 6 uden verificeret targetteam |
| Verificeret goal-plane crossing | 0 |
| Direction-gate reapplication uændret | 56 af 56 |
| Ball-proof-gate reapplication uændret | 56 af 56 |
| Gemte `GOAL_REVIEW_BUDGET_EXHAUSTED` | 0 |

Reapplication dokumenterer adfærd på de gemte **slutudfald**. Uden separate
før/efter-snapshots beviser den ikke, at en midlertidig kandidat aldrig blev
nedgraderet undervejs. De gemte udfald har heller ingen downgrade-reason fra
disse to gates. Der er dermed intet gemt bevis for, at de fjernede et allerede
verificeret mål i dette run.

Ved referenceskuddet 23.68 s og målet 30.83 s findes henholdsvis tre og seks
kontaktkandidater inden for ±350 ms. Alle ni har faktisk
`time_authority=ACTUAL_MEDIA_PTS`, men `ball_at_contact.state=PREDICTED_SHORT_GAP`
og `proof_eligible=false`. Den eneste rejection-reason er
`CONTACT_TIME_NOT_EXACT_PROOF`. Kodens `exact_time` kræver **også** bold-proof:

```python
exact_time = (
    ball.get("proof_eligible") is True
    and ball.get("time_authority") == "ACTUAL_MEDIA_PTS"
    and cur_frame.get("used_fallback") is not True
)
```

Denne reason må derfor ikke fortolkes som dokumenteret klokke-/PTS-fejl.
Den konkrete boldbane er predicted/non-proof, og samtidig mangler target-
identitet i alle 42 gemte nærliggende observationer ved hver reference.
Det er to forskellige blockers. Timestampændring alene løser dem ikke.

Ved 43.19 s findes targetkontakt, men ingen bevist pass-to-goal-kæde.
Ved 49.44 s findes modtagelse, men den efterfølgende release er unresolved
og identiteten har huller. Referencekæden er #7 → #15 → #10 mål.
Ved 56.44 s findes targetrelease, men efterfølgende scorerreviews blokeres
af usikkert hold. Referenceaktioner må bruges som evaluering, aldrig som
hardcoded produktionsevents. Se fem-aktionen-tabellen i pipeline-auditten.

## Overlap og nytte: hvad bør beholdes eller ændres?

**Behold ved publicering:** korrekt medietid, samme spiller/scene, reel
kontakt, aktiv bold, hele bolden over linjen, retning, keeperrolle,
kausal scorer/assist-binding og deduplikering. De skelner mellem forskellige
fejl og har en faglig begrundelse. De konkrete numeriske thresholds er
derimod ikke valideret som optimale af denne audit.

**Skift rækkefølge for afklaring:** gør et afgrænset review muligt for
relevante kandidater med usikker identitet/kontakt/hold. Readeren undersøger
synlige pixels og returnerer observationer, før targetejerskab/publicering
besluttes. Et observeret holdkammeratmål kan hjælpe kædeundersøgelsen uden
at blive registreret som targetmål. Dette er et designforslag, ikke en
implementeret eller video-valideret løsning.

**Samordn genbrug af bevis:** resolver, touch-binding, roles, review og
reconciliation validerer ofte de samme tids-/identitets-/proof-felter igen.
Nogle gentagelser er korrekt validering ved modulgrænser. Saml fælles
kontrakter og behold stage-specifikke beslutninger/reasons; fjern ikke
checks alene fordi to funktioner begge læser `proof_eligible`.

**Skeln fejl fra utydelighed:** provider mangler, timeout, exceptions,
budget udtømt, review ikke valgt og pixels utilstrækkelige må have forskellige
states. `_safe_provider` kan nu omsætte en exception til default `None`.
Et vindue `ok` betyder teknisk gennemført, ikke at alle readers lykkedes.

**Ret status og confidence-sprog:** ready/scan_performed/skipped content
gate og vægtede votes må ikke fremstilles som komplet recall, verificeret
nul, målt god kvalitet eller kalibreret sikkerhed. Rapportens instruks om
aldrig at hedge skal kunne rumme eksplicit uafklaret evidens. Narrativer,
scores og GYG-labels skal tydeligt følge deres faktiske evidensgrundlag.

**Budgettér på fysisk aktion:** jersey cap er per vindue; goal-cache er
windowbundet. Overlap kan give gentagne afklaringer. Track-ID'er er lokale,
så dedup kræver scene, medietid og fysisk lineage, ikke blot samme nummer.
Gem requests, faktisk brugt budget, retries og reasons per action/run.

## Reproducerede kontroller og næste rettelsesrækkefølge

Det nye script har ni syntetiske kontroller på faktiske funktioner:
target-/teamkrav til review; tids-/scenebarrierer; identitetsafhængig graph-
recall; to-frame jersey-konsensus og ambiguous-body selection; separat
touchgruppering efter kvalitet; partial-contract physical skip; et positivt
struktureret whole-ball proof gennem begge slutgates; og afvisning af et
løst LLM-crossing-label. De er adfærdskontroller, ikke video-acceptancetests.

```sh
python backend/scripts/audit_analysis_gates.py
python backend/scripts/audit_analysis_gates.py --trace-dir /path/to/private/authoritative-traces
```

Inden produktrettelser anbefales denne konkrete rækkefølge:

1. **P0, sandt run-regnskab:** deployed SHA/config/renditionhash, atomisk
   joblease/run-ID, watchdog efter heartbeat, stage- og provider-status,
   korrekt terminalfejl i frontend. Ellers kan genkørsler og stale fields
   forveksles med, hvilke fixes der faktisk kørte.
2. **P0, rigtig dækningsvisning:** totalsikkerhed adskilt fra accepterede
   events. PARTIAL/UNKNOWN må vise dokumenterede observationer plus huller,
   ikke en sikker nulstatistik. Ingen events ændres alene for at udfylde tal.
3. **P1, identitet og bold før proof:** behold originale taps; reparer
   kamera-/overlap-/lokal trackkontinuitet og occluded active-ball recovery.
   Brug read-only trace-replays til at vise hvilken blocker der forsvinder.
4. **P1, afklaringslane og kausal kontekst:** relevansbaseret independent
   review ved tvivl, længere nødvendigt pass/receiver/scorer-forløb,
   forsvarlig delvinduebehandling og review-budget med actiondedup.
5. **P2, kontraktoprydning:** præcise reasons, fælles proof-schemas,
   dokumentation af virkelig frame-count/budget og ukalibrerede scores.
6. **Før deploy:** replay golden-video med referenceskud, mål og tre
   assistkæder, samt negative kontroller for opponent, markspillerintervention,
   spare ball, scene cuts og fejlretning. Sammenlign eventrecall, fejlagtige
   tilskrivninger, dækning, latency og modelbudget før/efter. Thresholds må
   ikke vælges ved blot at få denne ene video til at passere.

Intet her viser, at alle gates bør fjernes eller sænkes. Det dokumenterer
hvor usikre observationer stoppes, hvilke slutkrav beskytter korrekthed, og
hvilke undersøgelser der skal komme før en forsvarlig produktrettelse.
