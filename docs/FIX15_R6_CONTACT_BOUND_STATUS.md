# R6: kontaktbundet boldspor

Denne særskilte kandidat er implementeret og testet lokalt den 11. oktober 2026 uden Emergent. Den bygger på den uafhængigt testede lokale R6-version. Den præcise ufærdige Emergent-version og de tidligere lokale versioner er bevaret på deres egne backup-grene. Dette er en vurderet integration af udvalgte rettelser, ikke en automatisk sammenfletning.

## Rettelser

| Område | Ny kontrol |
| --- | --- |
| Kontakt → bold efter kontakt | Start ved kontaktens målte bold. Kræv en entydig, målt forbindelse til den præcise efterfølgende boldreference inden for det eksisterende kontaktvindue på 300 ms. En god detektorscore eller et generelt boldspor kan ikke erstatte forbindelsen. |
| Bevægelse efter startreferencen | Bevar den allerede målte kontaktbevægelse, når sporet fortsætter. Nulstil ikke hastigheden ved boldreferencen efter kontakten. |
| Kameratilstand | Stop ved en eksplicit uafklaret kameratilstand. En senere etiket reparerer ikke den manglende forbindelse, og ingen transformation opfindes. |
| Rolleudsnit | Afvis kropsudsnit med konkurrerende eller modstridende lokale spiller-id'er. Budgettet er fortsat fire spillerspor og fire billeder pr. spor. |
| Produktion, replay og senere målgennemgang | Brug samme kontaktbundne sporvalg, og bevar årsagen til en afvisning i resultatets audit. Et afvist startanker må ikke genåbnes af A7 eller erstattes af et andet globalt spor. |

En anden bolds tidligere koordinater bruges ikke som et permanent identitetsforbud: den aktive bold kan legitimt passere stedet senere. Sammenhæng skal bevises gennem målinger ved de relevante tidspunkter.

Ingen forudsagt boldposition godkendes som måling. Målehuller over 80 ms afslutter sporet. De eksisterende identitets-, trøje-, team-, rollekonsensus-, målkrydsnings- og kanoniske beviskrav er ikke lempet. SDK-runner og FIX10B er uændrede.

## Verificering

490 tests i 38 filer består: 72 R6-tests og 418 øvrige tests. Denne revision tilføjer 31 tests; de tidligere 41 R6-tests er bevaret. Eksisterende testkrav er ikke svækket. Den tidligere fulde pakke med 1.245 tests er ikke kørt igen.

Den udvidede lokale kontrol ramte først en manglende, allerede eksisterende referencefixture og den manglende projektfastlåste `httpx==0.28.1`-afhængighed. Begge miljøproblemer er løst uden produktændringer eller ændrede testkrav. Alle 490 tests består derefter; det lokale nyere Starlette-testmiljø giver én deprecation-advarsel om httpx.

Den rent lokale cachekontrol genbehandler 1.945 eksisterende billeder fra fem native-vinduer gennem produktionskodens fysiske kontroller. Af de 29 oprindeligt gemte boldforløb har 12 en målt kontakt-til-startreference-forbindelse; 17 kan ikke underbygges. Det betyder ikke, at 12 aktioner er korrekte, eller at alle 17 afviste forløb er forkerte.

Ved genopbygning af kontakter og roller dannes 54 kandidatforløb: 27 med underbygget kontaktforbindelse og 27 med afvist forbindelse. Det er mellemresultater, ikke 54 godkendte hændelser. Der genbruges ingen gemt målafgørelse som ny bevisautoritet, og auditten accepterer ingen kanoniske events.

Netværk, virkelig SDK og videoafkodning er blokeret under tests. Cacheauditten blokerer også native-detektorer. Alle registrerede forsøg er nul, og der er ingen nye modelkald. Originalvideo, alle 12 markeringer, cachedata og de 16 registrerede R5-filer er verificeret uændrede. Rå video, markeringernes koordinater, rå cache og nøgler indgår ikke i denne ændring.

## De fem aktioner

Den senest afsluttede strenge videoevaluering er fortsat R5: **0 af 5 verificeret**. Denne kandidat har ikke fået en ny streng videoevaluering. Den gamle cache dækker alle fem referencevinduer, men er fra før den senere komplette supporting-review-kørsel.

Denne rettelse certificerer ikke selv, at kontaktens første objekt var kampbolden. Den tilføjer heller ikke manglende kameratransformationer, nye trøje-/rolleobservationer eller bevis for hele boldens passage af mållinjen. Næste arbejde er en lokal, afgrænset gennemgang af netop disse evidenshuller uden Emergent. Forventede hændelsesetiketter skal fortsat kun bruges til offline-evaluering, ikke som svar til billedlæseren.

## Gentag kontrollerne

Kør fra `backend` i et miljø med backendens testafhængigheder. Den komplette liste med 38 testfiler og kildehashes findes i `backups/CODEX_R6_CONTACT_BOUND_MANIFEST.json` ved repositoryroden.

```sh
python scripts/run_fix15_offline_tests.py --backend . --tb line tests/test_fix15_r6_ball_identity.py tests/test_fix15_r6_role_scheduling.py tests/test_fix15_r6_anchor_callers.py tests/test_fix15_r6_contact_binding.py
python scripts/audit_cached_contact_paths.py /ABSOLUT/STI/TIL/HASHBUNDET/CACHE --cases-json /ABSOLUT/STI/TIL/OFFLINE/REFERENCER.json
```

Cacheauditten kræver de oprindelige hashbundne cachefiler. Den udfører ingen nye billedlæsninger, modelkald, databaseopdateringer eller deployment. Et bestået testresultat er ikke i sig selv en godkendelse til merge eller live-brug.
