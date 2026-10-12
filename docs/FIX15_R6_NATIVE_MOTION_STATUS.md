# R6: afgrænset trøjeudsnit og boldbevægelse i forhold til kameraet

Checkpoint 2026-10-12, oven på `a81f57338021e5126f7f888ef21e8f6b46674b7e`, på `codex-r6-native-jersey-20261011`.

**De fem referenceforløb er lokaliseret i originalvideoen. Automatisk, kanonisk verificering er fortsat 0/5. Ingen merge eller deployment.** Samme video, alle 12 eksisterende markeringer og uændret tidsforskydning bruges. Ingen nye markeringer, Emergent-kald eller betalte modelkald.

## Rettelser

Den oprindelige kropsafgrænsning i `cv_shadow.py` er allerede rettet i `e7537e4`. Denne revision retter to efterfølgende fejlkilder:

1. Trøjeudsnittets centrale 76 procent kunne afskære det første ciffer på en drejet ryg. Samtidig fik den eksisterende trøjereader et større udsnit med padding uden for kroppen. `jersey_pixels.py` leverer nu ét fælles rektangel: hele kropsbredden, fra 18 til 64 procent af den målte kropshøjde, rundet indad og klippet til synlige pixels. Både kvalitetsmålingen og readeren bruger det rektangel. Nabopixels kan ikke ændre readerens input. Rolereaderens kontekstudsnit ændres ikke.
2. A4 kunne godkende en berøring af en stationær bold, når den nærmeste spiller skiftede, eller meget små detektionsudsving ændrede retningen. Kameraets panorering kunne også ligne boldacceleration. `ball_motion_evidence.py` bruger nu de faktiske baggrundstransformationer mellem afkodede billeder, før bevægelsessignalet beregnes. En bevægelse skal overstige både to native pixels og én målt boldradius for at levere uafhængigt bevægelsesbevis. Spillerens afstand eller en tap kan ikke erstatte det signal.

Den tætte tracker gemmer transformationens faktiske fra-/til-PTS, pixelmål og den opløsning, hvor kamerabevægelsen blev estimeret. En etiket som `AFFINE_VERIFIED` er ikke nok. Kæden afviser sceneskift, forkert tidsautoritet, fallback, manglende led, forskellige billeddimensioner, ugyldige matricer og blandet native/legacy-evidens. Afrundingen fra 960 × 1707 native pixels til 480 × 854 estimationspixels håndteres eksplicit; den oprindelige kameramodels geometrigrænser ændres ikke.

Step-3's indgående/udgående bevægelsessammenligning og dens tap-/support-stier bruger samme måling. En spiller, der fjerner sig fra bolden, kan derfor ikke alene bevise et release. Eksisterende kontakt-, identitets-, tids-, tvetydigheds- og eventgrænser er bevaret. Det nye bevægelsesminimum er en yderligere, konservativ bevisgrænse. Legacy-traces uden det nye kamera-kontraktfelt beholder deres historiske fortolkning.

Eksporten i `event_trace.py` bevarer desuden dimensioner, kameratransformationer og det særskilte A7-supportspor. Tidligere mistede eksporten disse felter, så en genkørsel kunne få en anden koordinatfortolkning. Supportproposals forbliver support-only; rå billedarrays eksporteres ikke.

## Kontrol

**879 lokale tests i 55 filer består**, med én eksisterende AnyIO-deprecation-advarsel. Alle tidligere 820 tests er med, plus seks eksisterende eksporttests og 53 nye tests. Assertions i de eksisterende tests er ikke svækket. Offline-harnesset registrerer nul faktiske SDK-, netværks- og videoafkodningsforsøg.

Syv integrationstests er også kørt på uændrede produktionsmoduler fra `a81f573`: **alle syv fejler**. De viser falsk kontakt ved forbipassage, detektionsjitter og kameraacceleration på tre billedformater, forskel mellem kvalitets-/readerpixels samt padding uden for kroppen. Kun de nye testfiler og deres ubrugte hjælpere blev kopieret til baseline-checkoutet; fejlene skyldes ikke nye funktionssignaturer.

Samme 1.922 originalbilleder er genafkodet med faktiske PTS og præcise hits i den pixelbundne native detektorcache. Der er nul nye detektor-forwards i denne kontrol, ingen tilførte gamle kontakter, trøjevotes eller outcomes og ingen modelkald. Referenceetiketterne bruges til valg af eksisterende benchmarkvinduer og evaluering efter rekonstruktionen. Dette er fortsat en kontrol af fem afgrænsede vinduer, ikke en fuld-video recall-certificering.

| Referenceforløb | Reference i originalvideo | Kontakter ved a81f573 / nu | Kanonisk status |
| --- | ---: | ---: | --- |
| Skud/redning | 23.680 s | 25 / 20 | NOT_VERIFIED |
| Mål | 30.830 s | 47 / 18 | NOT_VERIFIED |
| Assist 1 | 43.190 s | 80 / 14 | NOT_VERIFIED |
| Assist 2 | 49.440 s | 34 / 17 | NOT_VERIFIED |
| Assist 3 | 56.440 s | 44 / 26 | NOT_VERIFIED |

Accepterede kontakter falder samlet fra 230 til 95. Det er ikke dokumentation for, at alle bortfaldne kontakter var falske, eller at alle resterende er korrekte. Små reelle bevægelser kan nu blive afvist, hvis de ikke kan skelnes fra detektionsopløsningen. Bevægelse beviser heller ikke i sig selv aktiv boldidentitet. Alle fem referencer fejler fortsat med `QUALIFIED_CANONICAL_EVENT_MISSING`.

## Gratis, lokale læserforsøg

En separat OCR-kontrol har læst 726 isolerede kropsudsnit fra originalvideoen uden at få forventede numre eller aktioner. Den finder flere gentagne numre, men også delvise og modstridende læsninger med høj score. En aggregeret OCR-status er derfor ikke behandlet som produktbevis, og ingen af disse votes er tilført identitetsautoriteten eller kanoniske events.

Fire nye Qwen3-VL 4B-læsninger med det fælles, afgrænsede udsnit giver én læsning af `15` og tre `readable=false`. De to prøver fra skudscenen giver således ikke to uafhængige, positive nummerlæsninger. Disse svar anvendes heller ikke som votes. Modellen tilføres ingen forventede numre, spilleridentitet eller outcomes.

En lokal personmodel blev vurderet på tøj og sko med hovedområdet maskeret. Den skelner nogle spillere, men dens kontrolmarginer adskiller ikke konsekvent samme-holdsspillere. En lokal posemodel finder flere faktiske ankler, men overser også kroppen i den afgørende målduel. En særskilt fodboldmodel giver utilstrækkelige eller fejlagtige proposals på stikprøverne. Ingen af disse forsøg giver kontakt-, rolle- eller target-autoritet. Ingen ny modelvægt eller modeldependency tilføjes til produktet.

Den automatiske godkendelseskontrol afviste fortsættelse af en OCR-proces på grund af et Microsoft-telemetriforsøg. Den efterfølgende, fuldførte kørsel har ONNX Runtime-telemetri deaktiveret og en procesfilterkontrol, der afviser socket-, connect- og send-syscalls også fra native biblioteker. En direkte libc-kontrol består, før inference starter. Tidligere Python-socket-tællere var ikke en kontrol af native telemetri. Den nye native videokontrol er også kørt med dette procesfilter.

## Det, der fortsat spærrer de fem aktioner

- Skudscenen efter sceneskiftet mangler sikker GLOBAL_TARGET-identitet; målduellen mister også target-koblingen.
- A3 kan fortsat fastholde en reservebold og udelukke nye aktive boldhypoteser. Bevægelsesrettelsen løser ikke denne objektidentitet eller støvler, der er fejlklassificeret som bold.
- De tre assistreferencer mangler en verificeret kæde fra den valgte spiller til afslutteren, inklusive afklaring af andre berøringer.
- Målmandsrolle, indgreb og målplanspassage har endnu ingen kvalificeret, gratis lokal provider i rekonstruktionen. De fejler lukket.

De fem forløb kan gennemgås i `ScoutMePlay-fem-referenceforloeb.mp4`. Den video er til manuel gennemgang og ændrer hverken markeringer eller eventstatus. Teknisk test-PASS og grøn CI erstatter ikke kravet om fem verificerede aktioner.
