# FIX12: rettelser fra upload til færdig analyse

Kodeændringer i draft PR #21. Ikke merged eller deployed. En eksisterende
live-rapport bliver ikke genanalyseret ved at opdatere denne PR.

## Problem og resultat

Auditten dokumenterede, at FIX10A/FIX10B/FIX11 faktisk kørte på live-rapporten,
men også jobstyringsfejl, misvisende totalsikkerhed og blokering af afklarende
review. Rettelserne nedenfor bevarer fysisk/kanonisk bevis som eventmyndighed.
Ingen referencescoring, fixture-timestamp eller videohash er hardcoded i produktet.

| Område | Rettelse | Kontrolleret grænse |
| --- | --- | --- |
| Analyseknap og autoanalyse | Atomisk Mongo-claim med run-ID; manuel, betalt og watchdog-start bruger samme wrapper | Parallelle requests starter én ejer |
| Watchdog og pod-start | Lease-udløb eller gammel heartbeat afgør takeover; frisk heartbeat vinder over gammel starttid | Et aktivt 52-minutters job genstartes/fejlmarkeres ikke alene pga. alder |
| Stale writes | Run-ID + ikke-udløbet lease indgår i alle aktuelle analysewrites | En gammel ejer kan ikke overskrive et nyere resultat |
| Heartbeat | Hele full-task, CV og modelventetid dækkes; tab af lease stopper publication; hård run-grænse på to timer | Cancellation af en thread standser ikke straks CV, men dens senere report-writes afvises |
| Mediefiler | Rapportframes/proof clips ligger i run-mapper; doubt/fast-check filenames er adskilt | En gammel ejer genbruger ikke en ny ejers evidensfilnavne |
| Status/polling | Preview-stage læser både `s` og `stage`; separat full-stage/run-ID; terminale backend-/authfejl vises straks | Aktiv heartbeat kan fortsætte over tidligere 45-minutters grænse; lokal ventetid begrænset til to timer |
| Komplethed | Semantisk kontrakt, fysisk udførelse og dokumenteret dækning adskilles | Manglende identitet, boldbevis, downstream-kæde, source-dækning eller audit-storage beviser ikke nul scoringer |
| Statistik/UI | Accepterede events beholdes som `observed_counts`; usikre totaler er `null`; UI viser Verified Goals/Assists og dækningsnote | Ingen opdigtede mål/assists; en eksplicit komplet legacy-scan kan stadig vise nul |
| Delvis/fejlet sekvensmodel | Normaliserede, gyldige planvinduer kan stadig køres fysisk; providerfejl stopper gentagen sekvensspend | Delvis respons bliver ikke erklæret komplet; ingen uplanlagte/ugyldige vinduer tillades |
| Recall ved identitetstvivl | Eksplicit UNRESOLVED target-kandidat med relevant possession kan åbne replay | Replay ændrer ikke GLOBAL_TARGET eller registrerer et event |
| Afklarende goal review | Separat begrænset lane ved usikkert ejerskab/hold i relevant target-vindue/kæde | Verificeret fysisk kontakt kræves stadig; klar opponent udelukkes; slutgates og tilskrivning bevares |
| Budget/cache | Fire afklaringer adskilt fra 16 normale reviews; scene/tid/kontekst dedupliceres på tværs af overlap | Kort kontekst erstatter ikke et længere review; afklaringsbudget kan ikke bruge normal budgetpulje |
| Jersey/role votes | Mindst to tidsadskilte, forskellige faktiske frames kræves; cache rebindes til lokale track-ID'er | Gentagen læsning af samme pixels kan ikke verificere identitet/rolle |
| Reader-kontrakt | JSON-booleans parses strengt; fejl, manglende provider og ingen evidens får forskellige diagnostics | Strengen `false` bliver ikke et positivt match |
| Trace-storage | Hvert færdigt vindue leveres løbende; uploadfejl bevarer fysisk kandidat og forsøger lokal diagnostic | Et afbrudt sent vindue sletter ikke tidligere leveret evidens; storagefejl skjules ikke som komplet audit |
| Kontakt-reasons | Skelner faktisk medietid fra boldens proof-eligibility | Predicted ball med korrekt ACTUAL_MEDIA_PTS beskrives ikke længere som en timestampfejl |
| Content gate/prompt | Betalt skip og fejl får unknown/skipped/error-status; observationstvivl tillades i prompt | Eksisterende tilladelsespolitik bevares uden syntetisk good/clear-måling |

Der er ikke fjernet målretning, whole-ball, samme-bold, scene-cut,
keeper-/save-, scorer- eller assistattributionskrav. De beskytter mod falske
resultater. Afklaringsadgang er adgang til yderligere undersøgelse, ikke bevis.

## Ny sporbarhed

`analysis_run_manifest` gemmer hashes af den faktiske canonical video, originale
`t`/`box`/`segment`/`verify`-tapfelter, backendkilde og detektor, samt aktuelle
runtimeversioner/flags/models/budgets. Deployed Git-SHA gemmes kun, hvis miljøet
faktisk leverer en gyldig SHA; ellers `null`.

`analysis_runs` gemmer stadier og relevante outputs pr. run-ID, efterhånden som
de produceres. En senere kørsel må rydde aktuelle report-felter uden at slette
den tidligere kørsels audit. `analysis_model_calls` gemmer hvert eksisterende
Gemini-kald med input-video-/prompthash, status og rå respons før parsing.
Malformed JSON og det eksisterende JSON-retry kan dermed efterprøves. Responsen
begrænses til 8 MiB pr. dokument; truncation, fuld længde og SHA er eksplicitte.
Transportfejl gemmes som type, ikke credentials/URL/error-streng.

FIX10A leverer færdige vinduer til event-loopens storagekø uden at blokere
CV-threaden på en upload i den samme executor. Manifestet appenderes atomisk i
report og run-audit, før resten af rekonstruktionen behøver at være afsluttet.
Callback-/storagefejl ugyldiggør ikke allerede rekonstrueret fysisk evidens.
Jobstatus returnerer også antallet af leverede fysiske vinduer.

Ingen ekstra modelkald udføres af auditlagringen. Nye afklaringsreviews tilføjer
højst fire review-actions pr. analyse; et review kan indeholde goal- og field-side
modelkald. Støttende vision har de eksisterende featureflags. Rå video/billeder og
private rapportpayloads er ikke inkluderet i GitHub.

## Validering

- Lokal bred regression: 995 Python-tests består med no-network modelstubs og
  testkonfiguration. Fem eksisterende deprecation warnings.
- Frontend: fem faktiske polling-kontroller og tre statistikprojektioner består;
  alle fire ændrede frontendmoduler parses som JSX/ES-moduler.
- De nye tests dækker parallel admission, healthy startup, expired takeover,
  stale writes, audit-historik, response/error-storage, ufuldstændige totaler,
  source-gaps, crop-cache, uafhængige frames og negative attribution controls.
- Gateaudit: ni kontroller består. På alle 15 SHA-verificerede live-traces matcher
  56/56 oprindelige ejerskabsbeslutninger; de to slutgates ændrer stadig ingen af
  de 56 gemte udfald. Ingen ny scoring er dermed bevist.
- Den nye afklaringsregel kan undersøge 34 af de tidligere blokerede
  strike-observationer (29 usikkert ejerskab, fem usikkert downstream-hold).
  Det er overlappende observationer, ikke 34 nye aktioner eller modelkald;
  det separate fire-actions-budget gælder stadig.
- Ny lokal CV-replay: samme canonical video-SHA
  `5b75f4523af1afe1f95341ac733c02647c8b8c2b1c3a9b08b99993e144e9b333`
  og 11 uændrede `USER_TAP` tid/boks-authorities rekonstrueret fra de verificerede
  traces. Ingen retaps, modelkald eller produktions-DB-writes. 355 identitetssamples,
  152 timeline-points; 576 scene-graph-frames, 10 sekvensvinduer, 21 refinement-
  vinduer og 11 recall-vinduer. Dette tester planlægning/tracking, ikke fuld
  modelbaseret eventacceptance.
- Den efterfølgende fysiske CV-replay afsluttede med status `ok`, 16 traces
  og 714,4 sekunders runtime, stadig uden modelproviders. Ved 23,68 og 30,83 s
  var 0/42 nærliggende frame-observationer identitetsbevis; ved 43,19 s 42/42;
  ved 49,44 s 0/42; ved 56,44 s 9/42. Overlappende observationer er ikke et
  mål for recall. Dette er konkret negativ acceptance-evidens: tracking og
  planlægning alene har endnu ikke løst de fem referenceaktioner. Jersey/
  identity-handoff og outcome-modelreview blev ikke udført i denne replay.
  Rå replay-data og tapbokse er private og ikke tilføjet repositoryet.

## Før live-deploy

Kør den fulde analyse i et isoleret miljø med den rigtige modelintegration og
uændrede originalvideo/taps. Evaluer referenceskuddet, målet og alle tre
assistkæder, inklusive #7 → #15 → #10 ved den korrigerede assistreference.
Kontrollér falske opponent-mål, markspillerinterventioner, spare ball, forkert
retning og scene cuts, samt run-identitet, varighed og requestbudget.

De beståede kodetests garanterer ikke, at alle fem referenceaktioner nu bliver
fundet. Identitet/kontakt/kæde/outcome kan stadig være uafklaret på rigtig video.
Draftstatus og manglende deploy er derfor bevidst bevaret.
