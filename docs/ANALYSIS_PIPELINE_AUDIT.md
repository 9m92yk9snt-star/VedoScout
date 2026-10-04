# Analyseforløbet: kodeaudit og verificeret live-evidens

Undersøgt 4. oktober 2026. Live-rapport:
`5df7c569-b6af-4f93-8b2a-c8c134baf2a6`, spiller #15.

Udvidet med [gate- og modelaudit](ANALYSIS_GATES_AUDIT.md): 40 gatefamilier,
ni nye adfærdskontroller og genberegning af alle 56 live-reviewbeslutninger.
`CONTACT_TIME_NOT_EXACT_PROOF` ved 23.68/30.83 s skyldes i de gemte kandidater
predicted/non-proof bold, selv med korrekt `ACTUAL_MEDIA_PTS`; reasonen
beviser ikke en tidsbasefejl. Retnings-/boldslutgates ændrer ingen af de 56
gemte udfald. Produktrettelser afventer fortsat afsluttet audit/validering.

## Konklusion og afgrænsning

FIX10A, FIX10B og FIX11 blev brugt i den konkrete live-rapport. Der findes
gemt fysisk evidens og uafhængige visuelle læsninger. Ingen af de gemte
fysiske udfald er et verificeret mål eller reddet skud, så FIX10B har nul
godkendte scoringsforslag at indsætte. Tab af identitet/kontakt og manglende
scoringskæder ligger før rapportens billed- og statistikvisning.

Derudover har analyseforløbet konkrete fejl i jobstyring, status og
statistikernes fortolkning af dækning. De kan give flere samtidige analyser,
misvisende nulstatistikker og skjulte fejl. En færdig jobstatus dokumenterer
ikke, at videoens aktioner er fundet korrekt.

Auditten følger upload, preview, oplåsning, fuld analyse, alle tilknyttede
FIX00–FIX11-trin, fejl/fallback, kanonisk registrering, statistik, evidens,
gendannelse, watchdog og frontendens polling. Den er ikke en garanti for
alle øvrige dele af hjemmesiden eller for fejlfri analyse af alle videoer.

Kodegrundlag: `main` ved `f051fa11c6d73eccb0e15a643c57b6d7c5f9fccd` og
draft PR #21 ved `dd6dcbd35aa2b7f056bb39a826f97b57498ec6c3`. Serverens
orkestrering, fysisk rekonstruktion, FIX10A-runtime, statistiklaget og de
undersøgte upload/rapportkomponenter er identiske med dette `main`.
FIX12-ændringer i PR #21 er endnu ikke merged. De kan ikke antages at være
aktive i live-rapporten. Den præcise deployed Git-SHA er ikke verificeret;
rapportens versionsfelter er modulversioner, ikke en deployed commit.

## Fra analyseknap til rapport

| Trin | Kaldesti | Hvad der faktisk afsluttes |
| --- | --- | --- |
| Upload | `UploadPage.jsx` → POST `/reports/upload` → `_analyze_preview_task_with_timeout` | Modtagelse og et background-job, ikke fuld analyse |
| Preview | `analyze_preview_task` | Video, originale taps/crops (FIX00A), identitetsprofil, content gate og preview |
| Preview klar | `analysis_status=ready` | Upload-overlayet stopper; fuld rapport kan stadig mangle |
| Fuld rapport | Betalt/admin-upload starter `_full_report_with_heartbeat`; senere oplåsning/rapportside kalder POST `/generate-full` | Gratis preview alene starter ikke den fulde FIX09/FIX10/FIX11-analyse |
| Tracking | `_tracking_core` → FIX04 `track_player` → FIX09A `build_identity_timeline` | Tapbaseret og sceneopdelt identitet |
| Fælles analyse | `prepare_analysis` → scene graph og sequence plan → modelrespons → `finalise_analysis` | FIX09B.0–B.3 identitet, sekvens og kanoniske beslutninger |
| Fysisk analyse | Await `fix10a_runtime.run` → `reconstruct_physical_match` | FIX10A dense replay, boldbane, kontakt, okklusionsgenopretning, touch graph, trøjenummer, udfald |
| FIX11 | `build_physical_recall_windows` + `union_dense_windows` inde i fysisk rekonstruktion | Semantikuafhængige ekstra vinduer; ingen separat FIX11-knap/enable-flag |
| Registrering | `fix10b_runtime.build_candidate` → `reconcile_canonical_events` | Kun dokumenterede fysiske forslag føjes til den kanoniske sandhed |
| Rapport | FIX09C `apply_result_to_report` → FIX01 → FIX07 → FIX02 | Kanoniske aktioner erstatter modellens timeline; statistik og proof binds deterministisk |
| Billeder/klip | `_persist_video_frames`, FIX03 medietid, FIX05 telestration/proof clips | Genererer materiale til allerede accepterede aktioner; opdager ikke manglende mål |
| Bevægelse | `_movement_pace_core`, FIX06 | Parallelle bevægelses-/pace-resultater; ingen scoringsmyndighed |
| Finalisering | FIX00B identitetsgate → `_finalize_full_report` | `full_report_status=ready`, efter den krævede finalisering |

Den gamle FIX08-discovery og den generelle ekstra modelverifikation springes
bevidst over, når FIX09B kanonisk analyse er accepteret. Det er ikke i sig
selv en manglende fix: den nye kanoniske myndighed erstatter den gamle.
En korrektiv genbeskrivelse bevarer ligeledes den gemte kanoniske timeline.
Den kan derfor ikke alene genskabe mål, der aldrig blev accepteret fysisk.

## Hvad live-evidensen beviser

MongoView blev læst i Production DB `vedoscout-main-elite_scout_db`.
Alle 15 gzip-filers størrelser og SHA-256 af deres ukomprimerede indhold
matcher rapportens gemte manifest. Den oprindelige ZIP med 29 tracevarianter
matcher kun én af disse 15 filer og må ikke bruges som eneste live-sandhed.

Den private verificerede pakke `5df7c569-live-authoritative-traces.zip` har
SHA-256 `2f6b7e371ac9eb9a8b30b523b330f4e2708aa988ca756af4c1b8c8625ea2a0f7`.
Den indeholder de præcise traces og synlige kanoniske/scoringsfelter; den er
ikke en komplet Mongo-eksport. Rå brugerfiler, medielinks og credentials
er ikke lagt i GitHub.

| Observation | Betydning |
| --- | --- |
| FIX10A `mode=production`, `status=ok`, 15 traces, nul fejlede vinduer | Fysisk rekonstruktion blev udført |
| 9 recall-vinduer planlagt, udført og `ok` | FIX11-recall blev udført |
| 443 accepterede kontakter, 14 genoprettede kontakter, 512 touches | Kontakt- og okklusionsmoduler bidrog med fysisk evidens; summer på tværs af overlappende vinduer |
| 56 strikes/outcomes, heraf 8 target-strikes | Fysisk kontakt er ikke det samme som bevis for mål/assist |
| 292 gemte trøjenummervotes, 119 `readable=true`, 7 verificerede track-konsensusser | Nummerlæseren kørte og gav resultater; kun én af de verificerede konsensusser er nummer 15 |
| 15 målreviews tilladt, 41 fravalgt af kausalitetsgaten | Målreaderens adgang afhænger af target-/hold-/kontaktbevis |
| 49 `PLAYER_INTERVENTION`, 2 `UNRESOLVED_TERMINAL_VISIBILITY`, 5 `UNRESOLVED` | Ingen gemte verificerede mål eller saves blandt disse udfald |
| 4 geometrireviews `VERIFIED`, men ingen verificeret scoring | At finde mållinjen beviser ikke boldens passage eller målscorer |
| FIX10B myndighed aktiv, `no_change`, nul forslag/anvendelser | FIX10B kørte; den havde ikke tilstrækkelige scorerbeviser |
| 8 accepterede og 8 unresolved kanoniske observationer | De to SHOT-kandidater ligger ved 28.132 og 36.132 s; de er ikke de forventede skud/mål |

`fix10a_canonical_authority=false` er korrekt arkitektur: FIX10A producerer
evidens, FIX10B ejer registreringen. Det er ikke et disable-flag.
`FIX10A_SUPPORT_VISION_ENABLED` har default `1`; API-key/provider-tilgængelighed
kan stadig give manglende readers i andre runs. Funktionen hedder historisk
`build_shadow_providers`, men kaldes på produktionsvejen. Navnet er ikke en
shadow-begrænsning. Gemte læsninger viser, at readers var aktive i dette run.

## Hvor de fem aktioner bliver tabt

Referenceaktionerne er brugerens annotationskrav; de er ikke automatisk
modelbevis. De må bruges til evaluering, ikke hardcodes ind i produktion.

| Reference | Faktisk live-blocker | Nødvendig rettelse |
| --- | --- | --- |
| 23.68 s, reddet skud | Alle 42 frame-observationer inden for ±350 ms har `TARGET_GAP`; tre kontaktkandidater afvises som `CONTACT_TIME_NOT_EXACT_PROOF` | Identitet gennem skudsekvensen og fysisk kontakt før keeper-/save-bevis |
| 30.83 s, mål | Alle 42 nærliggende observationer har `TARGET_GAP`; seks unresolved kontakter; intet target-scoring-release ved målet | Identitet, kontakt og efterfølgende målgennemgang i samme boldkæde |
| 43.19 s, assist | Identitet bevist i de nærliggende frames og target-strikes findes; udfald/receiver-til-mål-kæde ikke bevist | Følg afleveringen til modtagerens scoring og behold nødvendig sen kontekst |
| 49.44 s, assist | Kun 2 af 42 nærliggende observationer er identitetsbevis; modtagelse ved 49.465 s findes, release 49.515 s unresolved; ingen strike inden for ±1.8 s | Følg #7 → #15 modtagelse/vending/aflevering → #10 mål uden identitetsswitch |
| 56.44 s, assist | Target-release ved 56.148 s findes; efterfølgende releases 56.398, 56.731 og 58.164 s blokkeres af `DOWNSTREAM_RELEASE_TARGET_TEAM_UNVERIFIED` | Sammenhængende hold-/modtager-/boldkæde og uafhængigt bevis for holdkammeratens mål |

De 42 frame-observationer pr. reference er observationer fra gemte vinduer;
de er ikke en ny måling af full-video recall. Semantiske og dense track-ID'er
har forskellige lokale navnerum og skal ikke sammenlignes som globale IDs.

## Reproducerede kodefejl og øvrige risici

### A. Watchdog kan genstarte et aktivt job (høj prioritet)

`server.py::_sweep_stuck_full_reports` vælger efter
`full_report_started_at`, ikke efter heartbeat. Efter 20 minutter kan den
starte et nyt job, selv med `last_progress_at=nu`. Ved to tidligere retries
kan et stadig aktivt job markeres failed. De gamle tasks bliver ikke
annulleret, og writes er ikke bundet til et run-ID/lease.

Reproduceret med den faktiske funktion og syntetiske DB/task-boundaries:
30 minutter gammelt job, frisk heartbeat → ét nyt job. Samme situation
med retries=2 → failed. Din live-rekonstruktion tog 3117.206 s (~52 min),
og dokumentet har `full_report_retries=2`. Det stemmer med risikoen,
men vi har ikke logs/run-ID'er til at bevise samtidige jobs i netop dette run.
Et worker-restart er også en mulig årsag til retries.

### B. Jobstart er ikke atomisk; entry points har forskellig heartbeat

POST `/generate-full` læser status og skriver `generating` i separate kald.
To samtidige requests kan begge se den gamle status og begge starte et job.
Reproduceret: to faktiske endpoint-kald med samtidige syntetiske reads giver
to queued jobs. Frontendens ref-guard beskytter ikke mod andre requests,
auto-start eller watchdog. Endpointet starter desuden
`generate_full_report_task` direkte, mens auto-start og watchdog bruger
`_full_report_with_heartbeat`.

### C. Ufuldstændig evidens bliver stadig vist som en nulstatistik

`verified_stats.py::build_verified_stats` bruger kun `scan.performed` til
`goals_assists_available` og `verified_stat_line`. Det ignorerer den nye
`physical_recall_verification_complete=false`/PARTIAL-status fra PR #21.
Reproduceret: ufuldstændig target-evidens → `stats_available=true` og
`0 goals · 0 assists · 0 shots`. Den tidligere dækningsrettelse er derfor
kun en diagnostisk rettelse; statistikvisningen skal også ændres.

Bevar accepterede aktioner/tal som dokumenterede observationer, men angiv
tydeligt, at totalen kan være ufuldstændig. Huller er ikke bevis for nul.
Gamle verifikationskontrakter uden nye dækningsfelter kræver en eksplicit
kompatibilitetsregel; hele det historiske statistiklag må ikke blindt lukkes.

### D. Frontend skjuler en eksplicit fejl som ventetid

`ReportPage.jsx::pollFullReportReady` kaster en fejl ved backendstatus
`failed` inde i sin `try`, men `catch` kaster kun videre ved HTTP 404.
Dermed sluges den konkrete analysedriftsfejl og behandles som et netværksblip.
Reproduceret med den faktiske JS-funktion og syntetisk API/ur:
`synthetic backend failure` bliver til beskeden om, at rapporten tager
længere tid end normalt, efter pollingens 20-minuttersgrænse.

### E. Pipeline-trin mangler i status

`_trace` gemmer `{s, at}`, mens `/status` læser `.get('stage')`.
Reproduceret: gemt `s=transcode_start` → `pipeline_stage=null`.
Der findes heller ikke tilstrækkelige stage-markers for hele den fysiske
analyse. Status skal følge både preview og fuld analyse, hver med run-ID.

### F. Readerfejl kan blive til almindelig unresolved evidens

`physical_match_reconstruction::_safe_provider` og `_safe_role_provider`
returnerer default ved exceptions. Flere adapters gør tilsvarende.
Reproduceret: reader-exception → `None`, uden fejldetaljer fra wrapperen.
Vinduet kan stadig blive `ok`. Manglende/fejlet reader, utydelige pixels og
kausalt fravalgt review bør have adskilte status/reason-felter. Dette er ikke
bevis for reader-fejl i din rapport; gemte læsninger viser reelle resultater.

### G. Trace-lagringsfejl kan kassere en færdig reconciliation-candidate

`fix10a_runtime.run` bygger kandidaten før trace-upload, men trace-upload
ligger i samme store `try`. En enkelt exception i `_persist_trace` sender
funktionen til error-return uden `_fix10b_candidate`; serveren beholder
FIX09B-resultatet. Reproduceret med faktisk runtime og syntetisk lagring:
fysisk rekonstruktion færdig, lagring fejler → candidate ikke returneret.
Det skal være eksplicit, om manglende audit-lagring blokerer publicering,
og hvorfor. Din rapport har alle 15 gemte traces, så dette er en anden
potentiel fejlvej, ikke den dokumenterede årsag til dens nulresultat.

### H. Fallback og recovery kan se ud som en fuld ny analyse

Ved manglende anchors, disabled/fejlet FIX09A, mislykket preparation eller
ufuldstændig sequence-kontrakt går serveren til legacy FIX08; FIX10A/FIX11
starter da ikke. `_fallback_unset` rydder kanoniske felter, men ikke alle
gamle `fix10a_*`/`fix10b_*` diagnostikfelter. Ved fremtidige genkørsler kan
de uden run-ID se aktuelle ud. Dette er en statisk kodefinding.

`generate_full_report_task` genbruger en eksisterende ready-rapport eller
genstarter kun finalisering, hvis body allerede findes. Admin-knappen
`regenerate-evidence` starter kun `_persist_video_frames`. Ingen af disse
garanterer en frisk fuld FIX09/FIX10/FIX11-analyse. De bør have klart
adskilte navne og returnere, hvilke trin der faktisk blev kørt.

`is_production_ready` accepterer bevidst også en komplet respons med
`canonical.status=empty/unresolved`. Reproduceret: nul accepterede events
kan være production-ready. Det kan være korrekt for en video uden aktioner,
men kriteriet dokumenterer ikke præcision eller recall på golden-videoen.

## Kontroller og næste konkrete rettelser

Lokale read-only reproduktioner:

```sh
python backend/scripts/audit_analysis_control_flow.py
node frontend/scripts/audit-analysis-poll.cjs
```

Pythonværktøjet kører udvalgte faktiske funktioner via AST, uden at importere
serverens startup. Fake DB/task/model/storage-boundaries gør det muligt at
undersøge kontrolflow uden netværk. JS-værktøjet kører den faktiske
pollingfunktion med syntetisk ur og API. De dokumenterer nuværende adfærd;
de er ikke end-to-end acceptancetests. Når fejlene rettes, skal
reproduktionernes forventninger opdateres til rigtige regressionstests.

Otte Python-cases og én JS-case reproduceret; critical Python lint og
`git diff --check` består. GitHub Production verification på commit `dd6dcbd`
er success. Workflowet bruger no-network modelstubs og verificerer hverken
deployed commit, alle live-readers eller de fem aktioner i din video.

Prioriteret implementering:

1. Én atomisk jobstart og én heartbeat/lease-kontrakt for alle entry points.
   Watchdog må ikke genstarte en gyldig ejer; run-ID/fencing skal afvise writes
   fra gamle tasks. Adskil liveness fra en eventuel reel max-runtime-politik.
2. Korrekt videreføring af backend-fejl og evidensdækning til statistik/UI.
   Færdig kørsel, tilgængeligt bevis og valideret recall er tre forskellige ting.
3. En varig audit pr. run: commit, video/tap-hash, konfiguration uden secrets,
   stage start/slut/skip/error, reader-status og manifest/canonical-hash.
   Bevar run-sammenhængen ved fallback, storagefejl og recovery.
4. Ret identitet og kontakt ved 23.68/30.83/49.44 s; følg hold-/modtager-/mål-
   kæder ved alle tre assists. Ingen ændrede originale taps eller sænkede
   proof-thresholds. Supplér uafhængige visuelle beviser, hvor de mangler.
5. Kontrolleret frisk golden-run på samme video og alle 11 originale taps:
   1 target-mål, 1 reddet target-skud og 3 target-assists, korrekt ejer og
   tidslinje. Holdkammeratens mål må ikke registreres som #15's mål.
   Deploy først efter godkendt fuld videovalidering.

Auditten har ikke lavet produktionswrites, merge/deploy eller betalte
modelkald. Den konkrete fejl i aktionernes detektion er fortsat uløst.
