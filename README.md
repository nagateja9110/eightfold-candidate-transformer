# Multi-Source Candidate Data Transformer

Merges candidate data from a structured source (recruiter CSV) and an
unstructured source (GitHub API) into one canonical, deduplicated profile —
with provenance, confidence scoring, and a runtime-configurable output shape.

## Pipeline

```
extract -> normalize -> merge (match + resolve conflicts) -> project (config) -> validate -> write
```

- **Extract** ([pipeline/extractors.py](pipeline/extractors.py)) — `CSVExtractor` / `GitHubExtractor` read raw files into `RawSource` envelopes. Missing/malformed files are logged and skipped, never crash the run.
- **Normalize** ([pipeline/normalizers.py](pipeline/normalizers.py)) — pure functions for phone (E.164 via `phonenumbers`), name, location (city/region/ISO-3166 country), skill (canonical name), date (YYYY-MM), email.
- **Merge** ([pipeline/merger.py](pipeline/merger.py)) — groups raw sources into one candidate via email -> phone -> name+location matching (not a shared ID), then resolves each field with a 5-rule confidence policy (full agreement / majority / trust-based conflict / single-source / no data) and builds field-level provenance.
- **Project** ([pipeline/projector.py](pipeline/projector.py)) — reshapes the canonical profile into any custom JSON shape per a runtime `OutputConfig` (field selection, `from`-path remapping, normalization, `on_missing` policy), without mutating the canonical record.
- **Validate** ([pipeline/validator.py](pipeline/validator.py)) — checks the projected output for required fields, type correctness, and that every populated value traces back to a provenance entry (no invented data).

## Install

```bash
cd eightfold-transformer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the CLI

Default schema (all canonical fields, with provenance + confidence):

```bash
python main.py \
  --recruiter-csv data/sample_recruiter.csv \
  --github-json data/sample_github.json \
  --config config/default.json \
  --output output/profile_default.json
```

Custom schema (subset + remapped fields, e.g. `primary_email`, E.164 `phone`, canonical `skills`):

```bash
python main.py \
  --recruiter-csv data/sample_recruiter.csv \
  --github-json data/sample_github.json \
  --config config/custom.json \
  --output output/profile_custom.json
```

Either `--recruiter-csv` or `--github-json` may be omitted if you only have one source available; at least one is required.

## Run the tests

```bash
pytest -v
```

101 tests across extractors, normalizers, merger, projector, validator, and an end-to-end CLI test.

## Sample output

The output produced by the two commands above on the sample inputs is checked into
[output/profile_default.json](output/profile_default.json) and
[output/profile_custom.json](output/profile_custom.json).

## Demo video

~2 min walkthrough: default + custom config runs, one design decision, one edge case.
See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the script.

**Video:** [Watch on Google Drive](https://drive.google.com/file/d/1xxu197QqMFTl1g5hxZ19Sr4-nT8UwQCT/view?usp=sharing)

## Output config format

```json
{
  "fields": [
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```

- `path` — the output key. `from` — optional dotted path into the canonical profile (`a.b`, `a[0]`, `a[].b` to map a field across a list); defaults to `path` if omitted.
- `normalize` — `E164` (phone) or `canonical` (skill name).
- `on_missing` — `null` keeps the key with a `null` value, `omit` drops the key, `error` raises for any missing field (a `required: true` field always raises regardless of this setting).

## Assumptions & descoped

- GitHub source extracts `name, email, bio, location, company, blog, languages` only (no `login`/`public_repos`), so `links.github` is never populated from GitHub in this implementation — only `links.portfolio` (from `blog`).
- No source in scope provides structured education data or experience dates, so `education` is always `[]` and `experience[].start/end/summary` are always `null` — left null rather than invented.
- Year-only dates (`"2022"`) normalize to `"2022-01"` (documented default-to-January choice for YYYY-MM granularity), not left as a bare year.
- "Circular config reference" detection: this architecture has fields resolve only from the canonical profile, never from each other, so a true cycle can't arise; the projector instead rejects configs with duplicate output paths, the closest realistic misconfiguration.
- Candidate matching prioritizes email -> phone -> name+city; it does not do fuzzy/typo-tolerant name matching.
