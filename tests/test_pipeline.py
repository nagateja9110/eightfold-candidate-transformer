import json

from main import load_config, main, run_pipeline


class TestEndToEndPipeline:
    def test_default_config_end_to_end(self):
        config = load_config("config/default.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)

        assert len(results) == 2
        c001 = next(r for r in results if r["candidate_id"] == "C001")

        # Merged from both CSV rows + GitHub
        assert c001["full_name"] == "John Doe"
        assert "john.doe@example.com" in c001["emails"]
        assert "jdoe@personal.com" in c001["emails"]
        assert c001["phones"] == ["+14155552671"]

        skill_names = {s["name"] for s in c001["skills"]}
        assert "python" in skill_names

        assert len(c001["provenance"]) > 0
        assert 0.0 <= c001["overall_confidence"] <= 1.0

    def test_custom_config_end_to_end(self):
        config = load_config("config/custom.json")
        results = run_pipeline("data/sample_recruiter.csv", "data/sample_github.json", config)

        assert len(results) == 2
        c001_result = next(r for r in results if r["full_name"] == "John Doe")

        assert c001_result["primary_email"] == "john.doe@example.com"
        assert c001_result["phone"] == "+14155552671"
        assert "python" in c001_result["skills"]
        assert "provenance" not in c001_result  # include_provenance: false in custom.json

    def test_missing_source_file_degrades_gracefully(self):
        config = load_config("config/default.json")
        results = run_pipeline("data/does_not_exist.csv", "data/sample_github.json", config)

        # CSV source missing -> skipped with a warning, GitHub-only data still produces profiles
        assert len(results) == 2

    def test_no_sources_returns_empty(self):
        config = load_config("config/default.json")
        results = run_pipeline(None, None, config)
        assert results == []


class TestCLI:
    def test_cli_writes_schema_valid_json(self, tmp_path):
        output_path = tmp_path / "profile.json"
        exit_code = main(
            [
                "--recruiter-csv",
                "data/sample_recruiter.csv",
                "--github-json",
                "data/sample_github.json",
                "--config",
                "config/default.json",
                "--output",
                str(output_path),
            ]
        )

        assert exit_code == 0
        assert output_path.exists()

        data = json.loads(output_path.read_text())
        assert len(data) == 2
        assert {p["candidate_id"] for p in data} == {"C001", "C002"}

    def test_cli_requires_at_least_one_source(self):
        exit_code = main(["--config", "config/default.json", "--output", "/tmp/unused.json"])
        assert exit_code == 1
