import asyncio
import json as basejson
import os
import shutil
import sys
import time
from contextlib import suppress
from string import Template
from pathlib import Path
from collections import OrderedDict
from typing import AsyncIterator, Callable, NamedTuple

from ..decorators import on
from ..http.model import HTTPRequest, HTTPResponse
from ..model import Service
from ..utils.json import json
from ..utils.logging import debug, info, warning

WATCH_IGNORED_DIRS = {"build", "dist", "node_modules"}
WATCH_IGNORED_PATTERN = r"(^|/)(\.[^/]+|build|dist|node_modules)(/|$)"

JS_SCRIPT = Template(
	"""function watch() {
  const watchPaths = $watch_paths;
  const debounceMs = Number($debounce) || 120;
  const streams = [];
  let timer = null;

  const scheduleReload = function (reason) {
    if (timer !== null) return;
    timer = window.setTimeout(function () {
      timer = null;
      console.log('[watch.js] Reload triggered', reason || 'change');
      window.location.reload();
    }, debounceMs);
  };

  for (const path of watchPaths) {
    const source = new EventSource(`/watch?path=$${encodeURIComponent(path)}$window_param`);
    source.addEventListener('ready', function (event) {
      console.log('[watch.js] watching', path, event.data || '');
    });
    source.addEventListener('change', function (event) {
      scheduleReload(event.data || path);
    });
    source.onerror = function (event) {
      console.warn('[watch.js] stream error for', path, event);
    };
    streams.push(source);
  }

  window.addEventListener('beforeunload', function () {
    for (const source of streams) source.close();
  });
};watch();export default watch;
"""
)


class WatchBackend(NamedTuple):
	name: str
	command: list[str]


class FileWatchService(Service):
	"""Streams file system changes over Server-Sent Events."""

	@staticmethod
	def IgnorePattern() -> str:
		return WATCH_IGNORED_PATTERN

	@staticmethod
	def ShouldIgnorePath(path: str | Path) -> bool:
		parts = path.parts if isinstance(path, Path) else Path(path).parts
		for part in parts:
			if part in ("", ".", ".."):
				continue
			if part.startswith(".") or part in WATCH_IGNORED_DIRS:
				return True
		return False

	@staticmethod
	async def TerminateProcess(process: asyncio.subprocess.Process) -> int | None:
		if process.returncode is not None:
			return process.returncode
		process.terminate()
		try:
			await asyncio.wait_for(process.wait(), timeout=1.0)
		except TimeoutError:
			process.kill()
			await process.wait()
		return process.returncode

	@staticmethod
	def DetectBackend(
		*,
		platform: str = sys.platform,
		which: Callable[[str], str | None] = shutil.which,
	) -> str | None:
		if platform.startswith("linux") and which("inotifywait"):
			return "inotifywait"
		if platform == "darwin" and which("fswatch"):
			return "fswatch"
		return None

	@staticmethod
	def MakeBackend(name: str, path: Path) -> WatchBackend:
		target_paths = FileWatchService.CollectWatchPaths(path)
		exclude_pattern = FileWatchService.IgnorePattern()
		if name == "inotifywait":
			return WatchBackend(
				name=name,
				command=[
					"inotifywait",
					"-m",
					"--exclude",
					exclude_pattern,
					"--format",
					"%w%f\t%e",
					"-e",
					"modify,create,delete,move,attrib",
					*target_paths,
				],
			)
		elif name == "fswatch":
			return WatchBackend(
				name=name,
				command=[
					"fswatch",
					"-x",
					"--exclude",
					exclude_pattern,
					"--format",
					"%p\t%f",
					*target_paths,
				],
			)
		else:
			raise ValueError(f"Unsupported watch backend: {name}")

	@staticmethod
	def CollectWatchPaths(path: Path) -> list[str]:
		if path.is_file():
			return [str(path)]
		paths: list[str] = []
		for dirpath, dirnames, filenames in os.walk(
			path, topdown=True, followlinks=False
		):
			current = Path(dirpath)
			if FileWatchService.ShouldIgnorePath(current):
				dirnames[:] = []
				continue
			dirnames[:] = [
				d
				for d in dirnames
				if not FileWatchService.ShouldIgnorePath(current / d)
			]
			paths.append(str(current))
			for filename in filenames:
				child = current / filename
				if child.exists() and not FileWatchService.ShouldIgnorePath(child):
					paths.append(str(child))
		return paths

	@staticmethod
	def ParseEventLine(line: str, backend: str) -> tuple[str, list[str]] | None:
		parts = line.strip().split("\t", 1)
		if len(parts) != 2:
			return None
		path, events = parts
		if backend == "inotifywait":
			return path, [_.strip() for _ in events.split(",") if _.strip()]
		elif backend == "fswatch":
			return path, [_.strip() for _ in events.split() if _.strip()]
		else:
			return path, [events]

	def __init__(
		self,
		root: str | Path | None = None,
		*,
		prefix: str | None = None,
		followSymlinks: bool = False,
	):
		super().__init__(prefix=prefix)
		self.root: Path = (
			root if isinstance(root, Path) else Path(root or ".")
		).resolve()
		self.followSymlinks: bool = followSymlinks
		self.aggregateWindow: float = 0.1
		self.maxPendingPaths: int = 128

	def resolvePath(self, path: str) -> Path | None:
		if self.ShouldIgnorePath(path):
			return None
		local_path = (self.root / path).resolve(strict=False)
		if not local_path.is_relative_to(self.root):
			return None
		if not self.followSymlinks and not local_path.resolve(
			strict=False
		).is_relative_to(self.root):
			return None
		if not local_path.exists():
			return None
		return local_path

	def eventPayload(self, watched: Path, changed: str, events: list[str]) -> bytes:
		changed_path = Path(changed)
		if changed_path.is_absolute():
			try:
				rel = changed_path.relative_to(watched)
				path = rel.as_posix()
			except ValueError:
				path = changed
		else:
			path = changed
		return json(
			{
				"path": path,
				"events": events,
				"timestamp": time.time(),
			}
		)

	@staticmethod
	def mergeEvents(
		pending: OrderedDict[str, list[str]], path: str, events: list[str]
	) -> None:
		if path in pending:
			existing = pending[path]
			for event in events:
				if event not in existing:
					existing.append(event)
		else:
			pending[path] = list(events)

	@staticmethod
	def Skip(watched: Path, changed: str) -> bool:
		changed_path = Path(changed)
		if changed_path.is_absolute():
			with suppress(ValueError):
				changed_path = changed_path.relative_to(watched)
		return FileWatchService.ShouldIgnorePath(changed_path)

	ignorePattern = IgnorePattern
	shouldIgnorePath = ShouldIgnorePath
	detectBackend = DetectBackend
	makeBackend = MakeBackend
	collectWatchPaths = CollectWatchPaths
	parseEventLine = ParseEventLine
	skip = Skip

	@on(GET="/watch")
	@on(GET="/watch/{path:any}")
	def watch(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		path = request.param("path", path) or path
		watched = self.resolvePath(path)
		if watched is None:
			return request.notAuthorized(f"Not authorized to watch path: {path}")

		backend_name = self.DetectBackend()
		if backend_name is None:
			return request.fail(
				"No supported watcher tool found. Install inotifywait (Linux) or fswatch (macOS).",
				status=503,
			)

		backend = self.MakeBackend(backend_name, watched)
		window_param = request.param("window", None)
		aggregate_window = self.aggregateWindow
		if isinstance(window_param, str):
			try:
				aggregate_window = max(float(window_param), 0.02)
			except ValueError:
				pass

		async def stream() -> AsyncIterator[str]:
			info(
				"Starting file watch stream",
				Path=str(watched),
				Backend=backend.name,
				Client=str(request.header("X-Forwarded-For") or "local"),
			)
			process = await asyncio.create_subprocess_exec(
				*backend.command,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
			assert process.stdout is not None
			assert process.stderr is not None
			process_stdout = process.stdout
			process_stderr = process.stderr
			pending: OrderedDict[str, list[str]] = OrderedDict()
			stderr_tail: bytearray = bytearray()

			async def consumeStderr() -> None:
				while True:
					chunk = await process_stderr.read(4096)
					if not chunk:
						break
					if len(stderr_tail) < 8192:
						left = 8192 - len(stderr_tail)
						stderr_tail.extend(chunk[:left])

			stderr_task = asyncio.create_task(consumeStderr())

			async def flushPending() -> AsyncIterator[str]:
				for changed, events in pending.items():
					yield "event: change\n"
					payload = self.eventPayload(watched, changed, events)
					yield f"data: {payload.decode('utf8')}\n\n"
				pending.clear()

			try:
				yield "event: ready\n"
				ready_payload = json({"path": str(watched), "backend": backend.name})
				yield f"data: {ready_payload.decode('utf8')}\n\n"
				while True:
					try:
						line = await asyncio.wait_for(
							process_stdout.readline(), timeout=aggregate_window
						)
					except TimeoutError:
						if pending:
							async for chunk in flushPending():
								yield chunk
						continue
					if not line:
						if pending:
							async for chunk in flushPending():
								yield chunk
						break
					decoded = line.decode("utf8", errors="replace").strip()
					if not decoded:
						continue
					parsed = self.ParseEventLine(decoded, backend.name)
					if parsed is None:
						continue
					changed, events = parsed
					if self.Skip(watched, changed):
						continue
					self.mergeEvents(pending, changed, events)
					if len(pending) >= self.maxPendingPaths:
						async for chunk in flushPending():
							yield chunk
			finally:
				await self.TerminateProcess(process)
				if not stderr_task.done():
					stderr_task.cancel()
					with suppress(asyncio.CancelledError):
						await stderr_task
				else:
					await stderr_task
				if process.returncode not in (0, -15):
					stderr = bytes(stderr_tail)
					code = process.returncode if process.returncode is not None else -1
					warning(
						"Watcher process exited",
						Code=code,
						Error=stderr.decode("utf8", errors="replace")[:200],
					)
				debug("Stopping file watch stream", Path=str(watched))

		def onClientClose(_: HTTPRequest) -> None:
			debug("File watch client disconnected")

		return request.onClose(onClientClose).respond(
			stream(),
			contentType="text/event-stream",
			headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
		)

	def watchPathsFromRequest(self, request: HTTPRequest) -> list[str]:
		if not request.query:
			return ["."]
		reserved = {"path", "window", "reload", "debounce"}
		paths: list[str] = []
		for key, value in request.query.items():
			if key in reserved:
				continue
			candidate = key if key else value
			if candidate and not self.ShouldIgnorePath(candidate):
				paths.append(candidate)
		if not paths and (query_path := request.param("path", None)):
			if not self.ShouldIgnorePath(query_path):
				paths.append(query_path)
		return paths

	@on(GET="/watch.js")
	def watchScript(self, request: HTTPRequest) -> HTTPResponse:
		paths = self.watchPathsFromRequest(request)
		window = request.param("window", None)
		debounce = request.param("debounce", "120") or "120"
		watch_paths = basejson.dumps(paths)
		window_param = f"&window={window}" if window else ""
		script = JS_SCRIPT.substitute(
			watch_paths=watch_paths,
			debounce=basejson.dumps(debounce),
			window_param=window_param,
		)
		return request.respond(
			script,
			contentType="text/javascript; charset=utf-8",
			headers={"Cache-Control": "no-cache"},
		)

	ignorePattern = IgnorePattern
	shouldIgnorePath = ShouldIgnorePath
	detectBackend = DetectBackend
	makeBackend = MakeBackend
	parseEventLine = ParseEventLine
	skip = Skip


# EOF
