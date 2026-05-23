import time
from main import RateLimiter

def test_allow_within_limit():
    rl = RateLimiter(max_calls=2, period=10)
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is False

def test_expired_calls_cleared():
    rl = RateLimiter(max_calls=1, period=0.01)
    assert rl.allow() is True
    time.sleep(0.02)
    assert rl.allow() is True

def test_initial_state():
    rl = RateLimiter(max_calls=5, period=60)
    assert rl.allow() is True
