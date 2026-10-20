# Dependency Conflict Predictor (MVP)

CX Linux includes an MVP pre-install dependency conflict predictor for package operations.

## What it checks

- **apt/dpkg path**
  - Reads installed package set from `dpkg-query`
  - Reads package metadata from `apt-cache show`
  - Flags likely `Conflicts`/`Breaks` against currently installed packages
  - Emits a confidence score per finding

- **pip path**
  - Parses requested pip constraints (e.g. `urllib3==2.0.0`)
  - Compares against current Python environment metadata
  - Flags direct constraint mismatches and reverse dependency risks

- **Resolution suggestions**
  - Ranked by safety (higher first)
  - Includes dry-run and isolation-first guidance

## CLI usage

```bash
python -m cx.dependency_conflict_predictor --apt nginx postgresql --pip "urllib3==2.1.0"
```

JSON output:

```bash
python -m cx.dependency_conflict_predictor --apt nginx --json
```

Exit code behavior:

- `0`: no high-confidence conflict detected
- `2`: at least one high-confidence conflict found (`confidence >= 0.85`)
