import pytest

from models.schemas import (
    CanonicalProfile,
    Links,
    Location,
    OutputConfig,
    Provenance,
    Skill,
    SourceType,
)
from pipeline.projector import ProjectionError, project, resolve_path


def make_profile() -> CanonicalProfile:
    return CanonicalProfile(
        candidate_id="C001",
        full_name="John Doe",
        emails=["john.doe@example.com", "jdoe@personal.com"],
        phones=["+14155552671"],
        location=Location(city="San Francisco", region="CA", country="US"),
        links=Links(github=None, linkedin=None, portfolio="https://johndoe.dev", other=[]),
        headline="Software engineer passionate about Python and ML",
        years_experience=None,
        skills=[
            Skill(name="python", confidence=0.7, sources=[SourceType.GITHUB_API]),
            Skill(name="javascript", confidence=0.6, sources=[SourceType.GITHUB_API]),
        ],
        experience=[],
        education=[],
        provenance=[Provenance(field="full_name", source=SourceType.RECRUITER_CSV, method="merged")],
        overall_confidence=0.75,
    )


class TestResolvePath:
    def test_simple_key(self):
        data = {"full_name": "John Doe"}
        assert resolve_path(data, "full_name") == "John Doe"

    def test_array_index(self):
        data = {"emails": ["a@x.com", "b@x.com"]}
        assert resolve_path(data, "emails[0]") == "a@x.com"

    def test_array_index_out_of_range_returns_none(self):
        data = {"emails": ["a@x.com"]}
        assert resolve_path(data, "emails[5]") is None

    def test_nested_dot_path(self):
        data = {"links": {"github": "https://github.com/x"}}
        assert resolve_path(data, "links.github") == "https://github.com/x"

    def test_map_over_list(self):
        data = {"skills": [{"name": "python"}, {"name": "go"}]}
        assert resolve_path(data, "skills[].name") == ["python", "go"]

    def test_missing_key_returns_none(self):
        assert resolve_path({}, "full_name") is None


class TestProject:
    def test_default_style_config_selects_fields(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[
                {"path": "full_name", "type": "string", "required": True},
                {"path": "emails", "type": "string[]"},
            ],
            include_confidence=True,
            include_provenance=False,
        )

        result = project(profile, config)

        assert result["full_name"] == "John Doe"
        assert result["emails"] == ["john.doe@example.com", "jdoe@personal.com"]
        assert result["overall_confidence"] == 0.75
        assert "provenance" not in result
        assert "headline" not in result  # not requested -> excluded entirely

    def test_remap_with_from_and_array_index(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[
                {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
            ],
            include_confidence=False,
            include_provenance=False,
        )

        result = project(profile, config)
        assert result == {"primary_email": "john.doe@example.com"}

    def test_e164_normalize_on_already_normalized_phone(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"}],
            include_confidence=False,
        )

        result = project(profile, config)
        assert result["phone"] == "+14155552671"

    def test_skills_map_with_canonical_normalize(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "skill_names", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}],
            include_confidence=False,
        )

        result = project(profile, config)
        assert result["skill_names"] == ["python", "javascript"]

    def test_missing_optional_field_with_on_missing_null(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "github_url", "from": "links.github", "type": "string", "required": False}],
            on_missing="null",
            include_confidence=False,
        )

        result = project(profile, config)
        assert result["github_url"] is None

    def test_missing_optional_field_with_on_missing_omit(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "github_url", "from": "links.github", "type": "string", "required": False}],
            on_missing="omit",
            include_confidence=False,
        )

        result = project(profile, config)
        assert "github_url" not in result

    def test_missing_required_field_raises_regardless_of_on_missing(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "github_url", "from": "links.github", "type": "string", "required": True}],
            on_missing="omit",
            include_confidence=False,
        )

        with pytest.raises(ProjectionError):
            project(profile, config)

    def test_on_missing_error_raises_for_any_missing_field(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "github_url", "from": "links.github", "type": "string", "required": False}],
            on_missing="error",
            include_confidence=False,
        )

        with pytest.raises(ProjectionError):
            project(profile, config)

    def test_include_provenance_toggle(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "full_name", "type": "string"}],
            include_confidence=False,
            include_provenance=True,
        )

        result = project(profile, config)
        assert "provenance" in result
        assert result["provenance"][0]["field"] == "full_name"

    def test_does_not_mutate_canonical_profile(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}],
            include_confidence=False,
            include_provenance=False,
        )

        project(profile, config)

        assert profile.skills[0].name == "python"  # unchanged Skill objects, not strings
        assert isinstance(profile.skills[0], Skill)

    def test_string_to_number_coercion(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "confidence_str", "from": "overall_confidence", "type": "number"}],
            include_confidence=False,
            include_provenance=False,
        )

        result = project(profile, config)
        assert result["confidence_str"] == 0.75

    def test_type_mismatch_raises_for_non_numeric_string(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "full_name_as_number", "from": "full_name", "type": "number"}],
            include_confidence=False,
            include_provenance=False,
        )

        with pytest.raises(ProjectionError):
            project(profile, config)

    def test_type_mismatch_raises_for_scalar_where_list_expected(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "full_name", "type": "string[]"}],
            include_confidence=False,
            include_provenance=False,
        )

        with pytest.raises(ProjectionError):
            project(profile, config)

    def test_nonexistent_path_resolves_to_none_and_respects_on_missing(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[{"path": "bogus", "from": "totally.fake.path[0]", "type": "string", "required": False}],
            on_missing="null",
            include_confidence=False,
            include_provenance=False,
        )

        result = project(profile, config)
        assert result == {"bogus": None}

    def test_duplicate_output_path_in_config_raises(self):
        profile = make_profile()
        config = OutputConfig(
            fields=[
                {"path": "name", "from": "full_name", "type": "string"},
                {"path": "name", "from": "headline", "type": "string"},
            ],
            include_confidence=False,
            include_provenance=False,
        )

        with pytest.raises(ProjectionError):
            project(profile, config)
