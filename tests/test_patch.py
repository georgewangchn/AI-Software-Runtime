"""Tests for ASR patch diff models."""
import pytest

from asr.patch.diff import PatchEntry


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


def test_patch_entry_empty_diff():
    """Test PatchEntry with empty diff_text (used for rollback snapshots)."""
    entry = PatchEntry(
        file_path="main.py",
        diff_text="",
        original_content="print('hello')",
    )
    assert entry.file_path == "main.py"
    assert entry.diff_text == ""
    assert entry.original_content == "print('hello')"


def test_patch_entry_used_in_controller():
    """Test that PatchEntry can be used as controller rollback snapshot."""
    entries = [
        PatchEntry(file_path=f"file_{i}.py", diff_text="", original_content=f"content_{i}")
        for i in range(3)
    ]
    assert len(entries) == 3
    assert entries[0].file_path == "file_0.py"
    snapshotted = {e.file_path: e.original_content for e in entries}
    assert snapshotted["file_1.py"] == "content_1"
