"""Tests for LLM token usage tracker."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from asr.agents.llm_tracker import log_token_usage


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestLogTokenUsage:
    """Tests for log_token_usage function."""

    def test_log_token_usage_basic(self, temp_log_dir):
        """Test basic token usage logging."""
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }

        log_token_usage("builder", "gpt-4o", usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["agent"] == "builder"
        assert entry["model"] == "gpt-4o"
        assert entry["prompt_tokens"] == 100
        assert entry["completion_tokens"] == 50
        assert entry["total_tokens"] == 150
        assert "timestamp" in entry

    def test_log_token_usage_dict_with_to_dict(self, temp_log_dir):
        """Test logging with usage dict that has to_dict method."""
        mock_usage = MagicMock()
        mock_usage.to_dict.return_value = {
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300
        }

        log_token_usage("tester", "claude-3", mock_usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert log_file.exists()

        entry = json.loads(log_file.read_text().strip())
        assert entry["agent"] == "tester"
        assert entry["model"] == "claude-3"
        assert entry["prompt_tokens"] == 200

    def test_log_token_usage_missing_fields(self, temp_log_dir):
        """Test logging with missing fields - should default to zero."""
        usage = {
            "prompt_tokens": 100
        }

        log_token_usage("analyzer", "gpt-3.5", usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        entry = json.loads(log_file.read_text().strip())

        assert entry["prompt_tokens"] == 100
        assert entry["completion_tokens"] == 0
        assert entry["total_tokens"] == 0

    def test_log_token_usage_empty_dict(self, temp_log_dir):
        """Test logging with empty dict - should default all to zero."""
        log_token_usage("builder", "gpt-4o", {}, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        entry = json.loads(log_file.read_text().strip())

        assert entry["prompt_tokens"] == 0
        assert entry["completion_tokens"] == 0
        assert entry["total_tokens"] == 0

    def test_log_token_usage_multiple_entries(self, temp_log_dir):
        """Test logging multiple token usage entries."""
        usage1 = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        usage2 = {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}
        usage3 = {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}

        log_token_usage("builder", "gpt-4o", usage1, temp_log_dir)
        log_token_usage("tester", "gpt-4o", usage2, temp_log_dir)
        log_token_usage("analyzer", "gpt-4o", usage3, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        entry3 = json.loads(lines[2])

        assert entry1["agent"] == "builder"
        assert entry2["agent"] == "tester"
        assert entry3["agent"] == "analyzer"

    def test_log_token_usage_default_log_dir(self):
        """Test logging with default log directory."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

        log_token_usage("builder", "gpt-4o", usage)

        log_file = Path(".runtime/logs/llm.jsonl")
        assert log_file.exists()

        entry = json.loads(log_file.read_text().strip())
        assert entry["agent"] == "builder"

        if log_file.exists():
            log_file.unlink()

    def test_log_token_usage_non_dict_usage(self, temp_log_dir):
        """Test logging with non-dict usage - should be ignored."""
        log_token_usage("builder", "gpt-4o", "invalid", temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert not log_file.exists() or log_file.read_text().strip() == ""

    def test_log_token_usage_none_usage(self, temp_log_dir):
        """Test logging with None usage - should be ignored."""
        log_token_usage("builder", "gpt-4o", None, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert not log_file.exists()

    def test_log_token_usage_string_path(self, temp_log_dir):
        """Test logging with string path for log_dir."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

        log_token_usage("builder", "gpt-4o", usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert log_file.exists()

    def test_log_token_usage_path_object(self, temp_log_dir):
        """Test logging with Path object for log_dir."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

        log_token_usage("builder", "gpt-4o", usage, Path(temp_log_dir))

        log_file = Path(temp_log_dir) / "llm.jsonl"
        assert log_file.exists()

    def test_log_token_usage_timestamp_structure(self, temp_log_dir):
        """Test that timestamp is a valid Unix timestamp."""
        before_log = time.time()

        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        log_token_usage("builder", "gpt-4o", usage, temp_log_dir)

        after_log = time.time()

        log_file = Path(temp_log_dir) / "llm.jsonl"
        entry = json.loads(log_file.read_text().strip())

        assert "timestamp" in entry
        timestamp = entry["timestamp"]
        assert isinstance(timestamp, (int, float))
        assert before_log <= timestamp <= after_log

    def test_log_token_usage_append_mode(self, temp_log_dir):
        """Test that logging appends to existing file."""
        usage1 = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        usage2 = {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}

        log_token_usage("builder", "gpt-4o", usage1, temp_log_dir)
        log_token_usage("tester", "gpt-4o", usage2, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        content = log_file.read_text()

        lines = content.strip().split("\n")
        assert len(lines) == 2

        assert "builder" in lines[0]
        assert "tester" in lines[1]

    def test_log_token_usage_exception_handling(self, temp_log_dir):
        """Test that exceptions in logging are suppressed."""
        with patch("builtins.open", side_effect=IOError("Mock error")):
            with patch("pathlib.Path.mkdir", side_effect=IOError("Mock error")):
                usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

                log_token_usage("builder", "gpt-4o", usage, temp_log_dir)

    def test_log_token_usage_json_format(self, temp_log_dir):
        """Test that logged data is valid JSON."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

        log_token_usage("builder", "gpt-4o", usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        content = log_file.read_text().strip()

        entry = json.loads(content)
        assert isinstance(entry, dict)
        assert len(entry) == 6

    def test_log_token_usage_different_models(self, temp_log_dir):
        """Test logging usage for different models."""
        models = ["gpt-4o", "claude-3-opus", "gpt-3.5-turbo", "qwen-72b"]

        for i, model in enumerate(models):
            usage = {
                "prompt_tokens": 100 * (i + 1),
                "completion_tokens": 50 * (i + 1),
                "total_tokens": 150 * (i + 1)
            }
            log_token_usage("builder", model, usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        lines = log_file.read_text().strip().split("\n")

        assert len(lines) == 4

        logged_models = [json.loads(line)["model"] for line in lines]
        assert logged_models == models

    def test_log_token_usage_different_agents(self, temp_log_dir):
        """Test logging usage for different agents."""
        agents = ["builder", "tester", "analyzer"]

        for agent in agents:
            usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            log_token_usage(agent, "gpt-4o", usage, temp_log_dir)

        log_file = Path(temp_log_dir) / "llm.jsonl"
        lines = log_file.read_text().strip().split("\n")

        assert len(lines) == 3

        logged_agents = [json.loads(line)["agent"] for line in lines]
        assert logged_agents == agents
