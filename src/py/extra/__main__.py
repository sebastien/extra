import argparse

from .server import run
from .services.files import FileService
from .services.watch import FileWatchService
from .utils.logging import info
from .__version__ import __version__
from . import config  # NOQA: F401


def main(args: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(prog="extra")
	parser.add_argument(
		"-V",
		"--version",
		action="version",
		version=f"%(prog)s {__version__}",
	)
	parser.parse_args(args=args)
	info("Starting Extra in standalone local file server with watch service")
	run(FileService(), FileWatchService())


if __name__ == "__main__":
	main()
# EOF
