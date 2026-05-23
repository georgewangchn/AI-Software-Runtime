import pytest
from main import parse_args, process

def test_parse_valid_args():
    args = parse_args(["--input", "data.txt", "--verbose"])
    assert args is not None
    assert args.input == "data.txt"
    assert args.verbose is True

def test_parse_with_output():
    args = parse_args(["--input", "data.txt", "--output", "out.txt"])
    assert args is not None
    result = process(args)
    assert result is not None
    assert "output" in result
    assert result["output"] == "out.txt"

def test_reject_negative_count():
    args = parse_args(["--input", "data.txt", "--count", "-1"])
    assert args is None

def test_accept_zero_count():
    args = parse_args(["--input", "data.txt", "--count", "0"])
    assert args is not None
