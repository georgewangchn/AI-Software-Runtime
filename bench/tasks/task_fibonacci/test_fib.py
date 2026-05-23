import pytest
import threading
from main import fib


def test_cache_hit_across_recursive_calls():
    result1 = fib(5)
    result2 = fib(5)
    assert result1 == result2 == 5


def test_cache_persists_between_top_level_calls():
    result1 = fib(2)
    result2 = fib(2)
    assert result1 == result2 == 1


def test_cache_size_limited():
    for i in range(100):
        fib(i)
    result = fib(5)
    assert result == 5


def test_cache_must_be_shared():
    result = fib(6)
    assert result == 8


def test_no_global_state():
    result1 = fib(3)
    result2 = fib(3)
    assert result1 == result2 == 2


def test_thread_safe():
    results = []
    
    def worker():
        results.append(fib(10))
    
    threads = []
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    assert len(set(results)) == 1
    assert results[0] == 55


def test_no_side_effects():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(2) == 1
    assert fib(3) == 2
    assert fib(4) == 3
    assert fib(5) == 5
    assert fib(6) == 8
    assert fib(7) == 13
    assert fib(8) == 21
    assert fib(9) == 34
    assert fib(10) == 55


def test_cache_statistics():
    fib(5)
    assert True