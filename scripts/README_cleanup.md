# Engangsrydd av oppskrifter

Kjør fra prosjektmappen på Mac:

```bash
python3 scripts/cleanup_recipes_with_ai.py --dry-run
```

Hvis det ser greit ut:

```bash
python3 scripts/cleanup_recipes_with_ai.py --apply
```

Mer grundig med AI:

```bash
python3 scripts/cleanup_recipes_with_ai.py --ai --dry-run
python3 scripts/cleanup_recipes_with_ai.py --ai --apply
```

Tips: test først på noen få:

```bash
python3 scripts/cleanup_recipes_with_ai.py --ai --dry-run --limit 10
```
