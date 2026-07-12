# Scripts

This directory is reserved for development, validation, and maintenance scripts.

Scripts must not require machine-local secrets. If a script needs
environment-specific configuration, document the required variables and
keep examples separate from real credentials.

## Rogue Source Investigation

`inventory_rogue_source.py` inventories a Rogue source tree without
modifying it:

```powershell
python scripts/inventory_rogue_source.py C:\path\to\rogue `
  --json-output C:\tmp\rogue-inventory.json `
  --csv-output C:\tmp\rogue-inventory.csv
```

`compare_rogue_trees.py` compares two Rogue source trees by path,
SHA-256, and normalized text SHA-256:

```powershell
python scripts/compare_rogue_trees.py C:\path\to\baseline C:\path\to\local `
  --json-output C:\tmp\compare.json `
  --changed-csv-output C:\tmp\changed.csv
```

These scripts are for evidence generation only. They must not be used
to copy Rogue source into this repository.

## Generic Source Investigation

`hash_tree.py` records file sizes, per-file SHA-256 values, and a
project-local tree manifest hash:

```powershell
python scripts/hash_tree.py C:\path\to\source `
  --json-output C:\tmp\hash-tree.json `
  --csv-output C:\tmp\hash-tree.csv
```

`check_source_completeness.py` checks required files and Makefile-style
source lists:

```powershell
python scripts/check_source_completeness.py C:\path\to\source `
  --required LICENSE.TXT `
  --required Makefile.in `
  --required configure `
  --required new_level.c
```

`compare_source_tree.py` compares two trees by path, SHA-256, and
normalized text SHA-256:

```powershell
python scripts/compare_source_tree.py C:\path\to\golden C:\path\to\local `
  --json-output C:\tmp\compare.json `
  --changed-csv-output C:\tmp\changed.csv
```
