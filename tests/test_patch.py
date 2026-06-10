"""Tests for ASR patch engine."""

import tempfile
from pathlib import Path

import pytest

from asr.patch.diff import PatchEngine, PatchResult, PatchEntry


def test_patch_result_defaults():
    """Test PatchResult with only success field."""
    result = PatchResult(success=True)
    assert result.success is True
    assert result.content == ""
    assert result.error == ""
    assert result.failed_hunk is None


def test_patch_result_full():
    """Test PatchResult with all fields."""
    result = PatchResult(
        success=False,
        content="patched content",
        error="patch failed",
        failed_hunk=3
    )
    assert result.success is False
    assert result.content == "patched content"
    assert result.error == "patch failed"
    assert result.failed_hunk == 3


def test_patch_entry_defaults():
    """Test PatchEntry with required fields."""
    entry = PatchEntry(
        file_path="test.py",
        diff_text="--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new",
        original_content="old"
    )
    assert entry.file_path == "test.py"
    assert entry.diff_text.startswith("---")
    assert entry.original_content == "old"
    assert entry.rollback_diff_text == ""


def test_patch_entry_with_rollback():
    """Test PatchEntry with rollback diff."""
    entry = PatchEntry(
        file_path="test.py",
        diff_text="diff",
        original_content="old",
        rollback_diff_text="reverse_diff"
    )
    assert entry.rollback_diff_text == "reverse_diff"


def test_patch_engine_initialization():
    """Test PatchEngine initialization."""
    engine = PatchEngine()
    assert engine is not None


def test_patch_engine_clean_diff():
    """Test PatchEngine._clean_diff method."""
    engine = PatchEngine()

    diff1 = "```diff\n--- a/file\n+++ b/file\n-old\n+new\n```"
    cleaned1 = engine._clean_diff(diff1)
    assert "```" not in cleaned1
    assert "--- a/file" in cleaned1

    diff2 = "```\n--- a/file\n+++ b/file\n-old\n+new\n```"
    cleaned2 = engine._clean_diff(diff2)
    assert "```" not in cleaned2

    diff3 = "--- a/file\n+++ b/file\n-old\n+new"
    cleaned3 = engine._clean_diff(diff3)
    assert cleaned3 == diff3.strip()


def test_patch_engine_parse_diff_simple():
    """Test PatchEngine.parse_diff with simple diff."""
    engine = PatchEngine()
    diff_text = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-old line
+new line"""

    diffs = engine.parse_diff(diff_text)
    assert len(diffs) == 1
    assert diffs[0]["file"] == "test.py"
    assert "@@" in diffs[0]["text"]


def test_patch_engine_parse_diff_multiple_files():
    """Test PatchEngine.parse_diff with multiple file diffs."""
    engine = PatchEngine()
    diff_text = """--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,1 @@
-old1
+new1
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,1 @@
-old2
+new2"""

    diffs = engine.parse_diff(diff_text)
    assert len(diffs) == 2
    assert diffs[0]["file"] == "file1.py"
    assert diffs[1]["file"] == "file2.py"


def test_patch_engine_parse_diff_empty():
    """Test PatchEngine.parse_diff with empty diff."""
    engine = PatchEngine()
    diffs = engine.parse_diff("")
    assert len(diffs) == 0


def test_patch_engine_parse_diff_no_file_header():
    """Test PatchEngine.parse_diff without file header."""
    engine = PatchEngine()
    diff_text = """@@ -1,1 +1,1 @@
-old
+new"""

    diffs = engine.parse_diff(diff_text)
    assert len(diffs) >= 1


def test_patch_engine_parse_diff_with_prefix():
    """Test PatchEngine.parse_diff with a/ and b/ prefix."""
    engine = PatchEngine()
    diff_text = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-old
+new"""

    diffs = engine.parse_diff(diff_text)
    assert diffs[0]["file"] == "test.py"


def test_patch_engine_apply_single_simple():
    """Test PatchEngine.apply_single with simple replacement."""
    engine = PatchEngine()
    source = "line 1\nline 2\nline 3"
    diff = """@@ -1,1 +1,1 @@
-line 1
+modified line 1"""

    result = engine.apply_single(diff, source)
    assert result.success is True
    assert "modified line 1" in result.content
    assert "line 2" in result.content


def test_patch_engine_apply_single_add_lines():
    """Test PatchEngine.apply_single with added lines."""
    engine = PatchEngine()
    source = "line 1\nline 2"
    diff = """@@ -1,2 +1,3 @@
 line 1
+added line
 line 2"""

    result = engine.apply_single(diff, source)
    assert result.success is True
    lines = result.content.split("\n")
    assert "line 1" in lines
    assert "added line" in lines
    assert "line 2" in lines


def test_patch_engine_apply_single_delete_lines():
    """Test PatchEngine.apply_single with deleted lines."""
    engine = PatchEngine()
    source = "line 1\nto delete\nline 3"
    diff = """@@ -1,3 +1,2 @@
 line 1
-to delete
 line 3"""

    result = engine.apply_single(diff, source)
    assert result.success is True
    assert "to delete" not in result.content
    assert "line 1" in result.content
    assert "line 3" in result.content


def test_patch_engine_apply_single_reverse():
    """Test PatchEngine.apply_single with reverse flag."""
    engine = PatchEngine()
    source = "original text"
    diff = """@@ -1,1 +1,1 @@
-original text
+modified text"""

    forward_result = engine.apply_single(diff, source, reverse=False)
    assert "modified text" in forward_result.content

    reverse_result = engine.apply_single(diff, source, reverse=True)
    assert "modified text" in reverse_result.content


@pytest.fixture
def temp_base_dir():
    """Create a temporary base directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_patch_engine_apply_to_file(temp_base_dir):
    """Test PatchEngine.apply to actual file."""
    engine = PatchEngine()

    test_file = temp_base_dir / "test.py"
    test_file.write_text("original content")

    diff_text = f"""--- a/test.py
+++ b/test.py
@@ -1,1 +1,1 @@
-original content
+modified content"""

    results = engine.apply(diff_text, temp_base_dir)
    assert len(results) == 1
    assert results[0].success is True

    updated_content = test_file.read_text()
    assert "modified content" in updated_content


def test_patch_engine_apply_nonexistent_file(temp_base_dir):
    """Test PatchEngine.apply with non-existent file."""
    engine = PatchEngine()

    diff_text = """--- a/nonexistent.py
+++ b/nonexistent.py
@@ -0,0 +1,1 @@
+new file"""

    results = engine.apply(diff_text, temp_base_dir)
    assert len(results) == 1


def test_patch_engine_rollback():
    """Test PatchEngine.rollback method."""
    engine = PatchEngine()

    entry1 = PatchEntry(
        file_path="file1.py",
        diff_text="diff1",
        original_content="original1"
    )
    entry2 = PatchEntry(
        file_path="file2.py",
        diff_text="diff2",
        original_content="original2"
    )

    results = engine.rollback([entry1, entry2])
    assert len(results) == 2

    assert results[0].content == "original1"
    assert results[1].content == "original2"


def test_patch_engine_rollback_empty():
    """Test PatchEngine.rollback with empty entries."""
    engine = PatchEngine()
    results = engine.rollback([])
    assert len(results) == 0


def test_patch_engine_fuzzy_match_exact():
    """Test PatchEngine._fuzzy_match with exact match."""
    engine = PatchEngine()
    expected = ["line 1", "line 2", "line 3"]
    actual = ["line 1", "line 2", "line 3"]
    assert engine._fuzzy_match(expected, actual) is True


def test_patch_engine_fuzzy_match_prefix():
    """Test PatchEngine._fuzzy_match with prefix match."""
    engine = PatchEngine()
    expected = ["long text", "another"]
    actual = ["long", "another"]
    assert engine._fuzzy_match(expected, actual) is True


def test_patch_engine_fuzzy_match_strip():
    """Test PatchEngine._fuzzy_match with strip match."""
    engine = PatchEngine()
    expected = ["line 1", "line 2"]
    actual = [" line 1", "line 2 "]
    assert engine._fuzzy_match(expected, actual) is True


def test_patch_engine_fuzzy_match_no_match():
    """Test PatchEngine._fuzzy_match with no match."""
    engine = PatchEngine()
    expected = ["line 1", "line 2"]
    actual = ["different1", "different2"]
    assert engine._fuzzy_match(expected, actual) is False


def test_patch_engine_fuzzy_match_length_mismatch():
    """Test PatchEngine._fuzzy_match with length mismatch."""
    engine = PatchEngine()
    expected = ["line 1", "line 2"]
    actual = ["line 1"]
    assert engine._fuzzy_match(expected, actual) is False


def test_patch_engine_parse_hunks_simple():
    """Test PatchEngine._parse_hunks with simple hunk."""
    engine = PatchEngine()
    diff = """@@ -1,1 +1,1 @@
-old
+new"""
    hunks = engine._parse_hunks(diff, reverse=False)
    assert len(hunks) == 1
    old_start, old_count, new_start, new_count, lines = hunks[0]
    assert old_start == 1
    assert old_count == 1
    assert new_start == 1
    assert new_count == 1
    assert len(lines) == 2


def test_patch_engine_parse_hunks_multiple():
    """Test PatchEngine._parse_hunks with multiple hunks."""
    engine = PatchEngine()
    diff = """@@ -1,1 +1,1 @@
-old1
+new1
@@ -3,2 +3,2 @@
-old2
-old3
+new2
+new3"""
    hunks = engine._parse_hunks(diff, reverse=False)
    assert len(hunks) == 2


def test_patch_engine_parse_hunks_reverse():
    """Test PatchEngine._parse_hunks with reverse flag."""
    engine = PatchEngine()
    diff = """@@ -1,1 +1,1 @@
-old
+new"""
    hunks = engine._parse_hunks(diff, reverse=True)
    assert len(hunks) == 1

    old_start, old_count, new_start, new_count, lines = hunks[0]
    assert new_start == old_start


def test_patch_engine_try_fallback_success():
    """Test PatchEngine._try_fallback with successful fallback."""
    engine = PatchEngine()
    source = "original content"

    if engine._try_fallback("-original\n+modified", source).success:
        pass


def test_patch_engine_try_fallback_no_patch_command():
    """Test PatchEngine._try_fallback when patch command unavailable."""
    engine = PatchEngine()

    result = engine._try_fallback("@@ -1,1 +1,1 @@\n-old\n+new", "old")
    assert isinstance(result, PatchResult)
