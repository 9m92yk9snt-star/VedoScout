# FIX28: kontrol af den oplyste commit og genopbygning

Kontrolleret 16. oktober 2026. Den tidligere samtale oplyste commit `0efda7f`
på `codex-fix28-adaptive-sequence-context-20261016`, oven på `cfd29db`.

## Hvad der kan bekræftes nu

- Den tilgængelige arbejdsmappe står på FIX22, `3a6b50f`.
- Ingen af de to oplyste Git-objekter findes i den lokale objektbase.
- Lokale grene, worktrees, filnavne og unreachable Git-objekter indeholder
  ikke den oplyste FIX28-kildekode.
- GitHubs commitopslag i `9m92yk9snt-star/VedoScout` returnerede HTTP 422:
  `No commit found for SHA: 0efda7f`.
- Søgning efter grenen `fix28` og commits med teksten `FIX28` returnerede
  ingen resultater i det kendte repository.

Det dokumenterer, at den præcise commit ikke kan genfindes i de kontrollerede
kilder. Det dokumenterer ikke, hvorfor den mangler. Den tidligere oplyste
testkvittering på 1.968 tests og FIX28-målingerne kan derfor ikke efterprøves
mod deres oprindelige kilde her.

## Hvad der er genopbygget

Arbejdet fortsætter i den isolerede gren
`codex-fix29-sequence-recovery-20261016` fra den verificerede FIX22-kilde.
Den oprindelige arbejdsmappe og dens eksisterende billedændring er bevaret.

| Registreret FIX28-funktion | Ny implementering |
|---|---|
| Tætte native søgebilleder med samme billedbudget | `sequence_observation_context.sampling_plan` |
| Stabile kropslabels gennem billedserien | `labels` og `measured_body_candidates` |
| Lokale LLM-hypoteser og opfølgende spørgsmål | Valgfrie felter i samme action-readerbesvarelse |
| Fælles målte observationer mellem vinduer og læsere | Kildebundet kontekst med eksplicitte entity-mappings |
| Sammenhold mål, keeperkontakt, udenfor og anden bold | Valgfrie målreviewforklaringer med faktiske billedreferencer |
| Afgrænset efterkontrol og genbrug af samme målreview | Eksisterende runde/budget og kontekstbundet cache |

Genopbygningen er ny kode med nye tests. Den er ikke en byteidentisk
gendannelse af `0efda7f`, og der påstås ikke en komplet gendannelse af
FIX23–FIX27. FIX29 føjer desuden længere målt identitetskontinuitet,
ny genidentifikation efter klip, tovejssøgning, sammenhængende
review-/udfaldstid og grupperet billedafkodning til denne verificerbare kilde.

## Grænse for resultatet

Kodetests og lokale kontroller er beskrevet i
`fix29-connected-sequences.md` og `examples/fix29-validation.json`.
De fem referenceaktioner er ikke indkodet som detektionssvar. Der er ikke
foretaget merge, push, deployment, eksterne modelkald eller databaseændringer
som led i genopbygningen.
