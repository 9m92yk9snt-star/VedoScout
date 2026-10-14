# R6: reservebold må ikke lukke detailsøgningen

Denne separate kandidat bygger på kontaktbundet R6, commit `90c340a04aa15e01842a4dd8482dae940d8d330e`. Den er udviklet og kontrolleret lokalt uden Emergent. Tidligere backup-grene, main og PR28 ændres ikke.

## Den dokumenterede fejl og rettelse

I portrætvideo mister hele billedet opløsning ved detektorens letterbox-skalering. Den hidtidige kode søgte kun mere detaljeret i området omkring spillernes fødder, hvis hele-billedet-søgningen ikke fandt nogen bold. En reservebold andetsteds i billedet kunne derfor forhindre, at et relevant område blev undersøgt nærmere.

Rettelsen udfører højst én ekstra, afgrænset native-søgning i dette område, også når der allerede findes boldforslag. Højst to native detector-forwards pr. billede; ingen rekursion. Hele-billedet-forslag bevares med deres oprindelige koordinater og score. Overlappende detailforslag fjernes med den eksisterende NMS-IoU-grænse, så samme detektion ikke automatisk tæller som to konkurrerende bolde. For store eller billedoverskridende detailbokse afvises.

Den eksisterende native boldgrænse på 0,03 og klasse-32/argmax-kravet er uændret. Svage A7-forslag er fortsat adskilte og ikke bevis. Flere forslag er ikke mere sandhed: kontakt-, same-ball-, kameratilstands-, identitets-, rolle-, mål- og kanoniske kontroller er ikke lempet. Den ekstra native-billedberegning kan øge CPU-tiden; der tilføjes ingen model/API-udgift.

## Faktisk før/efter-kontrol

Originalvideoen er afkodet på ny. 126 fortløbende billeder i et afgrænset skudvindue er sammenlignet ved faktiske medietidsstempler, uden fallback. Før-lanen bruger de native forslag fra en frisk, uafhængig pixelkontrol med den tidligere detektorlogik. Efter-lanen måler på ny gennem den ændrede detektorkode. Begge gennemgår de samme dense spiller-/kamerakontroller og produktionskodens fysiske rekonstruktion.

| Måling | Før | Efter |
| --- | ---: | ---: |
| Afkodede billeder | 126 | 126 |
| Billeder med native boldforslag | 59 | 59 |
| Native boldforslag | 86 | 124 |
| Verificerede kontakter med den udpegede spiller | 0 | 0 |
| Kandidatforløb med underbygget kontakt-til-startreference | 0 | 0 |
| Kanoniske skud godkendt | Ikke udført | Ikke udført |

Der blev altså bevaret flere alternative forslag, ikke dækket flere billeder eller verificeret et nyt skud. De ekstra forslag kan også omfatte falske detektioner af støvler eller andre objekter. Spillere, identitet og kameratilstande var uændrede mellem de to lanes. Den nye lane anvendte 214 lokale native detector-forwards på de 126 billeder.

Denne afgrænsede kontrol har ikke konfigureret trøje-, rolle- eller mållæsere, og svag A7-support er slået fra ens i begge lanes. Der er ingen yderligere pixelbaseret occlusion recovery, ingen genbrugte gemte målafgørelser og ingen kanonisk accept. Det er en detektorregression med fysiske kontroller, ikke en ny komplet videoevaluering.

En separat kontrol af 54 originale billeder bekræfter, at sceneskiftet inden skudsekvensen er et reelt klip. Markeringer fra den tidligere scene må derfor ikke føres videre som identitetsbevis. En ny selvstændig trøje-/spilleridentifikation efter klippet og målte billeder gennem flyvning og keeperkontakt er fortsat nødvendige. En bold liggende ved nettet beviser heller ikke, at skudbolden krydsede mållinjen.

## Tests og status

**546 tests i 42 filer består**, heraf 16 nye syntetiske regressionstests for denne ændring. De 490 tidligere udvalgte tests er med, plus 40 eksisterende detektor-, dense tracking- og fælles-evidenstests. Der er én kendt lokal Starlette/httpx-deprecation-advarsel. Ingen eksisterende assertions er svækket. Den fulde tidligere pakke med 1.245 tests er ikke kørt igen lokalt.

Testharness blokerer virkelig SDK, netværk og videoafkodning; alle registrerede forsøg er nul. Den særskilte native videokontrol tillader lokal afkodning og detektoren, men blokerer SDK og netværk; alle registrerede forsøg er nul. SDK-runner og FIX10B er uændrede.

Den senest afsluttede strenge evaluering af de fem referenceaktioner er fortsat **R5: 0 af 5 verificeret**. Dette er ikke en ny succesvurdering af de fem aktioner. Ingen Emergent, nye betalte modelkald, nye markeringer, merge eller deployment er foretaget. Rå video, billeder, cachedata, markeringernes koordinater og credentials lægges ikke på GitHub.

Manifestet `backups/CODEX_R6_GROUND_BAND_MANIFEST.json` registrerer kodehashes og den præcise testliste. Den private billeddiagnostik indgår ikke i den offentlige kodebackup.
