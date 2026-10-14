# R6: fem native forløb og korrekte afstande i pixels

Status 2026-10-12, oven på `e7537e4857bcba3627c7c694aaaa3fd45dc269ef` på `codex-r6-native-jersey-20261011`.

**De fem referenceforløb er lokaliseret til gennemgang. Automatisk, kanonisk verificering er fortsat 0/5. Ingen merge eller deployment.** Den samme originalvideo og alle 12 eksisterende markeringer bruges; der er ingen nye markeringer, Emergent-kald eller betalte modelkald.

## Konkret fejl

Krops- og boldbokse normaliserer x efter billedets bredde og y efter højden. Flere kontaktberegninger brugte derefter `hypot(dx, dy) / body_h`, som om de to akser havde samme skala. Det gav forskellige afstande og vinkler for de samme pixels i kvadratiske, vandrette og lodrette billeder.

Et faktisk billede ved 23.499 sekunder viser forskellen: den native boldproposal nær en hvid spillers underkrop havde afstand 0.832 kropshøjder med den gamle formel, men 0.470 i de faktisk afkodede 960 x 1707-pixels. Kontaktgrænsen er fortsat 0.58. Dette beviser en enhedsfejl; det beviser ikke, at denne proposal er den aktive bold eller at spilleridentiteten er korrekt.

`frame_geometry.py` omsætter nu x-forskelle med `width / height`, før afstande i kropshøjder beregnes. Dimensionerne måles på den faktiske CV-matrix og mærkes `DECODED_NATIVE_PIXELS`. Ugyldige eller blandede dimensioner kan ikke give geometri-bevis. Historiske traces uden dimensionsmetadata beholder deres tidligere fortolkning.

Rettelsen bruges til A4-kontakt og besiddelse, fysisk aktørkontinuitet, A3's fodstøtte ved genfinding, Step-3's underkropszoner og separationsgevinst samt forsinket release-klassifikation. A4's retningsvinkel bruger samme koordinatsystem. Alle eksisterende kontakt-, afstands-, besiddelses-, tvetydigheds-, identitets-, tids- og eventgrænser er bevaret. A3's generelle normaliserede kinematik og den tætte tracker-association er ikke omskrevet i denne revision.

## Testresultater

43 nye tests sammenholder geometri med direkte pixelmålinger på flere billedformater. De dækker også fuld kontaktklassifikation, falsk release ved en kort dribling, reel separation, aktør-/tapkontinuitet, ugyldige dimensioner, legacy-adfærd og faktiske matrixdimensioner frem for rapporterede inputstørrelser.

15 af integrationstestene er desuden kørt på de uændrede produktionsmoduler fra `e7537e4`: **6 fejler og 9 består**. Kun den nye testfil og dens ubrugte dimensionshjælper blev kopieret til baseline-checkoutet. Fejlene viser forkert pixelafstand, en mistet kontakt, en falsk release, en mistet reel release samt forkert accept/afvisning af fysisk kontinuitet. De skyldes ikke ændrede funktionssignaturer.

**820 lokale tests i 52 filer består**, inklusive alle tidligere 777 og de 43 nye. Eksisterende assertions er ikke svækket. Offline-harnesset registrerer nul netværks-, faktisk SDK- og videoafkodningsforsøg under testene. Én AnyIO/Starlette-deprecation-advarsel er bevaret. Den fulde historiske testpakke køres af CI, ikke af dette lokale udvalg.

## Samme originalvideo, fem eksisterende vinduer

Den friske native baseline afkoder 1.922 billeder med faktiske PTS og udfører 3.797 lokale YOLOv8n-forwards. Der bruges kun eksisterende vinduers tidsafgrænsning fra eksporten. Gamle eksportkontakter, trøjelæsninger, modelidentiteter, outcomes og kanoniske events tilføres ikke rekonstruktionen. Identitetsautoriteten bygges fra de oprindelige markeringer og tidslinjen fra den nye lokale afgrænsningskontrol.

Efter-lanen genafkoder de samme originalbilleder og genbruger præcis de samme native proposals. Den isolerede afstandssammenligning bekræfter, at de raffinerede input er identiske bortset fra de nye dimensionsmetadata; der tilføres ikke nye modelobservationer. Flere accepterede kontakter er ikke i sig selv bevis for bedre eventkorrekthed.

| Reference | Originalt gennemgangsinterval | Native billeder | Kontakter før / efter | Kanonisk status |
| --- | --- | ---: | ---: | --- |
| Skud/redning, 23.680 s | 20.00–25.20 s | 354 | 16 / 25 | NOT_VERIFIED |
| Mål, 30.830 s | 28.80–33.00 s | 481 | 41 / 47 | NOT_VERIFIED |
| Assist 1, 43.190 s | 41.40–46.95 s | 402 | 55 / 80 | NOT_VERIFIED |
| Assist 2, 49.440 s | 48.70–52.65 s | 333 | 27 / 34 | NOT_VERIFIED |
| Assist 3, 56.440 s | 55.10–58.80 s | 352 | 29 / 44 | NOT_VERIFIED |

Referenceetiketterne stammer fra evalueringsfilen. De er ikke nye kanoniske resultater. Alle fem fejler fortsat med `QUALIFIED_CANONICAL_EVENT_MISSING`. Kørselen er begrænset til de fem vinduer og certificerer ikke genfinding gennem hele videoen.

Den nye `backend/scripts/audit_native_five_actions.py` gør kontrollen gentagelig. Den afkoder originalvideoen igen, bygger autoriteten fra de samme markeringer og afgrænsningstidslinjen, blokerer netværk/SDK og evaluerer først referenceetiketterne efter fysisk rekonstruktion. En valgfri cache indeholder alene native proposals bundet til hash af de faktiske billedpixels, videohash, detektorhash og detektorkode. Manglende eller forkert cache kan ikke bruges i `--cache-only`-tilstand. Scriptet er kørt på alle 1.922 billeder med 1.922 præcise cachehits, nul nye detektor-forwards og nul netværks-/SDK-forsøg. Det giver også 0/5.

Eksempel med private input og output uden for checkoutet:

```bash
python backend/scripts/audit_native_five_actions.py \
  --video /private/original.mp4 --anchors /private/anchors.json \
  --identity-timeline /private/timelines/after.json \
  --evidence-export /private/evidence.zip \
  --cases docs/examples/five_action_reference_cases.json \
  --output /private/native-action-audit --cache /private/native-proposals.json
```

Uden en eksisterende cache beregner scriptet nye lokale detektorproposals. `--cache-only` kræver en allerede valideret pixelcache. Referencetidslinjen kan gendannes med den eksisterende `audit_body_crop.py` og dens `--private-timelines`-mulighed.

## Hvad der fortsat mangler

- Skudscenen efter det virkelige sceneskift har ingen sikker GLOBAL_TARGET-identitet. Målkontakten mister også identitet omkring duellen.
- Det globale boldspor vælger flere steder en reservebold eller en støvle. Den aktive bold mangler mellem benene eller lige efter release. De relevante native proposals er ikke en sammenhængende, verificeret kontakt- og afleveringskæde.
- Flere touch-fragmenter blander kontrol og release. Aktørskift og overlap er fortsat usikre.
- Målmandsrolle, berøring og målplanspassage er ikke uafhængigt verificeret. De nye kørselers rolle-, jersey- og målproviders er ikke konfigureret; de fejler lukket.

Gratis lokale læserforsøg tilføjer ikke bevis: Qwen3-VL 4B gav modstridende diagnostiske rygnummer-svar på to tidsmæssigt adskilte udsnit. Qwen3-VL 8B afviste begge med `readable=false` ved et mindre billedbudget; de første større forsøg ramte hukommelsesgrænsen. En særskilt lokal YOLOv9-boldmodel gav ingen proposals ved sin dokumenterede 0.20-grænse på seks prøver. Ingen af disse svar bruges som trøjevotes, target-identitet, bold-, rolle- eller eventbevis. Ingen model eller ny modeldependency tilføjes til produktet i denne revision.

De fem intervaller er samlet i `ScoutMePlay-fem-referenceforloeb.mp4` til manuel gennemgang. Den video ændrer ingen markeringer eller kanoniske events. Rå video, billeder, markeringer, spor og modelvægte fra forsøgene er ikke med i committen.

Teknisk test-PASS og grøn CI opfylder ikke kravet om fem verificerede aktioner. Deployment forbliver blokeret af 0/5-resultatet.
