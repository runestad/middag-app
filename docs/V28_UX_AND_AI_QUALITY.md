# MatplanApp v28 – UX og AI-kvalitet

## Prinsipper

- Eksisterende Recipe Recovery- og importpipeline gjenbrukes.
- Ingen migrering eller automatisk Recovery kjøres.
- Pantry, `lastCooked`, filtre og lokale Registry-overstyringer lagres i eksisterende `app_state.meta`, og bare etter en eksplisitt brukerhandling.
- Oppskriftsdata skrives kun når brukeren velger å lagre importforhåndsvisningen.

## Ingredienskategorisering

Serveren bruker den sentrale Ingredient Registry først. En liten generell heuristikk korrigerer
krydder basert på funksjon og ordmønstre som `-pulver`, `-flak`, `-pepper`, `-krydder` og
`-masala`. AI-prompten har samme prioriterte regel. Brukeren kan alltid korrigere kategori i
forhåndsvisningen før lagring.

## Næringsestimat

AI-parseren estimerer protein, kalorier, fett, karbohydrater og fiber per porsjon. Manuelle
lagringer uten et eksisterende estimat bruker `/api/nutrition`. Verdiene er omtrentlige og
lagres på oppskriften slik at de ikke beregnes på nytt ved visning eller sortering.

## Pantry

Pantry-elementer har `zone` (`pantry`, `fridge`, `freezer`) fra første versjon. Dette gjør at
kjøleskap, fryser og tørrlager senere kan få egne visninger uten endring av datamodellen.
Automatisk overføring fra avkrysset handleliste er bevisst ikke aktivert.
