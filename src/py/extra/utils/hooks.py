import sys
from typing import Optional

ERR = sys.stderr


def setErrorStream(stream):
    global ERR
    ERR = stream
    return ERR


# --
# # Hooks
#
# Global hooks that are used by non-framework modules.
def onException(exception: Exception, message: Optional[str] = None):
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


# EOF
