# R6: modstridende trøjefarve må ikke arve et sikkert lokalt spiller-id

Denne separate, ikke-deployede kandidat bygger på `2090624fb3e33a443a74e46abdb10571087cc8d9` (`codex-r6-ground-band-20261011`). Main, PR28 og de tidligere backup-grene ændres ikke. Den hidtidige grens fem GitHub CI-jobs bestod; det er ikke bevis for, at de fem videoaktioner er fundet.

## Dokumenteret fejl og afgrænset ændring

Originale spillerudsnit viser, at et lokalt track starter på en spiller i hvid trøje med synligt 15 og senere følger en blå modstander under en duel. Den geometriske association havde ingen kontrol af målt trøjefarve. Det kan også forurene de udsnit, der senere sendes til en trøjelæser.

Den nye kontrol bruges først efter de eksisterende geometriske matchkrav. Den kræver mindst tre aktuelle, native torsofarvemålinger, mindst 120 ms mellem målingerne, højst 1.200 ms gammel historik og højst 5 Lab-kromaenheders maksimal spredning. Overlappende detektionsbokse med IoU på mindst 0,25 kan ikke etablere denne historik. Kun faktiske medietidsstempler uden fallback og en accepteret kameratilstand er egnede.

En kromaafstand på mindst 20 afviser den pågældende kobling; afstand 10 til under 20 gør associationen til en uafklaret hypotese. Usikre målinger overskriver ikke det senest accepterede spillerlegeme, bevægelse eller farvehistorik. Andre geometrisk mulige spiller-id'er bevares i hypotesen. Et klip nulstiller historikken. Farve tilfører ingen positiv identitets-score og kan aldrig alene skabe `GLOBAL_TARGET`.

Geometriske grænser, kamera-/gapkrav, boldgrænser og de uafhængige identitets-, trøje-, same-ball-, rolle-, mål- og kanoniske beviskrav er ikke lempet. Ens trøjefarve beviser ikke, at to legemer er samme spiller. Der indbygges ingen forventet trøjenummer- eller referenceaktionstider i den nye kontrol.

## Native før/efter på originalvideoen

361 fortløbende billeder fra én scene er undersøgt ved faktiske PTS. En frisk native detektorkørsel på originalvideoen gav 668 lokale ONNX-forwards; observationerne deles derefter af begge trackere. Den endelige A/B gentager videoafkodning og kameramåling, men genbruger præcis dette aktuelle native observationssæt. Det er ikke en ny fuld modelkørsel pr. variant og ikke genbrug af gamle gemte kontakter, afgørelser eller trøjevotes.

| Måling | Før | Efter |
| --- | ---: | ---: |
| Billeder pr. lane | 361 | 361 |
| Lokale tracks | 48 | 54 |
| Spillerobservationer med `VERIFIED_LOCAL` | 1.783 | 1.586 |
| Spillerobservationer med `HYPOTHESES` | 60 | 251 |
| Farvemodsatrettede koblingsforslag afvist | 0 | 34 |
| Koblingsforslag markeret med farve-usikkerhed | 0 | 199 |
| Fysiske kontakter, ikke nødvendigvis målspilleren | 22 | 19 |
| Kandidatforløb med verificeret kontakt-til-startreference | 3 | 3 |
| Verificerede kontakter med målspilleren | 0 | 0 |
| Billeder med kanonisk målspillerstatus `UNRESOLVED` | 361 | 361 |

Afviste/usikre koblingsforslag tæller associationer, ikke 34/199 manuelt beviste spillerfejl. Det berørte gamle id har 119 tilknyttede observationer før og 94 efter. Den tydelige blå fortsættelse bliver opdelt eller uafklaret, men et overgangsbillede med blandet hvid/blå krop bevarer stadig det gamle id. Derfor er dette en **delvis beskyttelse mod id-skift, ikke en fuld identitetsrettelse**. Mere fragmentering og færre kontakter kan også koste recall; flere eller færre kandidataktioner er ikke et succeskriterium.

Begge lanes anvender samme produktionskontroller for fysiske kontakter og releasebinding. Svag A7-support er ens i begge; ekstra pixelbaseret occlusion recovery er slået fra ens. Der er ingen konfigurerede trøje-, keeperrolle- eller mållæsere, ingen kanonisk accept og ingen ny komplet fem-aktionsvurdering. Ingen fysisk spillerintervention er her ophøjet til en verificeret keeperredning eller et mål.

## Lokal OCR blev ikke identitetsbevis

40 originale udsnit blev afprøvet med lokal Tesseract: 24 fra den eksisterende trøjeprioritering og 16 diagnostiske, tidsfordelte alternativer. 160 OCR-forsøg omfattede flere visninger af samme billede; de tæller ikke som uafhængige votes. Aflæsningerne gav ikke en pålidelig, uafhængig nummerkonsensus. En forkert encifret aflæsning havde endda en OCR-score over 94. Ingen aflæsninger blev lagt i produktionskonsensus eller brugt til spilleridentitet.

Den eksisterende trøjehåndtering kræver også et direkte identitetsanker i samme scene. Markeringer før det reelle klip kan ikke flyttes gennem klippet som bevis, selv hvis et nummer efter klippet kan læses. En uafhængig, dokumenteret genidentifikation efter klip er stadig uløst; denne kandidat ændrer ikke den regel og beder ikke om nye markeringer.

## Tests og status

**581 tests i 44 filer består**, heraf 28 nye syntetiske regressionstests. De 546 tidligere udvalgte tests er med, plus syv eksisterende trøjekonsensustests. Der er én kendt lokal Starlette/httpx-deprecation-advarsel. Ingen eksisterende assertions er svækket. Den fulde tidligere pakke på 1.245 tests er ikke kørt igen lokalt.

Det lokale testharness blokerer faktisk SDK, netværk og videoafkodning; registrerede forsøg er nul. Den separate native kontrol tillader lokal afkodning/ONNX, men blokerer SDK/netværk; registrerede forsøg er nul. SDK-runner og FIX10B er byte-uændrede. Ingen Emergent, nye betalte modelkald, nye markeringer, merge eller deployment.

Senest afsluttede strenge videoevaluering er fortsat **R5: 0 af 5 verificeret**. Denne kandidat er ikke en PASS på de fem referenceaktioner. Rå video, billeder, cachedata, markeringernes koordinater og credentials indgår ikke i GitHub-backuppen. Manifestet `backups/CODEX_R6_LOCAL_KIT_MANIFEST.json` angiver kodehashes, præcis testliste og begrænsninger.
