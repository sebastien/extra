from typing import ClassVar
import os

# SEE: https://no-color.org/
NO_COLOR: bool = "NO_COLOR" in os.environ
FORCE_COLOR: bool = "FORCE_COLOR" in os.environ
COLOR: bool = FORCE_COLOR or NO_COLOR is False


class Term:
	BOLD: ClassVar[str] = "" if NO_COLOR else "\033[1m"
	NORMAL: ClassVar[str] = "" if NO_COLOR else "\033[0m"
	RESET: ClassVar[str] = "" if NO_COLOR else "\033[0m"

	@staticmethod
	def Color(color: int, bold: bool = False) -> str:
		return f"\033[{'1' if bold else '0'};38;5;{color}m" if COLOR else ""

	@staticmethod
	def Bold(color: int) -> str:
		return "\033[1;38;5;%sm" % (color) if COLOR else ""


# EOF
