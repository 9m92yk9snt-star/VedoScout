# R6: vælg trøjeudsnit efter målte pixels og spredning i tid

Denne separate kandidat bygger på `5089b74f03b7fa6ff46912bb087339ac573bee67` (`codex-r6-local-kit-20261011`). Alle fem CI-jobs på den forrige gren er bestået. Kandidaten er ikke merged eller deployet; main, PR28 og tidligere grene bevares.

## Problem og ændring

Den hidtidige ordinære trøjeudvælgelse krævede, at spillerboksen dækkede mindst 0,8 procent af hele billedet, og valgte derefter de største bokse. I portrætvideoen kunne et tydeligt rygnummer derfor være udelukket, mens senere front-/sideudsnit blev valgt. God association er ikke ensbetydende med, at et nummer kan læses.

Dense tracking måler nu central torso på det faktisk afkodede CV-billede: pixelbredde, pixelhøjde, Laplacian-skarphed og overlap med andre detekterede legemer. Målingerne følger alle tre associationstilstande, men uafklarede associationer kan fortsat ikke vælges af den ordinære trøjeudvælgelse. Metadata tilfører ingen trøjenummer-, hold- eller identitetsvurdering.

Den native udvælgelse kræver faktiske medietidsstempler uden fallback, mindst 32 x 40 målte torso-pixels, skarphed mindst 12 og ingen anden detektionsboks med IoU på mindst 0,25. De værdier er selektionsheuristikker, ikke kalibreret sandsynlighed for læsbare cifre. Manglende zoner opskaleres ikke til kunstig pixelstøtte. Store bokse med ugyldige, slørede eller overlappede native målinger må ikke falde tilbage til arealreglen.

Op til fem tidsbånd over et tracks målte levetid bidrager med højst ét klart udsnit hver; eventuelle ledige pladser fyldes med uafhængige kandidater. Mindst 120 ms mellem valgte billeder er uændret. Den native skarpheds-/tidsprioritet bevares gennem request-merge, så afstand til en kontakt ikke igen flytter store, senere udsnit først i køen. Selvstændigt pixelinspicerede requests beholder deres eksisterende forrang.

Ældre spor uden native kvalitetsmetadata bruger fortsat den hidtidige arealregel og sortering. Kun fysisk involverede tracks indgår i ordinær udvælgelse. Målspiller og verificerede release-aktører beholder deres eksisterende prioritet. Maksimum er stadig fem udsnit pr. track og 24 læsninger i providerens afgrænsede kald. Flere egnede billeder kan bruge en større del af det eksisterende budget; maksimum forhøjes ikke.

Nummerkonsensus, alle positive identitetskrav og de kanoniske begivenhedskrav er uændrede. Den uafhængige trøjelæser modtager fortsat kun et originalt billedudsnit uden forventet nummer, spilleridentitet eller referenceaktion. Ny lokal CPU bruges til torso-målinger; der tilføjes ingen detektor-forwards. Samlet rapportlatens er ikke benchmarket her.

## Originale billeder og før/efter

361 originale billeder i én scene er afkodet på ny i hver lane, med faktiske PTS uden fallback. Afgrænsningen kommer fra et eksisterende produktionsvindue, ikke indkodede referenceaktionstider. Begge lanes bruger de samme, hash-verificerede native detektionsforslag fra den tidligere lokale kontrol. Det er en ny måling af torso-pixels og kamerabevægelse, **ikke en ny native detektorkørsel eller komplet videoanalyse**.

| Måling | Før | Efter |
| --- | ---: | ---: |
| Originale frames pr. lane | 361 | 361 |
| Mulige requests efter selection/merge | 26 | 47 |
| Requests inden for providerbudgettet | 24 | 24 |
| Kontakter i fysisk rekonstruktion | 19 | 19 |
| Frames med målspillerstatus `UNRESOLVED` | 361 | 361 |
| Nye trøjevotes eller identitetsbeviser | 0 | 0 |

De 361 komplette dense frame-records er identiske mellem lanes, når den nye torso-kvalitetsmetadata fjernes. Der er 1.882 målte spillerudsnit; alle 24 planlagte efter-requests har native kvalitetsmetadata. Der opstår ingen forbedring af kanonisk identitet eller fysisk eventaccept fra metadata alene.

For det tidligere undersøgte hvide track valgte før-lanen front-/sideudsnit ved 20,849 og 20,982 sekunder. Efter-lanen vælger rygudsnit ved 20,466 og 20,149 sekunder. På disse to uafhængige originalbilleder er 15 visuelt synligt. Billederne er valgt uden forventet nummer; den visuelle kontrol er efterfølgende privat diagnostik og bliver ikke omdannet til produktionsvotes. Det er dokumenteret bedre input til den selvstændige læser, ikke bevis for, at den udpegede spiller er genidentificeret efter klippet.

Den afgrænsede før/efter-kontrol tog 57,777 sekunder inklusive original-crop-inspektion. SDK og netværk var blokeret; registrerede forsøg var nul. Trøje-, rolle- og mållæsere var ikke konfigureret, ekstra pixelbaseret occlusion recovery var slået fra, og ingen gamle gemte kontakter, trøjevotes eller mål-/saveafgørelser blev tilført.

## OCR og den resterende identitetsblokering

Begge lanes' 24 planlagte udsnit blev afprøvet med samme lokale, blinde Tesseract-procedure: 48 originaludsnit og 96 forsøg. Gentagne visninger af samme billede er ikke uafhængige votes. Der kom stadig ikke en brugbar aflæsning af 15. Ingen OCR-output blev lagt i produktionskonsensus eller brugt til identitet.

Den eksisterende lokale genidentifikation er tidligere kørt over hele denne originalvideo med samme identitets-/embedding-kildekode. Den tapløse skudscene forblev `UNRESOLVED`; at gentage uændret kode ville ikke skabe et nyt evidensgrundlag. Den eksisterende verificerede trøjehåndtering kræver desuden et direkte identitetsanker i samme scene. Bedre nummerbilleder ophæver ikke det krav. En selvstændig, dokumenteret genidentifikation efter klip er fortsat nødvendig. Kandidaten flytter ikke en markering gennem et klip og fjerner ikke dette sikkerhedskrav.

## Test og leverance

**634 tests i 46 filer består**, heraf 26 nye syntetiske regressionstests. De 581 tidligere udvalgte tests er med plus 27 eksisterende Orman10-recovery-tests. Testharness blokerer faktisk SDK, netværk og videoafkodning; alle registrerede forsøg er nul. Der er én kendt lokal Starlette/httpx-deprecation-advarsel. Ingen eksisterende assertions er svækket. Den tidligere fulde pakke på 1.245 tests er ikke kørt igen lokalt.

SDK-runner, FIX10B, identitetsautoritet og nummerkonsensuskrav er uændrede. Ingen Emergent, nye betalte modelkald, nye markeringer, merge eller deployment er foretaget. Seneste afsluttede strenge vurdering af hele videoens fem referenceaktioner er fortsat **R5: 0 af 5 verificeret**. Der er ikke udført en ny fem-aktionsvurdering her.

Kun to kodefiler, den nye syntetiske testfil, dette statusdokument og manifestet `backups/CODEX_R6_NATIVE_JERSEY_MANIFEST.json` lægges på GitHub. Rå video, billeder, cachedata, markeringernes koordinater og credentials er udeladt.
