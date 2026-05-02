from pathlib import Path
from collections import OrderedDict

from extra.services.watch import FileWatchService


failed = 0


def expect(condition: bool, message: str) -> None:
	global failed
	if not condition:
		print(f"FAIL: {message}")
		failed += 1


svc = FileWatchService(root=Path("."))

# Backend detection
expect(
	FileWatchService.detectBackend(platform="linux", which=lambda n: "/usr/bin/inotifywait" if n == "inotifywait" else None)
	== "inotifywait",
	"Linux should pick inotifywait",
)
expect(
	FileWatchService.detectBackend(platform="darwin", which=lambda n: "/opt/homebrew/bin/fswatch" if n == "fswatch" else None)
	== "fswatch",
	"macOS should pick fswatch",
)
expect(
	FileWatchService.detectBackend(platform="darwin", which=lambda _: None) is None,
	"No backend should return None",
)

# Parsing
parsed_inotify = FileWatchService.parseEventLine(
	"/tmp/demo.txt\tMODIFY,CREATE", "inotifywait"
)
expect(parsed_inotify is not None, "inotify line should parse")
if parsed_inotify:
	expect(parsed_inotify[0] == "/tmp/demo.txt", "inotify path parse")
	expect(parsed_inotify[1] == ["MODIFY", "CREATE"], "inotify events parse")

parsed_fswatch = FileWatchService.parseEventLine(
	"/tmp/demo.txt\tUpdated IsFile", "fswatch"
)
expect(parsed_fswatch is not None, "fswatch line should parse")
if parsed_fswatch:
	expect(parsed_fswatch[1] == ["Updated", "IsFile"], "fswatch events parse")

# Payload shape
payload = svc.eventPayload(Path("/tmp"), "/tmp/demo.txt", ["MODIFY"])
payload_text = payload.decode("utf8") if isinstance(payload, bytes) else payload
expect('"path":"demo.txt"' in payload_text, "payload should include relative path")
expect('"events":["MODIFY"]' in payload_text, "payload should include events list")

# Aggregation merge
pending: OrderedDict[str, list[str]] = OrderedDict()
FileWatchService.mergeEvents(pending, "a.py", ["CREATE"])
FileWatchService.mergeEvents(pending, "a.py", ["MODIFY", "CREATE"])
FileWatchService.mergeEvents(pending, "b.py", ["DELETE"])
expect(list(pending.keys()) == ["a.py", "b.py"], "merge should keep insertion order")
expect(
	pending["a.py"] == ["CREATE", "MODIFY"],
	"merge should deduplicate while preserving event order",
)


class FakeRequest:
	def __init__(self, query: dict[str, str] | None = None):
		self.query = query

	def param(self, name: str, default=None):
		if not self.query:
			return default
		return self.query.get(name, default)


paths = svc.watchPathsFromRequest(FakeRequest({"src/js": "", "tests": ""}))
expect(paths == ["src/js", "tests"], "watch script should parse key paths")

paths = svc.watchPathsFromRequest(FakeRequest({"path": "src/py"}))
expect(paths == ["src/py"], "watch script should use path query fallback")

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
