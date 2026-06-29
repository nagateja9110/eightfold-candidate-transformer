# Demo Script (~2 minutes)

Record terminal + a quick look at the JSON output. Have these two terminal tabs ready:
1. `eightfold-transformer/` with `.venv` activated
2. A text editor / `cat` for showing JSON output

---

## 0:00–0:15 — Intro (talk over a blank terminal)

"This is the Multi-Source Candidate Data Transformer for the Eightfold assignment. It merges
a recruiter CSV and GitHub profile data into one canonical candidate record, then projects
it into whatever output shape a runtime config asks for."

## 0:15–0:50 — Default config run

```bash
python main.py \
  --recruiter-csv data/sample_recruiter.csv \
  --github-json data/sample_github.json \
  --config config/default.json \
  --output output/default.json
```

Point out the log lines as they print:
- "Extracted 3 records from CSV" / "2 profiles from GitHub" — two independent sources.
- "Merged 5 raw sources into 2 candidate profiles" — **this is the key moment**: the CSV has
  3 rows (John Doe appears twice with a different name spelling and phone format) plus 2
  GitHub profiles, but it collapses to exactly 2 people.

Then open `output/default.json` and point at John Doe's (`C001`) record:
- `emails` has both his work and personal email, unioned from different rows.
- `phones` has one number — `(415) 555-2671` and `415-555-2671` normalized to the same E.164
  string and deduped.
- `full_name: "John Doe"` — note `provenance` shows this came from both `RECRUITER_CSV` and
  `GITHUB_API`, because one CSV row had "J. Doe" but two sources agreed on "John Doe", so
  majority won.
- `skills` populated only from GitHub (`sources: ["GITHUB_API"]`) — CSV doesn't carry skills.
- `overall_confidence` is a real number, not hand-waved.

## 0:50–1:20 — Custom config run

```bash
python main.py \
  --recruiter-csv data/sample_recruiter.csv \
  --github-json data/sample_github.json \
  --config config/custom.json \
  --output output/custom.json
```

Open `config/custom.json` briefly, then `output/custom.json`:
- Same underlying canonical profile, completely different shape: `primary_email` (remapped
  from `emails[0]`), `phone` forced through `E164` normalization, `skills` flattened from
  `skills[].name` and re-canonicalized, provenance turned off via `include_provenance: false`.
- "Same engine, no code changes — just a different JSON config."

## 1:20–1:45 — One design decision I'm proud of

Pick ONE, say it in your own words, e.g.:

> "Candidate matching doesn't rely on a shared candidate_id across sources — that's
> unrealistic in the real world. Instead it matches by normalized email, then falls back to
> phone, then name+city. I actually have a test that strips candidate_id out of every record
> entirely and confirms the merge still groups the right people together."

(Optionally run `pytest tests/test_merger.py -k candidate_id -v` live to show it passing.)

## 1:45–2:00 — One edge case handled

Pick ONE, e.g.:

> "Conflicting values get resolved by a confidence policy, not just 'last write wins' — full
> agreement across sources scores highest, a majority vote scores lower, and a real conflict
> falls back to whichever source has the higher trust score, CSV over GitHub here. Missing
> data — like education, which no source in scope provides — stays null instead of being
> invented, and the validator actually checks that every non-null field traces back to a
> provenance entry, so invented data would fail validation."

Close: "All 96 tests pass, README has full run instructions." Cut.

---

## Pre-recording checklist

- [ ] `source .venv/bin/activate` (or re-run `pip install -r requirements.txt` if recording on a fresh machine)
- [ ] `rm -rf output/*.json` so the run isn't silently reusing stale output
- [ ] Run both commands once *before* recording to confirm no surprises, then `rm -rf output/*.json` again
- [ ] Have `config/custom.json`, `output/default.json`, `output/custom.json` open in tabs ready to alt-tab to
- [ ] Terminal font size large enough to read on a recording
