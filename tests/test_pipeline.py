import json

from main import load_config, main, run_pipeline

ALL_CANDIDATE_IDS = {"C001", "C002", "C003", "C004", "C005", "C006"}


class TestEndToEndPipeline:
    def test_produces_all_six_candidates(self):
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        assert len(results) == 6
        assert {r["candidate_id"] for r in results} == ALL_CANDIDATE_IDS

    def test_c001_multi_source_merge(self):
        """C001: 3 sources (2 CSV rows + GitHub). Name conflict resolved by majority."""
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        c001 = next(r for r in results if r["candidate_id"] == "C001")

        assert c001["full_name"] == "John Doe"        # majority over "J. Doe"
        assert "john.doe@example.com" in c001["emails"]
        assert "jdoe@personal.com" in c001["emails"]  # union of both CSV rows
        assert c001["phones"] == ["+14155552671"]      # two formats → one E.164
        assert {s["name"] for s in c001["skills"]} >= {"python", "javascript", "go"}
        assert len(c001["provenance"]) > 0
        assert 0.0 <= c001["overall_confidence"] <= 1.0

    def test_c003_csv_only_candidate(self):
        """C003: no GitHub profile → skills empty, all provenance methods are single-source."""
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        c003 = next(r for r in results if r["candidate_id"] == "C003")

        assert c003["full_name"] == "Bob Chen"
        assert c003["skills"] == []                           # no GitHub = no skills
        assert c003["phones"] == ["+16503001234"]             # normalized from 650-300-1234
        provenance_methods = {p["method"] for p in c003["provenance"]}
        assert "merged" not in provenance_methods             # only 1 source → never merged

    def test_c004_github_only_candidate(self):
        """C004: no CSV row → no phone, location parsed from 'Berlin, Germany'."""
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        c004 = next(r for r in results if r["candidate_id"] == "C004")

        assert c004["full_name"] == "Maria Garcia"
        assert c004["phones"] == []                           # GitHub never has phone
        assert c004["location"]["city"] == "Berlin"
        assert c004["location"]["country"] == "DE"            # "Germany" → ISO-3166
        assert c004["links"]["portfolio"] == "https://maria.design"

    def test_c005_conflict_resolution_and_two_companies(self):
        """C005: headline conflict (CSV vs GitHub bio) resolved by trust; two companies."""
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        c005 = next(r for r in results if r["candidate_id"] == "C005")

        # CSV headline wins (trust 0.8 > 0.6) when sources conflict
        assert c005["headline"] == "Senior Engineer"
        assert c005["phones"] == ["+447911123456"]            # UK mobile E.164

        # DataCorp (CSV) and @bigco (GitHub) normalise to different keys → 2 experience entries
        companies = {e["company"] for e in c005["experience"]}
        assert len(companies) == 2
        assert "DataCorp" in companies

    def test_c006_unparseable_phone_becomes_null(self):
        """C006: 'NOT-A-PHONE' → phones empty, doesn't crash; ML skills pass through."""
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)
        c006 = next(r for r in results if r["candidate_id"] == "C006")

        assert c006["phones"] == []                           # NOT-A-PHONE → null, omitted from union
        skill_names = {s["name"] for s in c006["skills"]}
        assert "python" in skill_names
        assert "tensorflow" in skill_names                    # unknown skill → canonical lowercase

    def test_custom_config_end_to_end(self):
        config = load_config("config/custom.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)

        assert len(results) == 6
        c001 = next(r for r in results if r["full_name"] == "John Doe")
        assert c001["primary_email"] == "john.doe@example.com"
        assert c001["phone"] == "+14155552671"
        assert "python" in c001["skills"]
        assert "provenance" not in c001                       # include_provenance: false

    def test_missing_source_file_degrades_gracefully(self):
        """Missing CSV → skipped with a warning; GitHub-only data still runs to completion."""
        config = load_config("config/default.json")
        results = run_pipeline("data/does_not_exist.csv", "data/sample_github.json", config)
        # 5 GitHub profiles (C001,C002,C004,C005,C006), no C003 since it's CSV-only
        assert len(results) == 5

    def test_no_sources_returns_empty(self):
        config = load_config("config/default.json")
        assert run_pipeline(None, None, config) == []


class TestCLI:
    def test_cli_writes_schema_valid_json(self, tmp_path):
        output_path = tmp_path / "profile.json"
        exit_code = main([
            "--recruiter-csv", "data/sample_recruiter.csv",
            "--github-json", "data/sample_github.json",
            "--config", "config/default.json",
            "--output", str(output_path),
        ])

        assert exit_code == 0
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert len(data) == 6
        assert {p["candidate_id"] for p in data} == ALL_CANDIDATE_IDS

    def test_cli_requires_at_least_one_source(self):
        exit_code = main(["--config", "config/default.json", "--output", "/tmp/unused.json"])
        assert exit_code == 1
