from models.schemas import CanonicalProfile, OutputConfig, Provenance, SourceType
from pipeline.validator import validate


def make_profile(**overrides) -> CanonicalProfile:
    defaults = dict(
        candidate_id="C001",
        full_name="John Doe",
        emails=["john@example.com"],
        provenance=[
            Provenance(field="full_name", source=SourceType.RECRUITER_CSV, method="normalized"),
            Provenance(field="emails", source=SourceType.RECRUITER_CSV, method="normalized"),
        ],
        overall_confidence=0.8,
    )
    defaults.update(overrides)
    return CanonicalProfile(**defaults)


class TestValidate:
    def test_valid_result_passes(self):
        profile = make_profile()
        config = OutputConfig(fields=[{"path": "full_name", "type": "string", "required": True}])
        result = {"full_name": "John Doe"}

        is_valid, errors = validate(profile, config, result)
        assert is_valid
        assert errors == []

    def test_missing_required_field_fails(self):
        profile = make_profile()
        config = OutputConfig(fields=[{"path": "headline", "type": "string", "required": True}])
        result = {}

        is_valid, errors = validate(profile, config, result)
        assert not is_valid
        assert "headline" in errors[0]

    def test_type_mismatch_fails(self):
        profile = make_profile()
        config = OutputConfig(fields=[{"path": "full_name", "type": "number"}])
        result = {"full_name": "John Doe"}

        is_valid, errors = validate(profile, config, result)
        assert not is_valid
        assert "type" in errors[0]

    def test_value_without_provenance_flagged_as_possible_invented_data(self):
        profile = make_profile(provenance=[])  # no provenance backing full_name at all
        config = OutputConfig(fields=[{"path": "full_name", "type": "string"}])
        result = {"full_name": "John Doe"}

        is_valid, errors = validate(profile, config, result)
        assert not is_valid
        assert "invented" in errors[0]

    def test_candidate_id_exempt_from_provenance_check(self):
        profile = make_profile(provenance=[])  # candidate_id had no provenance entry
        config = OutputConfig(fields=[{"path": "candidate_id", "type": "string"}])
        result = {"candidate_id": "C001"}

        is_valid, errors = validate(profile, config, result)
        assert is_valid

    def test_remapped_field_checks_provenance_of_base_canonical_field(self):
        profile = make_profile()
        config = OutputConfig(fields=[{"path": "primary_email", "from": "emails[0]", "type": "string"}])
        result = {"primary_email": "john@example.com"}

        is_valid, errors = validate(profile, config, result)
        assert is_valid

    def test_null_optional_field_does_not_fail(self):
        profile = make_profile()
        config = OutputConfig(fields=[{"path": "headline", "type": "string", "required": False}])
        result = {"headline": None}

        is_valid, errors = validate(profile, config, result)
        assert is_valid

    def test_empty_list_does_not_require_provenance(self):
        profile = make_profile(provenance=[])  # education never has any source/provenance
        config = OutputConfig(fields=[{"path": "education", "type": "object"}])
        result = {"education": []}

        is_valid, errors = validate(profile, config, result)
        assert is_valid

    def test_all_null_object_does_not_require_provenance(self):
        profile = make_profile(provenance=[])  # links never populated
        config = OutputConfig(fields=[{"path": "links", "type": "object"}])
        result = {"links": {"linkedin": None, "github": None, "portfolio": None, "other": []}}

        is_valid, errors = validate(profile, config, result)
        assert is_valid
