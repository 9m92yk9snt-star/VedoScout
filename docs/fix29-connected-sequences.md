# FIX29: sammenhængende spiller- og angrebssøgning

Implementeret i en isoleret gren fra FIX22, `3a6b50f`. Den præcise tidligere
FIX28-commit kunne ikke genfindes. `fix28-recovery-audit.md` beskriver opslagene
og de funktioner, der er genopbygget med nye tests.

## 1. Identitet gennem et sammenhængende spor

Den tidligere 1.200 ms bro bevares for ældre målinger. Et længere forløb kan
nu beholde identiteten fra sit oprindelige bevis, når hvert trin har en
faktisk native kropsobservation, isoleret krop og et entydigt match i begge
retninger. Det målte tidsforløb erstatter en ubetinget nulstilling efter
1,2 sekunder. Nye poster bliver ikke nye uafhængige identitetsseeds.

Klip, fremmed scene, fallback, manglende/konkurrerende krop, eksplicit
identitetskonflikt og brud i billedrækken stopper forbindelsen. En krops lokale
ID alene forlænger ikke identiteten. Linkkontrollen genbruges mellem seeds,
så de samme billedpar ikke beregnes igen for hver oprindelig markering.

### Automatisk genidentifikation efter klip

En tidligere udvalgt spiller kan etablere en videobundet trøjereference, når
nummeret faktisk er læst på den kendte krop i to uafhængige billeder.
Brugerens oplyste nummer alene opretter ikke denne reference.

Efter et klip kan nye, uafhængige læsninger af samme nummer på en entydig
krop i det forankrede målspillerhold genfinde spilleren. Gamle koordinater
føres ikke over klippet. Nye lokale spor beholder deres egen navneplads.
Reference fra en anden video, en senere reference, dubletbilleder,
modstandertrøje, konkurrerende nummer/krop og konflikt med en allerede kendt
målspiller accepteres ikke som en ny identifikation.

Reference og nye trøjelæsninger kræver projektets faktiske billedlæser. Den
readerfri native kontrol opfinder ikke disse observationer.

## 2. Søg angrebet fremad og baglæns

`attack_sequence_search` bygger søgeepisoder fra eksisterende fysiske
kontakter og observerede udfald. En målspilleraflevering kan pege frem mod
modtageren. Et observeret terminalt udfald kan pege baglæns mod en tidligere
kontakt med en anden aktør, også når den første spilleridentifikation mangler.

Baglæns søgekanter er ikke bevis for en aflevering eller assist. Nye billeder
og de eksisterende fysiske beregninger skal etablere forbindelsen. En ukendt
spillerkontakt alene får ikke ny høj prioritet på bekostning af konkrete
mangler. Det sidste er kontrolleret særskilt efter native gennemgangen.

Læsere får fælles målte kontakter, spillerreferencer, roller, billedgrænser
og uafklarede spørgsmål. Rå modelbesvarelser og forventede spiller-/aktionstal
gentages ikke i dette input. Lokale billedlabels og fælles entity-ID'er er
adskilt. Modstridende rolleobservationer beholdes som alternativer.

## 3. Lad det observerede forløb bestemme konteksten

Et review med faktiske sammenhængende billeder kan følge den relevante
billedsekvens ud over den tidligere grænse på 2.600 ms efter kontakten.
Tidlige spark-/boldbilleder og terminal kontekst beholdes inden for det samme
billedbudget. Gentagne reviews bruger det samme bredeste kontekstgrundlag.
Den oprindelige målte kontakttid ændres ikke til et andet vindues kontakttid.

Den fysiske udfaldsberegning havde en separat grænse på tre sekunder. Den
kan nu følge en kvalificeret kontaktbunden boldbane videre. Et modeludsagn
eller en søgeplan kan ikke alene udvide bevisperioden. Forlængelsen kræver
en ubrudt målt boldrække fra det korrekte kontaktanker og stopper ved
afviste bolde, fallback, fremmed scene eller manglende målinger. De eksisterende
80 ms krav til målt boldkontinuitet og 900 ms okklusionshorisont bevares.

Kontrollerne omfatter en faktisk gennemkørsel af udfaldsfunktionen: En målt
krydsning efter tre sekunder kan genkendes, mens samme søgeplan med et hul,
forkert seed eller en forudsagt bold ikke giver den tidsforlængelse.

## 4. Brug arbejdet på manglende forbindelser

- Konkrete modelspørgsmål og rigere målte kæder kan prioritere efterkontrol.
  De anvender den eksisterende ene runde og højst otte valgte jobs.
- To adskilte spørgsmål i samme vindue kan medtages, mens nærliggende
  søgesteder og identiske billedinput genbruges. Hvert job bruger fortsat
  højst 12 actionbilleder.
- Kropslabels følger samme lokale spor gennem serien. Billeder omkring et
  native søgested koncentreres uden at tilføje modelbilleder.
- Målreviewets cache indeholder både kontekst og kontaktens native boldbane.
  Nye målinger kan genåbne vurderingen. Cachedata kopieres ved aflevering.
- Nærliggende billedanmodninger deler fremadrettet afkodning. Store spring
  bruger fortsat seek. Faktiske variable PTS og kildepixels bevares;
  fallback-tider returneres ikke som faktiske billedbeviser.
- Evidenseksporten medtager nu 15 manglende lokale kodeafhængigheder samt
  konfigurationen for tæt målreview. En test kontrollerer den transitive
  kildeafhængighed, så nye ZIP-filer kan dokumentere den anvendte kode.

Der er ikke tilføjet eller trænet en ny specialiseret boldmodel. En sådan
ændring bør sammenlignes på særskilt mærket materiale, før den får ansvar
for de eksisterende boldobservationer. Forbedringerne her bruger den
eksisterende detektor, bedre billedinput og målrettet genbrug.

## Validering på eksisterende data

Den afsluttende kernetest består **1.877 tests i 109 filer**, med 28 sprunget
over og to eksisterende afhængighedsadvarsler. De 56 nye FIX29-tilfælde og den
nye eksportkontrol indgår. Den fokuserede FIX29-/eksportkørsel består 92 tests;
den overlapper kernetesten. Kernetesten forsøgte ingen netværks-, SDK- eller
videoafkodningskald.

Fire kontroller blev også kørt direkte mod produktionens gamle funktioner fra
`3a6b50f` og de nye funktioner:

| Kontrolleret forhold | FIX22 | FIX29 |
|---|---|---|
| Samme entydige native kropsspor gennem fire sekunder | Identitet stopper efter 1,2 s | Identiteten følger det målte spor |
| Nye trøjelæsninger efter klip med tidligere bekræftet reference | Ingen genidentifikation | Ny identifikation uden ekstra tap |
| Målt boldkrydsning efter tre sekunder | Uafklaret | Fysisk krydsning verificeret |
| Sammenhængende billedvindue til 7 s, kontakt ved 1 s | Review slutter ved 3,6 s | Review følger til 7 s |

Det er kontrollerede kodeeksempler, ikke nye beviser for brugerens fem aktioner.

På den eksisterende kildevideo giver decoderkontrollen **identiske faktiske
PTS og identiske pixels for 156 billeder** fordelt på 13 jobs. Den separate
lokale prøve tog **25,796 s før og 9,002 s efter**. To andre prøver gav
31,835 → 12,543 s og 27,430 → 9,740 s. Baseline blev kørt først i hver prøve;
belastning og cache kan påvirke sekunderne. Dette dokumenterer en besparelse
i billedafkodningen, ikke en samlet liveanalysetid.

Den native sampling bruger også 156 billeder før og efter. Ved automatisk
valgte søgesteder findes nu i gennemsnit fire billeder inden for ±100 ms,
mod cirka 0,31 før. Søgestederne er native forslag, ikke kendte spark eller
facittider. Oversigtsbilledernes afstand ændres med koncentrationen.

Den afsluttende replay bruger de samme gemte native observationer og gennemfører
**15/15 vinduer uden fejl**. Alle afkodede frameposter, de 333 accepterede
kontakter og de fysiske udfald/krydsningsposter er identiske med kontrollen
fra den uændrede FIX22-kopi. Fire allerede kendte recoverykontakter bevares.
Nul nye detektorforwards, eksterne modelkald, netværksforsøg og databaseændringer.

Identitetsdækningen er i denne readerfri prøve fortsat 1.333 proof-eligible
frameposter i begge versioner. **De fem referenceaktioner er fortsat 0/5
automatisk verificerede.** Manglende trøje-/rolle-/målobservationer bliver ikke
opfundet. Den nye genidentifikation efter klip har brug for nye faktiske
billedlæsninger, selv om den bruger den eksisterende video og de gamle taps.
Der er derfor ikke dokumenteret en præcisionsgevinst på netop denne video.

Den lokale fysiske fase tog 66,163 s; baselineprøven tog 78,401 s. De blev
kørt med forskellig samtidig belastning og dokumenterer ikke en kontrolleret
hastighedsgevinst for den samlede fysiske fase. Kildekoden var uændret under
de afsluttende kontroller, og kvitteringens kildehashes matcher den gemte kode.

Den afsluttende kvittering er `examples/fix29-validation.json`. Den registrerer
kildehashes, tests, identiske decoderpixels, native vinduer og efterfølgende
kontrol af de fem referenceaktioner. Forventede aktioner er kun testfacit og
indgår ikke i rekonstruktion eller søgeplanlægning.

Reproducerbar lokal kontrol:

```bash
python backend/scripts/audit_fix29_saved_sequences.py \
  --run /private/existing-native-run --output /private/fix29-check --decode-check
```

Scriptet blokerer netværk og eksterne SDK-kald, genbruger gemte native
observationer og læser kun den eksisterende kildevideo. `--backend` kan pege
på den uændrede baseline. `--decode-only --decode-check` isolerer
billedafkodningen. Rå private traces og video placeres ikke i repositoryet.

De fysiske resultater og de fem aktioner skal vurderes særskilt fra beståede
kodetests. Der er ikke kørt en fuld analyse med tilsluttede billedmodeller,
og denne ændring dokumenterer derfor endnu ikke fem automatiske godkendelser
eller en bestemt samlet liveanalysetid.
