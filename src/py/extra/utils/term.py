import os

# SEE: https://no-color.org/
NO_COLOR = "NO_COLOR" in os.environ
FORCE_COLOR = "FORCE_COLOR" in os.environ
COLOR: bool = FORCE_COLOR or NO_COLOR is False


def color(color: int, bold: bool = False) -> str:
    return f"\033[{'1' if bold else '0'};38;5;{color}m" if COLOR else ""


def bold(color: int) -> str:
    return "\033[1;38;5;%sm" % (color) if COLOR else ""


class Term:
    BOLD = "" if NO_COLOR else "\033[1m"
    NORMAL = "" if NO_COLOR else "\033[0m"
    RESET = "" if NO_COLOR else "\033[0m"


# EOF
