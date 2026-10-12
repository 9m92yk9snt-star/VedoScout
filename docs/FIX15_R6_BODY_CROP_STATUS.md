# R6: identitetsudsnit afgrænset til kropsboksen

Rettelsen bygger direkte på `f96315eaabd3405dc335f9b7fb6aeecc28321716` på `codex-r6-native-jersey-20261011`. Den er en kandidat til afgrænsningsfejlen. De fem referenceaktioner er fortsat ikke verificeret, og der foretages ingen merge eller deployment.

## Fejl og rettelse

`cv_shadow._comp_mask_crop` lagde 10 procent af kropshøjden til på alle sider. Komponenten nærmest kroppens centrum kunne fortsætte ud i denne ekstra rand. Dens pixels og udstrækning påvirkede Lab-features, aspect, zoneinddeling og identitetsscore. Også reserveudsnittet, når ingen komponent kunne isoleres, omfattede randen. Helt tomme eller ugyldige bokse kunne låne pixels fra omgivelserne eller give en OpenCV-fejl.

Komponentudvælgelse og reserveudsnit bruger nu alene kropsboksens skæring med det faktiske billede. Tomme skæringer giver ingen embedding. Den eksisterende komponentudvælgelse inde i boksen, samme-frame ownership-masker, occluder-kontrol og alle identitetstærskler er bevaret. Der ændres ingen nummerlæsning, kontakt-, bold-, rolle-, mål- eller kanonisk eventregel.

Selve banens lysreference er fortsat en måling af hele billedet. Afgrænsningsgarantien gælder med den samme lysreference; kontrollen holder derfor `pitch_l` fast, når pixels uden for boksen ændres. Rettelsen beviser heller ikke, at alle pixels inde i en kropsboks tilhører den udpegede spiller. Blandede legemer og holdkammerater med samme dragt er fortsat et særskilt identitetsproblem.

## Regressionstests

25 nye tests bruger den faktiske komponent-/embedding-kode: sammenhængende pixels uden for kroppen, tilfældig tekstur, billedkanter, tomme/offscreen bokse, komponent-fallback, en separerbar anden spiller, ownership/occlusion samt en reel farveændring inde i kroppen. På den gamle kode fejlede 22 af dem; tre eksisterende egenskaber bestod. Alle 25 består efter rettelsen.

**777 tests i 51 filer består**: alle 634 tidligere udvalgte tests, de 25 nye og 118 yderligere eksisterende tests for pixel-ejerskab, spillerudvælgelse, identitetstidslinje og identitetsautoritet. De tidligere assertions er bevaret. Det lokale harness blokerer netværk, faktisk SDK og videoafkodning; alle registrerede forsøg er nul. Én lokal AnyIO/Starlette-deprecation-advarsel er registreret. Den fulde historiske testpakke er ikke kørt lokalt.

## Originalvideo med de eksisterende markeringer

Den samme originale 1080 x 1920-video og alle 12 markeringer er verificeret mod de tidligere hashes. 11 markeringer bliver brugbare tap-referencer i begge lanes. Der udføres en frisk afkodning i hver lane. Den lokale, uændrede YOLOv8n-detektor beregner 364 unikke originalbilleder én gang og genbruger kun detektionerne for præcis samme pixelhash i den anden lane. Der tilføres ingen gemte identiteter, trøjevotes, kontakter eller outcomes.

Begge lanes har **364 billeder med faktiske PTS, nul fallback-tider, 2.292 detekterede kropsbokse og identiske hashbundne geometri-, kamera- og tidsinput**. Det ændrede crop bruges også i tap-referencerne og den fulde lokale identitetstidslinje.

| Måling | Før | Efter |
| --- | ---: | ---: |
| Embedding-kald, inklusive tap/negativreference | 2.304 | 2.304 |
| Udsnit med støttede pixels uden for kropsboksen | 2.289 | 0 |
| Summerede støttede pixels uden for boksen, pr. kald | 2.292.252 | 0 |
| Ikke-tomme embeddings | 2.296 | 2.300 |
| Målepunkter accepteret af identitetskoden | 173 | 167 |
| `CUT_REID`-punkter | 0 | 0 |

For hvert af efter-lanens 2.304 embedding-kald udskiftes alle pixels uden for den accepterede kropsboks med henholdsvis hvidt og blåt. **Alle 4.608 sammenligninger bevarer den samme embedding**, inklusive maskestøtte, skala, aspect og Lab-zoner. Der er nul afgrænsningsbrud og nul netværksforsøg. Kontrollen af afgrænsningen består.

Faldet fra 173 til 167 accepterede målepunkter er ikke bevis for bedre identitetskorrekthed. Scene 4 mister otte punkter, scene 5 får to; andre sceners antal er ens. Den tapløse scene 2 ved skuddet har fortsat ingen accepterede identitetspunkter. Identitetsscore og dækning skal vurderes med uafhængig evidens, før denne kandidat kan godkendes som et komplet produktfix.

Der udføres ingen ny streng fem-aktionsvurdering. Seneste afsluttede vurdering er fortsat **R5: 0 af 5 verificeret**. Denne crop-kontrol giver derfor ingen godkendelse af mål, reddet skud eller assists.

## Gentag den afgrænsede kontrol

Brug `backend/scripts/audit_body_crop.py` med den oprindelige video og `anchors.json`. Gem baseline-kilden fra `f96315e:backend/cv_shadow.py` lokalt, og giv følgende obligatoriske argumenter:

```sh
python backend/scripts/audit_body_crop.py \
  --video /ABSOLUT/STI/TIL/ORIGINALVIDEO.mp4 \
  --anchors /ABSOLUT/STI/TIL/anchors.json \
  --video-sha256 2774978344f9c54e44f81c2328f3165d3aada4f1b95193964bb22b73a9ecf85b \
  --anchors-sha256 0a49e85e325cbffb36f2296bad75ebf5051a53e5e8442a534fbe18f172da29ed \
  --baseline-source /ABSOLUT/STI/TIL/cv_shadow_before.py \
  --baseline-sha256 045bef4579cd016ebfce9437aec1ddc53b4e55b7c3d3a997fd57396f712165a8 \
  --output /ABSOLUT/STI/TIL/body-crop-original-ab.json
```

`--private-timelines` kan gemme lokale identitetstidslinjer til videre diagnostik. De indeholder kropsgeometri og skal holdes uden for Git. Det almindelige audit-output består af aggregerede målinger og kilde-/inputhashes.

Kildehashes, den fulde testliste og den aggregerede originalkontrol findes i `backups/CODEX_R6_BODY_CROP_MANIFEST.json`. Rå video, billeder, markeringernes koordinater, private tidslinjer og credentials lægges ikke på GitHub. Ingen Emergent, betalte modelkald, nye bruger-markeringer, databaseændringer, merge eller deployment er foretaget.
