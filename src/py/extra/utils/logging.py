import sys

ERR = sys.stderr


def exception(
    exception: Exception,
    message: str | None = None,
    # origin: str | None = None,
) -> Exception:
    try:
        stream = ERR
        stream.write(
            f"!!! EXCP {f'{message}: [{exception.__class__.__name__}] {exception}' if message else f'[{exception.__class__.__name__}] {exception}'}\n"
        )
        tb = exception.__traceback__
        while tb:
            code = tb.tb_frame.f_code
            stream.write(
                f"... in {code.co_name:15s} at {tb.tb_lineno:4d} in {code.co_filename}\n",
            )
            tb = tb.tb_next
        stream.flush()
    except Exception:  # nosec: B110
        # Swallow all exceptions so that this function can be called from an exception
        # handler safely, such as in the implementation of logging/logging sinks.
        pass

    # Return the exception so that this function can be called like:
    #   raise onException(exception)
    return exception
