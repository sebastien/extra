import tempfile
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
	FileWatchService.DetectBackend(
		platform="linux",
		which=lambda n: "/usr/bin/inotifywait" if n == "inotifywait" else None,
	)
	== "inotifywait",
	"Linux should pick inotifywait",
)
expect(
	FileWatchService.DetectBackend(
		platform="darwin",
		which=lambda n: "/opt/homebrew/bin/fswatch" if n == "fswatch" else None,
	)
	== "fswatch",
	"macOS should pick fswatch",
)
expect(
	FileWatchService.DetectBackend(platform="darwin", which=lambda _: None) is None,
	"No backend should return None",
)

# Ignore rules
expect(
	FileWatchService.IgnorePattern() == r"(^|/)(\.[^/]+|build|dist|node_modules)(/|$)",
	"inotifywait exclude pattern should use ERE groups",
)
expect(FileWatchService.ShouldIgnorePath(".git"), "dot dirs should be ignored")
expect(
	FileWatchService.ShouldIgnorePath("src/node_modules/pkg"),
	"node_modules should be ignored",
)
expect(FileWatchService.ShouldIgnorePath("dist/app.js"), "dist should be ignored")
expect(
	not FileWatchService.ShouldIgnorePath("src/py/app.py"),
	"regular paths should be watched",
)

with tempfile.TemporaryDirectory(prefix="extra-watch-") as tmp:
	root = Path(tmp)
	(root / "src").mkdir()
	(root / "src" / "app.py").write_text("print('ok')", encoding="utf8")
	(root / ".git").mkdir()
	(root / ".git" / "config").write_text("x", encoding="utf8")
	(root / "node_modules").mkdir()
	(root / "node_modules" / "pkg").mkdir(parents=True)
	(root / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf8")
	(root / "build").mkdir()
	(root / "build" / "bundle.js").write_text("x", encoding="utf8")
	(root / "dist").mkdir()
	(root / "dist" / "bundle.js").write_text("x", encoding="utf8")
	watch_paths = FileWatchService.CollectWatchPaths(root)
	expect(str(root / "src") in watch_paths, "source dir should be watched")
	expect(str(root / "src" / "app.py") in watch_paths, "source file should be watched")
	expect(not any(".git" in p for p in watch_paths), "git dir should be ignored")
	expect(
		not any("node_modules" in p for p in watch_paths),
		"node_modules should be ignored from watch paths",
	)
	expect(
		not any("/build" in p or p.endswith("build") for p in watch_paths),
		"build should be ignored",
	)
	expect(
		not any("/dist" in p or p.endswith("dist") for p in watch_paths),
		"dist should be ignored",
	)
	backend = FileWatchService.MakeBackend("inotifywait", root)
	expect(
		backend.command[-len(watch_paths) :] == watch_paths,
		"backend should watch the pruned path list",
	)

# Parsing
parsed_inotify = FileWatchService.ParseEventLine(
	"/tmp/demo.txt\tMODIFY,CREATE", "inotifywait"
)
expect(parsed_inotify is not None, "inotify line should parse")
if parsed_inotify:
	expect(parsed_inotify[0] == "/tmp/demo.txt", "inotify path parse")
	expect(parsed_inotify[1] == ["MODIFY", "CREATE"], "inotify events parse")

parsed_fswatch = FileWatchService.ParseEventLine(
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

paths = svc.watchPathsFromRequest(
	FakeRequest({"node_modules": "", "dist": "", "src/py": ""})
)
expect(paths == ["src/py"], "watch script should ignore generated paths")

paths = svc.watchPathsFromRequest(FakeRequest({"path": "src/py"}))
expect(paths == ["src/py"], "watch script should use path query fallback")

backend = FileWatchService.MakeBackend("inotifywait", Path("."))
expect("--exclude" in backend.command, "inotify backend should exclude ignored paths")
expect(
	FileWatchService.Skip(Path("."), "src/node_modules/pkg/index.js"),
	"ignored event paths should be skipped",
)

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
