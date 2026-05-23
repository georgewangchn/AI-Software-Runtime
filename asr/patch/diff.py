from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PatchResult:
    success: bool
    content: str = ""
    error: str = ""
    failed_hunk: int | None = None


@dataclass
class PatchEntry:
    file_path: str
    diff_text: str
    original_content: str
    rollback_diff_text: str = ""


class PatchEngine:
    def parse_diff(self, diff_text: str) -> list[dict]:
        cleaned = self._clean_diff(diff_text)
        diffs = []
        current_file = None
        current_lines: list[str] = []

        for line in cleaned.split("\n"):
            if line.startswith("--- ") or line.startswith("+++ "):
                if line.startswith("--- "):
                    current_file = line[4:].strip()
                    if current_file.startswith("a/") or current_file.startswith("b/"):
                        current_file = current_file[2:]
            elif line.startswith("@@"):
                if current_lines:
                    diffs.append({"file": current_file or "", "text": "\n".join(current_lines)})
                    current_lines = []
                current_lines.append(line)
            elif current_lines:
                current_lines.append(line)

        if current_lines:
            diffs.append({"file": current_file or "", "text": "\n".join(current_lines)})

        return diffs

    def apply(self, diff_text: str, base_dir: Path) -> list[PatchResult]:
        diffs = self.parse_diff(diff_text)
        results: list[PatchResult] = []

        for diff in diffs:
            file_name = diff.get("file", "")
            if not file_name:
                results.append(PatchResult(success=False, error="no file name in diff"))
                continue

            file_path = base_dir / file_name
            if not file_path.exists():
                alt_path = Path(file_name)
                if alt_path.exists():
                    file_path = alt_path
            if not file_path.exists():
                original = ""
            else:
                original = file_path.read_text()
            result = self.apply_single(diff["text"], original)
            results.append(result)

        return results

    def apply_single(self, diff_hunks: str, source_text: str, reverse: bool = False) -> PatchResult:
        fallback = self._try_fallback(diff_hunks, source_text)
        if fallback.success:
            return fallback

        try:
            result = self._apply_patch(diff_hunks, source_text, reverse)
            return PatchResult(success=True, content=result)
        except Exception as e:
            return PatchResult(success=False, error=str(e))

    def rollback(self, entries: list[PatchEntry]) -> list[PatchResult]:
        results = []
        for entry in reversed(entries):
            result = self.apply_single(entry.diff_text, entry.original_content, reverse=True)
            results.append(result)
        return results

    def _clean_diff(self, diff_text: str) -> str:
        cleaned = re.sub(r"```diff\s*", "", diff_text)
        cleaned = re.sub(r"```\s*$", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    def _fuzzy_match(self, expected: list[str], actual: list[str]) -> bool:
        if len(expected) != len(actual):
            return False
        for e, a in zip(expected, actual):
            if e == a:
                continue
            if e and a and (a.startswith(e) or e.startswith(a)):
                continue
            if e.strip() == a.strip():
                continue
            return False
        return True

    def _apply_patch(self, diff_hunks: str, source_text: str, reverse: bool = False) -> str:
        lines = source_text.split("\n")
        hunks = self._parse_hunks(diff_hunks, reverse)
        result_lines = list(lines)
        offset = 0

        for hunk in hunks:
            old_start, old_count, new_start, new_count, hunk_lines = hunk
            src_start = old_start - 1 + offset
            src_end = src_start + old_count

            removed_lines = [l for l in hunk_lines if l.startswith("-") and not l.startswith("---")]
            added_lines = [l[1:] for l in hunk_lines if l.startswith("+") and not l.startswith("+++")]

            expected_removed = result_lines[src_start:src_end]
            actual_removed = [l[1:] for l in removed_lines]

            if expected_removed != actual_removed:
                if not self._fuzzy_match(expected_removed, actual_removed):
                    raise ValueError(
                        f"Patch hunk mismatch at line {old_start}: "
                        f"expected {[l[:40] for l in actual_removed]}, "
                        f"got {[l[:40] for l in expected_removed]}"
                    )

            del result_lines[src_start:src_end]
            for i, added in enumerate(added_lines):
                result_lines.insert(src_start + i, added)

            offset += len(added_lines) - old_count

        return "\n".join(result_lines)

    def _parse_hunks(
        self, diff_hunks: str, reverse: bool = False
    ) -> list[tuple[int, int, int, int, list[str]]]:
        hunks = []
        header_pattern = re.compile(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@")
        lines = diff_hunks.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]
            match = header_pattern.match(line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2) or "1")
                new_start = int(match.group(3))
                new_count = int(match.group(4) or "1")
                hunk_lines = []
                i += 1
                while i < len(lines) and not header_pattern.match(lines[i]):
                    hunk_lines.append(lines[i])
                    i += 1

                if reverse:
                    reversed_lines = []
                    for hl in hunk_lines:
                        if hl.startswith("+") and not hl.startswith("+++"):
                            reversed_lines.append("-" + hl[1:])
                        elif hl.startswith("-") and not hl.startswith("---"):
                            reversed_lines.append("+" + hl[1:])
                        else:
                            reversed_lines.append(hl)
                    hunks.append((new_start, new_count, old_start, old_count, reversed_lines))
                else:
                    hunks.append((old_start, old_count, new_start, new_count, hunk_lines))
            else:
                i += 1

        return hunks

    def _try_fallback(self, diff_hunks: str, source_text: str) -> PatchResult:
        import subprocess
        import tempfile
        import os
        import shutil

        diff_text = diff_hunks
        if not diff_text.startswith("---") and not diff_text.startswith("diff"):
            diff_text = "--- a/target.py\n+++ b/target.py\n" + diff_text

        tmp_dir = tempfile.mkdtemp(prefix="asr_patch_")
        try:
            diff_path = os.path.join(tmp_dir, "fix.diff")
            src_path = os.path.join(tmp_dir, "main.py")
            with open(diff_path, "w") as f:
                f.write(diff_text)
            with open(src_path, "w") as f:
                f.write(source_text)

            result = subprocess.run(
                ["patch", "-d", tmp_dir, "-s", "-f", "-p0", "-i", "fix.diff", "main.py"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                content = open(src_path).read()
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return PatchResult(success=True, content=content)

            result2 = subprocess.run(
                ["patch", "-s", "-f", "-o", os.path.join(tmp_dir, "out.py"),
                 src_path, diff_path],
                capture_output=True, text=True, timeout=10,
            )
            out_path = os.path.join(tmp_dir, "out.py")
            if result2.returncode == 0 or os.path.exists(out_path):
                content = open(out_path).read() if os.path.exists(out_path) else open(src_path).read()
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return PatchResult(success=True, content=content)

            error = result2.stderr or result.stderr or "patch command failed"
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return PatchResult(success=False, error=error[:200])
        except FileNotFoundError:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return PatchResult(success=False, error="patch command not available")
        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return PatchResult(success=False, error=str(e)[:200])
