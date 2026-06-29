from models.schemas import Location, SourceType
from pipeline.extractors import CSVExtractor, GitHubExtractor
from pipeline.merger import _ExtractedFields, _merge_skills, merge


def load_sample_sources():
    csv_sources = CSVExtractor().extract("data/sample_recruiter.csv")
    github_sources = GitHubExtractor().extract("data/sample_github.json")
    return csv_sources + github_sources


def make_extracted(source_type, trust_score, skills):
    return _ExtractedFields(
        candidate_id=None,
        full_name=None,
        email=None,
        phone=None,
        location=Location(),
        headline=None,
        company=None,
        title=None,
        skills=skills,
        github_url=None,
        portfolio_url=None,
        source_type=source_type,
        trust_score=trust_score,
    )


class TestMerge:
    def test_produces_one_profile_per_candidate(self):
        profiles = merge(load_sample_sources())
        # 3 CSV rows (2 distinct people, C001 duplicated) + 2 GitHub profiles -> 2 candidates
        assert len(profiles) == 2

    def test_c001_matches_across_email_phone_and_github(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        # Both CSV emails + GitHub's matching email contribute, deduped.
        assert "john.doe@example.com" in c001.emails
        assert "jdoe@personal.com" in c001.emails
        # Both CSV phone formats normalize to the same E.164 number.
        assert c001.phones == ["+14155552671"]

    def test_conflicting_name_resolved_by_majority(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        # "John Doe" appears from CSV row 1 (trust .8) and GitHub (trust .6);
        # "J. Doe" appears once from CSV row 2 (trust .8). Majority wins.
        assert c001.full_name == "John Doe"

    def test_conflict_confidence_reflects_majority_rule(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        name_provenance = [p for p in c001.provenance if p.field == "full_name"]
        assert len(name_provenance) == 2  # CSV + GITHUB both contributed to the winning value
        assert {p.source for p in name_provenance} == {SourceType.RECRUITER_CSV, SourceType.GITHUB_API}

    def test_skills_only_come_from_github(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        skill_names = {s.name for s in c001.skills}
        assert skill_names == {"python", "javascript", "go", "machine learning"}
        assert all(s.sources == [SourceType.GITHUB_API] for s in c001.skills)

    def test_experience_merges_csv_company_variants(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        # Two CSV rows ("Acme Inc") + GitHub ("@acme-inc") normalize to the same company.
        assert len(c001.experience) == 1
        assert c001.experience[0].company == "Acme Inc"  # highest-trust (CSV) display value wins
        assert c001.experience[0].start is None  # no date data available in scope

    def test_provenance_is_populated(self):
        profiles = merge(load_sample_sources())
        c001 = next(p for p in profiles if p.candidate_id == "C001")

        assert len(c001.provenance) > 0
        fields_with_provenance = {p.field for p in c001.provenance}
        assert "full_name" in fields_with_provenance
        assert "emails" in fields_with_provenance
        assert "skills" in fields_with_provenance

    def test_overall_confidence_is_between_zero_and_one(self):
        profiles = merge(load_sample_sources())
        for profile in profiles:
            assert 0.0 <= profile.overall_confidence <= 1.0

    def test_c002_single_source_per_field_gets_single_source_confidence(self):
        profiles = merge(load_sample_sources())
        c002 = next(p for p in profiles if p.candidate_id == "C002")

        # Jane's name agrees exactly across CSV and GitHub -> full agreement, not conflict.
        assert c002.full_name == "Jane Smith"
        name_provenance = [p for p in c002.provenance if p.field == "full_name"]
        assert len(name_provenance) == 2

    def test_empty_input_returns_empty_list(self):
        assert merge([]) == []

    def test_matching_works_without_relying_on_candidate_id(self):
        """Grouping must succeed via email/phone matching alone, not the candidate_id field."""
        csv_sources = CSVExtractor().extract("data/sample_recruiter.csv")
        github_sources = GitHubExtractor().extract("data/sample_github.json")

        for source in csv_sources + github_sources:
            source.raw_data.pop("candidate_id", None)

        profiles = merge(csv_sources + github_sources)
        assert len(profiles) == 2
        names = {p.full_name for p in profiles}
        assert names == {"John Doe", "Jane Smith"}


class TestMergeSkillsDedup:
    """Sample data only exercises single-source skills (CSV extracts none), so this
    test directly drives the multi-source dedup/corroboration path."""

    def test_skill_from_two_sources_dedupes_and_merges_source_arrays(self):
        group = [
            make_extracted(SourceType.RECRUITER_CSV, 0.8, ["python"]),
            make_extracted(SourceType.GITHUB_API, 0.6, ["python", "go"]),
        ]

        skills, sources = _merge_skills(group)

        skill_by_name = {s.name: s for s in skills}
        assert set(skill_by_name) == {"python", "go"}

        python_skill = skill_by_name["python"]
        assert set(python_skill.sources) == {SourceType.RECRUITER_CSV, SourceType.GITHUB_API}
        # avg_trust = (0.8 + 0.6) / 2 = 0.7, + 0.1 corroboration bonus for 2 occurrences = 0.8
        assert python_skill.confidence == 0.8

        go_skill = skill_by_name["go"]
        assert go_skill.sources == [SourceType.GITHUB_API]
        assert go_skill.confidence == 0.6

        assert set(sources) == {SourceType.RECRUITER_CSV, SourceType.GITHUB_API}
