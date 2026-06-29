import pytest

from pipeline.normalizers import (
    normalize_date,
    normalize_email,
    normalize_location,
    normalize_name,
    normalize_phone,
    normalize_skill,
)


class TestNormalizePhone:
    def test_us_local_format(self):
        assert normalize_phone("(415) 555-2671") == "+14155552671"

    def test_us_dashed_format(self):
        assert normalize_phone("415-555-2671") == "+14155552671"

    def test_india_with_country_code(self):
        assert normalize_phone("+91 98765 43210") == "+919876543210"

    def test_none_input(self):
        assert normalize_phone(None) is None

    def test_empty_string(self):
        assert normalize_phone("") is None

    def test_unparseable_returns_none(self):
        assert normalize_phone("not-a-phone") is None

    def test_too_short_returns_none(self):
        assert normalize_phone("123") is None


class TestNormalizeName:
    def test_strips_whitespace(self):
        assert normalize_name("  John   Doe  ") == "John Doe"

    def test_title_cases(self):
        assert normalize_name("john doe") == "John Doe"

    def test_keeps_initials_as_is(self):
        assert normalize_name("J. Doe") == "J. Doe"

    def test_none_input(self):
        assert normalize_name(None) is None

    def test_empty_string(self):
        assert normalize_name("   ") is None


class TestNormalizeLocation:
    def test_city_region_country(self):
        loc = normalize_location("San Francisco, CA, USA")
        assert loc.city == "San Francisco"
        assert loc.region == "CA"
        assert loc.country == "US"

    def test_city_country_india(self):
        loc = normalize_location("Bangalore, India")
        assert loc.city == "Bangalore"
        assert loc.region is None
        assert loc.country == "IN"

    def test_city_region_no_country(self):
        loc = normalize_location("San Francisco, California")
        assert loc.city == "San Francisco"
        assert loc.region == "California"
        assert loc.country is None

    def test_city_only(self):
        loc = normalize_location("San Francisco")
        assert loc.city == "San Francisco"
        assert loc.region is None
        assert loc.country is None

    def test_none_input(self):
        loc = normalize_location(None)
        assert loc.city is None
        assert loc.country is None

    def test_empty_string(self):
        loc = normalize_location("")
        assert loc.city is None


class TestNormalizeSkill:
    def test_ml_maps_to_machine_learning(self):
        assert normalize_skill("ML") == "machine learning"

    def test_js_maps_to_javascript(self):
        assert normalize_skill("JS") == "javascript"

    def test_react_js_maps_to_react(self):
        assert normalize_skill("React.js") == "react"

    def test_unknown_skill_passthrough_lowercased(self):
        assert normalize_skill("Rust") == "rust"

    def test_none_input(self):
        assert normalize_skill(None) is None

    def test_empty_string(self):
        assert normalize_skill("") is None


class TestNormalizeDate:
    def test_year_month_passthrough(self):
        assert normalize_date("2022-06") == "2022-06"

    def test_month_name_year(self):
        assert normalize_date("June 2022") == "2022-06"

    def test_year_only_defaults_to_january(self):
        assert normalize_date("2022") == "2022-01"

    def test_none_input(self):
        assert normalize_date(None) is None

    def test_empty_string(self):
        assert normalize_date("") is None

    def test_garbage_returns_none(self):
        assert normalize_date("not a date") is None


class TestNormalizeEmail:
    def test_lowercases_and_strips(self):
        assert normalize_email("  John.Doe@Example.com  ") == "john.doe@example.com"

    def test_none_input(self):
        assert normalize_email(None) is None

    def test_empty_string(self):
        assert normalize_email("") is None
