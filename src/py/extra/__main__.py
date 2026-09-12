import argparse
import os
import shutil
import ssl
import subprocess  # nosec B404: only used with a fixed argument list below
from pathlib import Path

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


def _httpsContext(
	https: bool, certfile: str | None, keyfile: str | None
) -> ssl.SSLContext | None:
	if not https and (certfile is None and keyfile is None):
		return None
	if (certfile is None) != (keyfile is None):
		raise SystemExit("--certfile and --keyfile must be used together")
	if certfile is None or keyfile is None:
		mkcert = shutil.which("mkcert")
		if mkcert is None:
			raise SystemExit(
				"HTTPS needs mkcert; install it or provide --certfile and --keyfile"
			)
		certdir = Path(os.environ.get("EXTRA_CERT_DIR", ".extra/certs"))
		certfilePath = certdir / "localhost.pem"
		keyfilePath = certdir / "localhost-key.pem"
		certdir.mkdir(parents=True, exist_ok=True)
		if not certfilePath.exists() or not keyfilePath.exists():
			subprocess.run(  # nosec B603: executable is resolved from PATH, arguments are fixed
				[
					mkcert,
					"-cert-file",
					str(certfilePath),
					"-key-file",
					str(keyfilePath),
					"localhost",
					"127.0.0.1",
					"::1",
				],
				check=True,
			)
		certfile, keyfile = str(certfilePath), str(keyfilePath)
	context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
	context.load_cert_chain(certfile, keyfile)
	return context


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
		"--https",
		action="store_true",
		help="Enable local HTTPS, generating a trusted mkcert certificate if needed",
	)
	parser.add_argument("--certfile", help="TLS certificate PEM file")
	parser.add_argument("--keyfile", help="TLS private key PEM file")
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
		default=os.environ.get("PORT", "8000"),
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
	sslContext = _httpsContext(options.https, options.certfile, options.keyfile)
	info(
		f"Starting Extra {__version__} in standalone local file server with watch service"
	)
	run(
		FileService(enableCORS=options.cors, enableSSI=options.ssi),
		FileWatchService(),
		host=options.host,
		port=options.port,
		sslContext=sslContext,
	)


if __name__ == "__main__":
	main()
# EOF
