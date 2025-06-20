import os
import shutil
import subprocess  # nosec: B404
import sys
import tempfile
from contextlib import contextmanager
from fcntl import F_GETFL, F_SETFL, fcntl
from pathlib import Path
from select import select
from typing import ContextManager, Iterator, Optional, Union

# --
# # Shell Utils
#
# A collection of functions that make it easier to work and interact with the
# shell.


class ShellCommandError(RuntimeError):
	"""Wrapper for a shell command error."""

	__slots__ = ["command", "status", "err"]

	def __init__(self, command: list[str], status: int, error: bytes):
		super().__init__()
		self.command = command
		self.status = status
		self.error = error

	def __str__(self) -> str:
		return f"{self.__class__.__name__}: '{' '.join(self.command)}', failed with status {self.status}: {self.error.decode('utf8')}"


@contextmanager
def cd(path: str):
	"""Temporarily changes the current directory to the given `path`, and changes
	it back to the origin upon exit. Note that this makes this function
	not thread or async safe without locking."""
	cd_path = os.path.abspath(path)
	cwd_path = os.path.abspath(os.getcwd())
	if not (os.path.exists(cd_path)):
		os.makedirs(cd_path, exist_ok=True)
	if not (os.path.exists(cd_path)):
		raise RuntimeError(f"Path does not exist: {cd_path}")
	try:
		os.chdir(cd_path)
		yield cd_path
	except Exception as e:
		raise e
	finally:
		os.chdir(cwd_path)


class mkdtemp(ContextManager):
	"""Crates a temporary the given contents."""

	def __init__(self):
		super().__init__()
		self.path = Path(tempfile.mkdtemp(prefix="ss-", suffix=".cry"))

	def cleanup(self):
		if self.path and self.path.exists():
			shutil.rmtree(self.path)

	def __enter__(self):
		return self.path

	def __exit__(self, type, value, traceback):
		self.cleanup()


class mkstemp(ContextManager):
	"""Crates a secure temporary file with the given contents."""

	def __init__(
		self,
		content: Optional[Union[str, bytes]] = None,
		encoding: str = sys.getdefaultencoding(),
		prefix: str = "extra-",
		suffix: str = ".tmp",
	):
		super().__init__()
		# TODO: We may want to use some
		self.content = content.encode(encoding) if isinstance(content, str) else content
		fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
		if content is not None:
			os.write(
				fd, bytes(content, encoding) if isinstance(content, str) else content
			)
			os.close(fd)
		self.path: Path = Path(path)

	def __enter__(self):
		return self.path

	def __exit__(self, *_):
		if self.path and self.path.exists():
			self.path.unlink()


def shell(
	command: list[str], cwd: Optional[str] = None, input: Optional[bytes] = None
) -> bytes:
	"""Runs a shell command, and returns the stdout as a byte output"""
	# FROM: https://stackoverflow.com/questions/163542/how-do-i-pass-a-string-into-subprocess-popen-using-the-stdin-argument#165662
	res = subprocess.run(  # nosec: B603
		command,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		input=input,
		cwd=cwd,
	)
	if res.returncode == 0:
		return res.stdout
	else:
		raise ShellCommandError(command, res.returncode, res.stderr)


def shellstream(
	command: list[str],
	cwd: Path | str | None = None,
	*,
	period: float = 0.5,
	env: dict[str, str] | None = None,
	size: int = 64_000,
) -> Iterator[tuple[int, bytes]]:
	"""Runs a shell command, and returns an iterator of (stdout, stderr) as a byte output"""
	# NOTE: This is borrowed from the service-kit ShellRuntime.
	pipe = subprocess.Popen(  # nosec: B603
		command,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		bufsize=0,
		cwd=str(cwd.absolute()) if isinstance(cwd, Path) else cwd,
		env=env,
		# input=input,
		# FIXME: Why do we do w anew session?
		start_new_session=True,
	)
	# We set the pipes to non blocking, this should be of benefit when
	# the process (service) is terminating.
	waiting: list[int] = []
	channels: dict[int, int] = {}
	fdout: int | None = None
	fderr: int | None = None
	if pipe.stdout:
		fcntl(
			fdout := pipe.stdout.fileno(),
			F_SETFL,
			fcntl(fdout, F_GETFL) | os.O_NONBLOCK,
		)
		waiting.append(fdout)
		channels[fdout] = 1

	if pipe.stderr:
		fcntl(
			fderr := pipe.stderr.fileno(),
			F_SETFL,
			fcntl(fderr, F_GETFL) | os.O_NONBLOCK,
		)
		waiting.append(fderr)
		channels[fderr] = 2

	closed: list = []
	while waiting:
		for fd in select(waiting, [], [], period)[0]:
			try:
				chunk = os.read(fd, size)
			except OSError:
				# NOTE: We may get a bad descriptor
				chunk = None
			if chunk:
				yield channels[fd], chunk
			else:
				closed.append(fd)
				# We don't want to close the out/err fds.
				if fd != fdout and fd != fderr:
					try:
						os.close(fd)
					except Exception:
						# This is an invalid fd
						pass
		while closed:
			del waiting[waiting.index(closed.pop())]


# EOF
