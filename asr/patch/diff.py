from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PatchEntry:
    file_path: str
    diff_text: str
    original_content: str
    rollback_diff_text: str = ""
