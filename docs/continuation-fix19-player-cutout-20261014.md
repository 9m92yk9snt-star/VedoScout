# ScoutMePlay / VedoScout — fortsættelse 14. oktober 2026

**Nyere status:** FIX19-kode, modelpakning og validering fortsættes i
`docs/fix19-player-cutout-validation.md`. Nedenstående er det oprindelige
WIP-checkpoint og beskriver derfor også mangler, som senere er rettet.

Dette er et checkpoint til en ny chat. Brugeren bad om at flytte samtalen,
mens FIX19 stadig var under udvikling. Fortsæt arbejdet fra GitHub; antag ikke,
at gamle lokale filer, screenshots eller samtalehistorik findes i den nye chat.

## GitHub-status

- Repository: `9m92yk9snt-star/VedoScout`.
- Færdigtestet FIX16–18: draft [PR #31](https://github.com/9m92yk9snt-star/VedoScout/pull/31).
- PR-gren: `codex-fix16-orman100-physical-admission-20261014`.
- Verificeret PR-head: `7c41977b94e094ce9095d1dab25b82a646e82af9`.
- Base-tree: `f613fb790780679369fb7be748722b2f1cd1fb2d` (1.043 filer).
- Alle 10 GitHub-checks på denne head var grønne ved checkpointet: to kørsler
  af backend_regression, frontend_build, player_selection, fix10_unit og
  report_evidence_export.
- PR #31 var åben, draft og **ikke merged**. Main var
  `1ee2fd2aa7b2c64f78011472b86496c73fe7b3a0`. Rettelserne er ikke deployet live.
- FIX19-kilde og denne plan gemmes særskilt på
  `codex-fix19-player-cutout-wip-20261014`, med 7c41977 som parent.
- **FIX19 er ikke færdigtestet eller klar til merge/deploy.** Dens modelgraf-filer
  er ikke med i dette checkpoint. PR #31 og main er ikke flyttet til WIP-koden.

## Brugerens mål og seneste krav

ScoutMePlay skal efter den første spillerudvælgelse analysere automatisk uden
en ny manuel side med tre cirkel-taps. Brugeren ønsker intelligent udklip af
den synlige spiller: hoved, krop, trøje, arme og ben, ikke kun trøjen.

Når spilleren står bag andre, skal brugeren kunne markere området og vælge
**“Player is behind”**. Bevar området, lad brugeren markere synlige dele af sin
spiller og udelukke spilleren foran. Kun synlige pixels tilhørende den valgte
spiller må bruges; skjulte kropsdele må ikke opfindes. En sådan markering
forbliver partial og er ikke fuldt identitets- eller handlingsbevis.

Brugeren vil senere deploye gennem Emergent og køre en ny videoanalyse med nye
taps. Ingen ny Emergent-login eller deploy er gennemført her.

## FIX16–18: hvad der allerede er afsluttet

Læs de eksisterende detaljer i `docs/fix16-degenerate-sequence-recovery.md`,
`docs/fix17-contact-reinspection.md` og `docs/fix18-automatic-player-selection.md`.

- FIX16: reparation af degenereret scenedækning og sikker physical admission;
  manglende evidens forbliver PARTIAL. Konflikt mellem erklæret trøjenummer og
  uploadfelt afvises før betaling/lagring. Ingen falsk måltekst fra legacy-data.
- FIX17: én afgrænset kontakt-geninspektion, større budget op til 8, deduplikering
  efter faktiske frame-tider og bedre prioritering af relevant synlig evidens.
  Identitets- og eventkrav er bevaret.
- FIX18: én indledende editor med 3–10 klare referencer. Ingen obligatorisk
  ekstra fase med tre checks. Backend fortsætter automatisk med usikkerhed
  registreret; usikre spillere bliver ikke gættet. Historiske ventende rapporter
  kan fortsættes uden den gamle manuelle modal. Indtastet trøjenummer vises.
- FIX18 havde helområde-preview med valgfri maskering. FIX19 ændrer dette til
  automatisk personudklip efter brugerens nye krav.

## FIX19: kildekode i dette WIP-checkpoint

| Fil | Arbejde gemt |
| --- | --- |
| `backend/native_player_segmentation.py` | CPU person-instance-masker, udvidet kontekst omkring tap, outline-tilpasset automatisk boks, afvisning af tvetydige/trøje-only forslag. |
| `backend/prompt_player_segmentation.py` | MobileSAM encoder/decoder til positive synlige dele og negative forgrundsmarkeringer; forgrundens hele maskeforslag trækkes fra. |
| `backend/server.py` | Mask-route bruger lokal segmentering og de nye behind/include/exclude/auto-box hints. |
| `backend/player_selection.py` og `selectionHints.cjs` | `player_behind` serialiseres og tvinger partial, så det ikke bliver fuldt identitetsbevis. |
| `frontend/src/components/MarkerStudio.jsx` | Sender hints og modtager mask + boks + metadata. |
| `frontend/src/components/marker-studio/ScoutMode.jsx` | Automatisk maske efter tap, maskeret preview + område-preview, separat behind-knap der bevarer området, synlige/negative punkter. |
| `backend/requirements.txt` | Tilføjet `onnxruntime==1.31.0`; Torch er kun til modelbygning. |
| `backend/tests/test_fix19_player_cutout.py` | Tests af de faktiske hjælpefunktioner med injicerede modeller, inklusive synlige kropsdele, modstridende punkter, partial og checksum. |
| `backend/scripts/export_player_selection_models.py` | Reproducerbar eksport med verificerede kilde- og output-checksums; ingen download under serving. |
| `backend/models/yolov8n-seg-model-card.md` | YOLO-proveniens og begrænsninger. |

Hjælpemodellerne foreslår udklip. De godkender ikke automatisk mål, assists eller
spilleridentitet. Den oprindelige brugerbekræftelse i editoren er stadig nødvendig.

## Faktisk validering og kendte mangler

- Den lokale udvalgte backend-kørsel med FIX19 + FIX18 + player_selection og
  player_selection_routes bestod: **51 passed**, 2 warnings. Offline-runneren
  registrerede 0 netværkskald, 0 SDK-kald og 0 videodekodning i denne test.
- Frontend-tests er **ikke opdateret eller kørt for FIX19**. Eksisterende
  `ScoutMode.test.jsx` forventer det gamle valgfrie udklip og skal tilpasses.
- Kendt UI-punkt: et fejlet maskeforslag efterlader `maskRequested=true`, mens
  retry-knappen afhænger af false. Ret dette og test retry/stale svar/manuel boks.
- Test behind-flow med bevaret område, først negativt forgrundspunkt og derefter
  positiv synlig del; kræv korrekt preview før Confirm. Test re-tap og tilbage
  til normal synlig spiller. Undgå at opfinde et positivt punkt ved resize.
- Read-only afprøvning på gamle Orman-taps gav YOLO-forslag for **7 af 11**
  punkter og ingen maske for 4. Det er udklipsforslag, ikke handlings-recall.
  Nogle tætte dueller gav rester af en anden spiller i masken.
- MobileSAM behind-forsøg virkede på et afprøvet punkt, men andre synlige- og
  forgrundspunkter blev afvist. Fuld adskillelse af forgrundens ben er endnu ikke
  dokumenteret. Foretag billedkontrol; antag ikke at en høj modelscore er bevis.
- Der er **ingen ny komplet ScoutMePlay-videokørsel** med FIX17–19 og ingen
  dokumentation for, at de fem referenceaktioner nu er automatisk godkendt.

## Modelgraf-filer: mangler på GitHub og kan genskabes

De tre lokale ONNX-grafer blev eksporteret, men er **ikke committed på denne
gren**. En tidligere upload gav ingen bekræftet Git-reference. Brug ikke
WIP-grenen som en deploybar pakke uden at få graferne med og teste dem.

| Output i `backend/models/` | Bytes | SHA256 |
| --- | ---: | --- |
| `yolov8n-seg.onnx` | 13.841.502 | `015043fb9cc94830ad7065dd3e28d6f8e5758fe03071451675120f6a6b6e44e9` |
| `mobile-sam-encoder.onnx` | 27.969.718 | `85dc9194671a1173fc5632fc1ffae698f3ca0c82c7b208ed618a568377380d7e` |
| `mobile-sam-decoder.onnx` | 16.496.933 | `43c7655a81b62c0f2b0e31d2bc91d3811b48d7f736ecf93b3a4a1254318241cf` |

YOLO-kilde: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-seg.pt

- Bytes: 7.071.756; SHA256
  `a7cd8f929e1903d78a12a48efecab430209f18dc46cb96c3599a5980c63c423c`.
- Ultralytics 8.3.0, AGPL-3.0. Bevar modelkort/licensproveniens ved pakning.

MobileSAM-kilde: https://github.com/ChaoningZhang/MobileSAM

- Checkout commit `f706ad9c4eb7f219c00d9050e46328518ffb65d2`.
- `weights/mobile_sam.pt`: 40.728.226 bytes; SHA256
  `6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f`.
- Apache-2.0. Tilføj kilde-LICENSE og MobileSAM-modelkort før graferne distribueres.

Eksportmiljøet brugte Python 3.11, `torch==2.5.1+cpu`,
`torchvision==0.20.1+cpu`, `ultralytics==8.3.0`, `onnx==1.17.0`,
`timm==0.9.16`, `numpy==1.26.4`, `opencv-python==4.11.0.86`.
YOLO: statisk 640, opset 12, simplify=False. MobileSAM: encoder 1024,
opset 17, dynamisk antal prompt-punkter i decoder.

I et isoleret eksportmiljø, efter at have hentet og verificeret de offentlige kilder:

```bash
python backend/scripts/export_player_selection_models.py \
  --yolo-weights /absolute/model-build/yolov8n-seg.pt \
  --mobile-sam-source /absolute/model-build/MobileSAM
```

Hvis eksportens hashes afviger, undersøg versions-/eksportforskellen. Skift ikke
runtime-checksums automatisk. Serving bruger lokal OpenCV/ONNX Runtime på CPU.

## Orman100: tidligere evidens, ikke nyt resultat

Rapport: `12186803-8681-4d1c-bd17-3582508d2c93`.
Gammel run: `5039563fa90c407794bb4a2ad5aea8cc`.
Video: ca. 76,764 sekunder, 1080×1920, ca. 60 fps, 4.606 frames.
SHA256: `0e6c68902aa3d01971f7f327b0fa432e5c526c60654062cc6f01276646884abb`.
Uploadfeltet havde nummer **5**, mens teksten og brugeren angav hvid **15**.
Oprindelsen til den gamle værdi 5 er ikke bevist; taps indeholder ikke et
trøjenummer og må ikke bruges til at gætte dette.

11 historiske tap-tider: 3.83, 11.5, 19.18, 26.87, 34.53, 42.21, 57.56,
49.9, 15.35, 41.38, 61.4 sekunder. 9 havde gamle masker; det beviser ikke,
at de masker omfattede hele den rigtige spiller.

Referenceaktioner ligger i `docs/examples/five_action_reference_cases.json`:
saved shot 23.68, goal 30.83, assists 43.19, 49.44 og 56.44.
49.44 er brugerens rettede #7 → #15 → #10 scorer. De fem labels er kun
efterfølgende QA-reference, aldrig input, hardcoded sandhed eller bevis.
Den gamle ufuldstændige native-audit var PARTIAL og havde 0/5 kvalificerede
referenceaktioner. Den må ikke præsenteres som det nye systems resultat.

Brugerens screenshots/video/PDF/ZIP er **ikke lagt på GitHub**. Hvis originalerne
ikke findes i den nye chat, skal de vedhæftes igen før billed- eller event-QA.

## Næste arbejde i rækkefølge

1. Hent WIP-grenen og læs denne plan samt FIX18-doc. Verificer remote-status;
   beskyt den allerede grønne PR31-base.
2. Genskab/pak de tre modelgrafer, verificer checksums og tilføj modelkort/licenser.
3. Ret retry og gennemtest det automatiske udklip/behind-flow i frontend.
   Opdater de meningsfulde UI-tests og kør frontend-checks + relevant backend-suite.
4. Kontroller rigtige frame-udklip i tætte dueller. Afvis tvetydighed og behold
   partial; ingen skjult krop eller forkert spiller må vises som sikker maske.
5. Når FIX19 er færdigtestet, saml den i den relevante review-PR og synkroniser
   kildekoden til Emergent. Brugeren deployer live gennem Emergent.
6. Brugeren kører ny ScoutMePlay-analyse med korrekt nummer 15 og nye initiale
   taps. Inspicer ny PDF og komplette evidens-ZIP og sammenlign de fem aktioner
   mod faktisk identitet, kontakt, boldbane og scoringsbevis.

## Lokale spor fra denne session (kan være forsvundet)

Repo-snapshot: `/workspace/scratch/6cadc75029b6/VedoScout`.
Modelbygning: `/workspace/scratch/6cadc75029b6/player-mask-model`.
Native udklipsreceipt: `player-mask-model/native-check/receipt.json`.
Original eksport: `upload/12186803-8681-4d1c-bd17-3582508d2c93-evidence (1).zip`
og `upload/EliteScout_Orman100_Report.pdf`. Privat audit: `orman100-audit/`.
Disse stier er historiske hints, ikke holdbar dokumentation eller lovet adgang.

Kort prompt til ny chat: “Fortsæt ScoutMePlay/VedoScout fra branch
codex-fix19-player-cutout-wip-20261014 i 9m92yk9snt-star/VedoScout. Læs
docs/continuation-fix19-player-cutout-20261014.md. FIX16–18 har grønne checks
i PR31. Færdiggør og test intelligent spillerudklip og Player is behind, uden
ekstra manuelle spillerchecks efter initiale taps, før merge/deploy.”
