from main import format_name, truncate

def test_format_full_name():
    assert format_name("John", "Doe") == "John Doe"

def test_format_with_middle():
    assert format_name("John", "Doe", middle="Quincy") == "John Q. Doe"

def test_format_with_title():
    assert format_name("John", "Doe", title="Dr.") == "Dr. John Doe"

def test_truncate_short():
    assert truncate("hi", 10) == "hi"

def test_truncate_long_exact():
    result = truncate("hello world", 5)
    assert result == "he..."
    assert len(result) <= 5
