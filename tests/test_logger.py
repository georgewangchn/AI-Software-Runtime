"""Tests for ASR logger."""

import tempfile
from pathlib import Path

import pytest

from asr.logger import ASRLogger


def test_logger_initialization_default():
    """Test ASRLogger initialization with default log dir."""
    logger = ASRLogger()
    assert Path(".runtime/logs").exists()
    assert Path(".runtime/logs/asr.log").parent.exists()


@pytest.fixture
def temp_log_dir():
    """Create a temporary log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_logger_initialization_custom_dir(temp_log_dir):
    """Test ASRLogger initialization with custom log dir."""
    logger = ASRLogger(log_dir=temp_log_dir)
    assert Path(temp_log_dir).exists()


def test_logger_log(temp_log_dir):
    """Test ASRLogger.log method."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log("INFO", "Test message", "builder")

    log_file = Path(temp_log_dir) / "asr.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "Test message" in content
    assert "INFO" in content
    assert "builder" in content


def test_logger_log_multiple_levels(temp_log_dir):
    """Test ASRLogger.log with different log levels."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log("DEBUG", "Debug message", "tester")
    logger.log("INFO", "Info message", "analyzer")
    logger.log("WARNING", "Warning message", "controller")
    logger.log("ERROR", "Error message", "builder")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert "DEBUG" in content
    assert "INFO" in content
    assert "WARNING" in content
    assert "ERROR" in content


def test_logger_log_empty_agent(temp_log_dir):
    """Test ASRLogger.log with empty agent name."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log("INFO", "Test message")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert "Test message" in content


def test_logger_log_convergence(temp_log_dir):
    """Test ASRLogger.log_convergence method."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log_convergence(iteration=5, errors=2, phase="REPAIRING", detail="fixing bugs")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert "CONV" in content
    assert "iter=" in content and "5" in content
    assert "errors=2" in content
    assert "phase=REPAIRING" in content
    assert "fixing bugs" in content


def test_logger_log_convergence_multiple(temp_log_dir):
    """Test ASRLogger.log_convergence with multiple calls."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log_convergence(iteration=1, errors=5, phase="TESTING", detail="running tests")
    logger.log_convergence(iteration=2, errors=3, phase="ANALYZING", detail="analyzing code")
    logger.log_convergence(iteration=3, errors=0, phase="CONVERGED", detail="all done")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert content.count("[CONV") == 3
    assert "iter=" in content


def test_logger_log_format(temp_log_dir):
    """Test ASRLogger.log message format."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log("INFO", "Test message", "builder")

    log_file = Path(temp_log_dir) / "asr.log"
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1

    line = lines[0]
    assert "[" in line
    assert "]" in line
    assert "[INFO" in line
    assert "[builder" in line


def test_logger_log_convergence_format(temp_log_dir):
    """Test ASRLogger.log_convergence message format."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log_convergence(iteration=3, errors=1, phase="TESTING", detail="testing")

    log_file = Path(temp_log_dir) / "asr.log"
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1

    line = lines[0]
    assert "[CONV" in line
    assert "iter=" in line
    assert "errors=1" in line


def test_logger_append_mode(temp_log_dir):
    """Test ASRLogger appends to existing log file."""
    logger1 = ASRLogger(log_dir=temp_log_dir)
    logger1.log("INFO", "First message")

    logger2 = ASRLogger(log_dir=temp_log_dir)
    logger2.log("INFO", "Second message")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert "First message" in content
    assert "Second message" in content
    assert content.count("INFO") == 2


def test_logger_elapsed_time(temp_log_dir):
    """Test ASRLogger.log_convergence includes elapsed time."""
    logger = ASRLogger(log_dir=temp_log_dir)
    logger.log_convergence(iteration=1, errors=0, phase="INIT", detail="starting")

    log_file = Path(temp_log_dir) / "asr.log"
    content = log_file.read_text()
    assert "0.0s" in content
