from main import fib

def test_fib_small():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(2) == 1
    assert fib(5) == 5

def test_fib_large_performance():
    import time
    start = time.time()
    result = fib(30)
    elapsed = time.time() - start
    assert result == 832040
    assert elapsed < 0.1
