"""Тесты version.py: parse_version и числовое semver-сравнение."""
from version import __version__, parse_version


def test_version_constant():
    assert __version__ == "1.10.0"


def test_parse_version_valid():
    assert parse_version("1.10.0") == (1, 10, 0)
    assert parse_version("1.9.1") == (1, 9, 1)
    assert parse_version("0.0.0") == (0, 0, 0)
    assert parse_version("2.0.0") == (2, 0, 0)


def test_numeric_comparison_1_10_0_newer_than_1_9_1():
    assert parse_version("1.10.0") > parse_version("1.9.1")


def test_numeric_comparison_1_10_0_newer_than_1_9_0():
    assert parse_version("1.10.0") > parse_version("1.9.0")


def test_numeric_comparison_equal_not_newer():
    assert not (parse_version("1.10.0") > parse_version("1.10.0"))


def test_numeric_comparison_older_not_newer():
    assert not (parse_version("1.9.1") > parse_version("1.10.0"))


def test_invalid_string_does_not_raise():
    result = parse_version("not_a_version")
    assert isinstance(result, tuple)
    assert len(result) == 3


def test_invalid_string_treated_as_old():
    assert parse_version("not_a_version") < parse_version("1.10.0")


def test_empty_string_does_not_raise():
    result = parse_version("")
    assert isinstance(result, tuple)


def test_partial_version_does_not_raise():
    result = parse_version("1.2")
    assert isinstance(result, tuple)
    assert len(result) == 3


def test_partial_version_treated_as_old():
    assert parse_version("1.2") < parse_version("1.2.3")
