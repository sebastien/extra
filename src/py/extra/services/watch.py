import asyncio
import json as basejson
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
from ..utils.logging import info, warning

JS_SCRIPT = Template(
	"""(function () {
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
})();
"""
)


class WatchBackend(NamedTuple):
	name: str
	command: list[str]


class FileWatchService(Service):
	"""Streams file system changes over Server-Sent Events."""

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

	@staticmethod
	async def terminateProcess(process: asyncio.subprocess.Process) -> int | None:
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
	def detectBackend(
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
	def makeBackend(name: str, path: Path) -> WatchBackend:
		if name == "inotifywait":
			return WatchBackend(
				name=name,
				command=[
					"inotifywait",
					"-m",
					"-r",
					"--format",
					"%w%f\t%e",
					"-e",
					"modify,create,delete,move,attrib",
					str(path),
				],
			)
		elif name == "fswatch":
			return WatchBackend(
				name=name,
				command=[
					"fswatch",
					"-xr",
					"--format",
					"%p\t%f",
					str(path),
				],
			)
		else:
			raise ValueError(f"Unsupported watch backend: {name}")

	@staticmethod
	def parseEventLine(line: str, backend: str) -> tuple[str, list[str]] | None:
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

	def resolvePath(self, path: str) -> Path | None:
		local_path = (self.root / path).resolve(strict=False)
		if not local_path.is_relative_to(self.root):
			return None
		if not self.followSymlinks and not local_path.resolve(strict=False).is_relative_to(
			self.root
		):
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

	@on(GET="/watch")
	@on(GET="/watch/{path:any}")
	def watch(self, request: HTTPRequest, path: str = ".") -> HTTPResponse:
		path = request.param("path", path) or path
		watched = self.resolvePath(path)
		if watched is None:
			return request.notAuthorized(f"Not authorized to watch path: {path}")

		backend_name = self.detectBackend()
		if backend_name is None:
			return request.fail(
				"No supported watcher tool found. Install inotifywait (Linux) or fswatch (macOS).",
				status=503,
			)

		backend = self.makeBackend(backend_name, watched)
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
			pending: OrderedDict[str, list[str]] = OrderedDict()
			stderr_tail: bytearray = bytearray()

			async def consumeStderr() -> None:
				while True:
					chunk = await process.stderr.read(4096)
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
							process.stdout.readline(), timeout=aggregate_window
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
					parsed = self.parseEventLine(decoded, backend.name)
					if parsed is None:
						continue
					changed, events = parsed
					self.mergeEvents(pending, changed, events)
					if len(pending) >= self.maxPendingPaths:
						async for chunk in flushPending():
							yield chunk
			finally:
				await self.terminateProcess(process)
				if not stderr_task.done():
					stderr_task.cancel()
					with suppress(asyncio.CancelledError):
						await stderr_task
				else:
					await stderr_task
				if process.returncode not in (0, -15):
					stderr = bytes(stderr_tail)
					warning(
						"Watcher process exited",
						Code=process.returncode,
						Error=stderr.decode("utf8", errors="replace")[:200],
					)
				info("Stopping file watch stream", Path=str(watched))

		return request.onClose(lambda _: info("File watch client disconnected")).respond(
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
			if key:
				paths.append(key)
			elif value:
				paths.append(value)
		if not paths and (query_path := request.param("path", None)):
			paths.append(query_path)
		return paths or ["."]

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


# EOF
