import csv
import json

from models.schemas import SourceType
from pipeline.extractors import CSVExtractor, GitHubExtractor


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestCSVExtractor:
    def test_extracts_valid_rows(self, tmp_path):
        path = tmp_path / "recruiter.csv"
        write_csv(
            path,
            [
                {
                    "candidate_id": "C001",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "phone": "415-555-2671",
                    "current_company": "Acme Inc",
                    "title": "Software Engineer",
                    "location": "San Francisco, CA, USA",
                }
            ],
            fieldnames=["candidate_id", "name", "email", "phone", "current_company", "title", "location"],
        )

        sources = CSVExtractor().extract(path)

        assert len(sources) == 1
        assert sources[0].source_type == SourceType.RECRUITER_CSV
        assert sources[0].trust_score == 0.8
        assert sources[0].raw_data["candidate_id"] == "C001"
        assert sources[0].raw_data["name"] == "John Doe"

    def test_missing_file_returns_empty_list(self, tmp_path):
        sources = CSVExtractor().extract(tmp_path / "does_not_exist.csv")
        assert sources == []

    def test_missing_candidate_id_is_skipped(self, tmp_path):
        path = tmp_path / "recruiter.csv"
        write_csv(
            path,
            [{"candidate_id": "", "name": "No ID", "email": "", "phone": "", "current_company": "", "title": "", "location": ""}],
            fieldnames=["candidate_id", "name", "email", "phone", "current_company", "title", "location"],
        )

        sources = CSVExtractor().extract(path)
        assert sources == []

    def test_empty_values_become_none(self, tmp_path):
        path = tmp_path / "recruiter.csv"
        write_csv(
            path,
            [{"candidate_id": "C002", "name": "Jane", "email": "", "phone": "", "current_company": "", "title": "", "location": ""}],
            fieldnames=["candidate_id", "name", "email", "phone", "current_company", "title", "location"],
        )

        sources = CSVExtractor().extract(path)
        assert sources[0].raw_data["email"] is None
        assert sources[0].raw_data["phone"] is None

    def test_sample_recruiter_csv(self):
        sources = CSVExtractor().extract("data/sample_recruiter.csv")
        assert len(sources) == 3
        assert all(s.source_type == SourceType.RECRUITER_CSV for s in sources)

    def test_completely_empty_file_returns_empty_list(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("")

        sources = CSVExtractor().extract(path)
        assert sources == []

    def test_header_only_csv_returns_empty_list(self, tmp_path):
        path = tmp_path / "header_only.csv"
        path.write_text("candidate_id,name,email,phone,current_company,title,location\n")

        sources = CSVExtractor().extract(path)
        assert sources == []


class TestGitHubExtractor:
    def test_extracts_valid_profiles(self, tmp_path):
        path = tmp_path / "github.json"
        path.write_text(json.dumps({"C001": {"name": "John Doe", "email": "john@example.com", "bio": "Engineer"}}))

        sources = GitHubExtractor().extract(path)

        assert len(sources) == 1
        assert sources[0].source_type == SourceType.GITHUB_API
        assert sources[0].trust_score == 0.6
        assert sources[0].raw_data["candidate_id"] == "C001"
        assert sources[0].raw_data["name"] == "John Doe"

    def test_missing_file_returns_empty_list(self, tmp_path):
        sources = GitHubExtractor().extract(tmp_path / "missing.json")
        assert sources == []

    def test_malformed_json_returns_empty_list(self, tmp_path):
        path = tmp_path / "github.json"
        path.write_text("{not valid json")

        sources = GitHubExtractor().extract(path)
        assert sources == []

    def test_non_object_profile_is_skipped(self, tmp_path):
        path = tmp_path / "github.json"
        path.write_text(json.dumps({"C001": "not an object", "C002": {"name": "Jane"}}))

        sources = GitHubExtractor().extract(path)
        assert len(sources) == 1
        assert sources[0].raw_data["candidate_id"] == "C002"

    def test_null_profile_value_is_skipped(self, tmp_path):
        """A candidate whose JSON value is null (a 'missing' profile) is skipped, not crashed on."""
        path = tmp_path / "github.json"
        path.write_text(json.dumps({"C001": None, "C002": {"name": "Jane"}}))

        sources = GitHubExtractor().extract(path)
        assert len(sources) == 1
        assert sources[0].raw_data["candidate_id"] == "C002"

    def test_empty_json_object_returns_empty_list(self, tmp_path):
        path = tmp_path / "github.json"
        path.write_text("{}")

        sources = GitHubExtractor().extract(path)
        assert sources == []

    def test_missing_fields_become_none(self, tmp_path):
        path = tmp_path / "github.json"
        path.write_text(json.dumps({"C001": {"name": "John"}}))

        sources = GitHubExtractor().extract(path)
        assert sources[0].raw_data["email"] is None
        assert sources[0].raw_data["bio"] is None

    def test_sample_github_json(self):
        sources = GitHubExtractor().extract("data/sample_github.json")
        assert len(sources) == 2
        assert all(s.source_type == SourceType.GITHUB_API for s in sources)
