import pytest
from main import is_leap_year, parse_date

def test_leap_year_divisible_by_4():
    assert is_leap_year(2024) is True
    assert is_leap_year(2023) is False

def test_leap_year_century_rule():
    assert is_leap_year(1900) is False
    assert is_leap_year(2000) is True

def test_parse_valid_date():
    assert parse_date("2024-02-29") == (2024, 2, 29)

def test_parse_invalid_leap_date():
    with pytest.raises(ValueError):
        parse_date("2023-02-29")

def test_parse_invalid_century_leap():
    with pytest.raises(ValueError):
        parse_date("1900-02-29")

def test_parse_valid_boundary():
    assert parse_date("2024-12-31") == (2024, 12, 31)
