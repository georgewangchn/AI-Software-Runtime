import pytest
import time
from main import retry

call_count = 0

def test_retry_success_first_try():
    @retry(max_attempts=3)
    def succeed():
        return "ok"
    assert succeed() == "ok"

def test_retry_eventually_succeeds():
    global call_count
    call_count = 0
    @retry(max_attempts=3, delay=0.01)
    def flaky():
        global call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("fail")
        return "recovered"
    result = flaky()
    assert result == "recovered"
    assert call_count == 2

def test_retry_exhausted():
    @retry(max_attempts=2, delay=0.01)
    def always_fails():
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        always_fails()

def test_no_unnecessary_delay():
    start = time.time()
    @retry(max_attempts=2, delay=0.5)
    def always_fails():
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        always_fails()
    elapsed = time.time() - start
    assert elapsed < 0.3
