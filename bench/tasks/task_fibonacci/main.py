def fib(n, cache={}):
    if n <= 1:
        return n
    if n in cache:
        return cache[n]
    result = fib(n-1, cache) + fib(n-2, cache)
    cache[n] = result
    return result
