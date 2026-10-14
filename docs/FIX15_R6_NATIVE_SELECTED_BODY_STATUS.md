# R6: den markerede krop findes uden at arve den blås spor

Fortsættelse af `0ad165325ae5ab05ce4b8651be7ba292ffdc2f02` på
`codex-r6-native-jersey-20261011`. Samme originalvideo og alle 12 eksisterende
USER-markeringer. Ingen Emergent-eksekvering, nye betalte modelkald, merge eller
deployment. **PASS for en afgrænset kropsbinding er ikke fem-aktions-PASS.**

## Fundet ved 50,4 sekunder

Den oprindelige markering lander nærmest det faktiske billede ved 50.398 s.
Den brede detektion omfatter den blå spiller foran den hvide, men dækker ikke
nok af den originale synlighedsmaske. `0ad1653` afviser derfor bindingen med
`TAP_POINT_BODY_MASK_CONFLICT` uden at finde en erstatningskrop.

To afgrænsede detektioner finder nu én krop, som indeholder det uændrede
USER-punkt og dækker maskens foreground. Det er den eksisterende, gratis lokale
YOLOv8n ONNX-model med uændret persongrænse 0,25. Det er ikke en nummerlæsning,
holdklassifikation eller mål-/assistafgørelse.

| Samme faktiske billede | Personscore, mindre/større udsnit | Geometrisk IoU | Binding |
| --- | --- | --- | --- |
| 1080 × 1920 originalpixels | 0,3454 / 0,3511 | 0,8822 | VERIFIED ved USER-markeringen |
| 960 × 1707 produktionspixels | 0,3923 / 0,4604 | 0,8294 | VERIFIED ved USER-markeringen |

De to udsnit er **én tidsobservation**, ikke to uafhængige billeder. Resultatet
bevarer det faktisk målte større udsnits boks, ikke en gennemsnitlig, udvidet
eller forudsagt krop.

## Rettelser og begrænsninger

`dense_track_refinement.py` undersøger kun udsnit ved en original,
proof-eligible USER-markering, når ingen eksisterende detektion passer til
punkt, udelukkelser og den gemte maske. En allerede fundet krop eller ægte
tvetydighed erstattes ikke. Begge udsnit skal finde præcis én kompatibel person
og have mindst 0,70 IoU. Maskens eksisterende 90 %-krav, udelukkelser og
personscore bevares. Boldproposals fra udsnittene kasseres.

Den første native A/B-prøve viste, at den hvide krop kunne arve det gamle blå
spor `p007`, når en gammel association faldt igennem til en anden detektion.
En ny udsnitskrop starter derfor med et nyt ID. Kun en tidligere målt
udsnitskrop fra samme USER-markering kan gå ind i de almindelige, uændrede
associations-/tvetydighedsgates. Gamle spor omdøbes ikke til den hvide spiller.

En mellemprøve viste også, at et hul på 300 ms kunne føre det nye spor til en
anden hvid spiller. For et nyligt isoleret fragment slutter kontinuiteten derfor
ved en manglende kildeframe-observation. Kameraforudsigelse alene kan ikke
genfinde en holdkammerat. Andre kroppes eksisterende trackinggrænser ændres ikke.

`player_identity_timeline.build_identity_timeline` tabte stadig masken ved
opbygningen af sine tap-rækker, selv om `assemble_timeline` allerede kunne
bruge den. Gyldige masker kopieres nu også gennem denne videoindlæsning.
Sampling-grid, punkter, bokse, rå tider og selve maskerne ændres ikke.

## Kildekontrol

En ny A/B-kørsel starter med tomme spor og ingen gamle identiteter, kontakter,
trøjevotes eller outcomes. 110 faktiske billeder omkring duellen genafkodes.
Alle 110 matcher originalens pixelcache og har faktiske PTS uden fallback eller
sceneskift. Fem ekstra person-forwards inkluderer afviste udsnit ved nabobilleder.

Ved 50.398 s bindes markeringen til et nyt hvidt spor `p012` med 100 %
foreground-dækning. Det beviser ikke tidligere/senere identitet: sporet har kun
denne ene accepterede kildeframe. Hold og nummer forbliver uafklaret. Begge
mellemprøver med fejlagtig sporoverførsel bevares som diagnostik, ikke evidens.

Alle 12 originale markeringer genafkodes og A/B-kontrolleres både ved 1080 og
960 pixels bredde. **Kun 50,4 s ændrer binding; de andre 11 resultater er identiske
med baseline i begge opløsninger.** Uafklarede markeringer forbliver uafklarede.
Originalens video- og markeringshash er uændrede.

## Tests

30 nye native-kropscases og én ekstra maskeret videoindlæsningscase indgår.
To integrationsassertions fejler på den præcise `0ad1653`-kode: manglende native
kropsfund og tab af masken ved videoindlæsning. De består efter rettelsen uden
ændrede forventninger til eksisterende tests.

**119 fokuserede tests består. Seriel udvidet offline-kontrol: 1.517 PASS,
19 SDK-afhængige SKIP**, med den eksisterende Starlette/AnyIO-deprecation-advarsel.
SDK-, netværks- og native video-decode-forsøg er nul i testharnesset. Rigtige
billedforsøg kører særskilt med OS-socketblokering og den eksisterende lokale model.

En tidligere fuld kørsel samtidigt med billedanalysen havde én procesoprydnings-
teardownfejl; loggen er bevaret. Den afsluttende serielle kørsel består. Ingen
lifecycle-assertion, test eller gate er fjernet eller svækket. De nye kropscases
tilføjes den eksisterende `player_selection`-CI-kontrol. CI kontrolleres på den
gemte revisions præcise SHA og er ikke video-PASS.

## Næste bevisled

Assistforløbet kræver stadig faktisk spillerkontinuitet gennem duellen og en
verificeret boldkæde fra aflevereren til afslutteren og mål. Det blå spor eller en
efterfølgende hvid spiller må ikke udfylde det manglende led. Målforløbets tidligere
occlusion/same-ball-gap er heller ikke løst. Ingen ny fem-aktionsgodkendelse udstedes.

Originalpixels, private scripts, mellemprøver, endelig A/B-kørsel, 12-markerings-
kontrol og testlogs bevares i `ScoutMePlay-native-spillerkontrol.zip`. Git-koden
opbevares alene på projektets eksisterende GitHub-branche.
