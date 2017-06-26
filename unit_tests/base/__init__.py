import backoff


def noop_decorator(*args, **kwargs):
    def decorator(f):
        return f
    return decorator


# Disable backoff retry calls
backoff.on_exception = noop_decorator
