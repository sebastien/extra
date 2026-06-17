import argparse
import os

from .server import run
from .services.files import FileService
from .services.watch import FileWatchService
from .utils.logging import info
from .__version__ import __version__
from . import config  # NOQA: F401


def _parseBoolOption(value: str | None) -> bool:
	if value is None:
		return True
	normalized = value.strip().lower()
	if normalized in ("1", "true", "yes", "on"):
		return True
	if normalized in ("0", "false", "no", "off"):
		return False
	raise argparse.ArgumentTypeError(f"Invalid boolean value: {value!r}")


def main(args: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(prog="extra", add_help=False)
	parser.add_argument("--help", action="help", help="Show this help message and exit")
	parser.add_argument(
		"-V",
		"--version",
		action="version",
		version=f"%(prog)s {__version__}",
	)
	parser.add_argument(
		"-h",
		"--host",
		dest="host",
		# By default we want to bind on all interfaces, as
		# development is our primary target.
		default=os.environ.get("HOST", "0.0.0.0"),  # nosec: B104
		help="Host to bind",
	)
	parser.add_argument(
		"-p",
		"--port",
		dest="port",
		type=int,
		default=8000,
		help="Port to bind",
	)
	parser.add_argument(
		"--cors",
		dest="cors",
		nargs="?",
		const=True,
		default=True,
		type=_parseBoolOption,
		help="Enable CORS headers (default: true, use --cors=false to disable)",
	)
	parser.add_argument(
		"--ssi",
		dest="ssi",
		nargs="?",
		const=True,
		default=True,
		type=_parseBoolOption,
		help="Enable SSI expansion (default: true, use --ssi=false to disable)",
	)
	options = parser.parse_args(args=args)
	info(
		f"Starting Extra {__version__} in standalone local file server with watch service"
	)
	run(
		FileService(enableCORS=options.cors, enableSSI=options.ssi),
		FileWatchService(),
		host=options.host,
		port=options.port,
	)


if __name__ == "__main__":
	main()
# EOF
