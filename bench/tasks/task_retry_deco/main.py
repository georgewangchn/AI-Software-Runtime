import functools
import time

def retry(max_attempts=3, delay=0.1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    time.sleep(delay)
                    if attempt == max_attempts - 1:
                        raise
        return wrapper
    return decorator
