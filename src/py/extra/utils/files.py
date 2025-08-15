import mimetypes
from typing import NamedTuple
import shutil
from pathlib import Path
from typing import NamedTuple

mimetypes.init()

mimetypes.init()

MIME_TYPES: dict[str, str] = dict(
	bz2="application/x-bzip",
	gz="application/x-gzip",
)


def isText(path: Path | str, size: int = 1024) -> bool:
	"""Check if a file is likely a text file by examining its content."""
	try:
		with open(path, "rb") as f:
			s = f.read(size)
			if b"\x00" in s:
				return False
			try:
				s.decode("utf-8")
				return True
			except UnicodeDecodeError:
				return False
	except Exception:
		return False


class FileEntry(NamedTuple):
	type: str
	name: str
	stem: str
	path: list[str]
	extension: str | None = None
	contentType: str | None = None
	contentSize: int | None = None
	createdAt: float | None = None
	updatedAt: float | None = None
	mode: int | None = None
	owner: int | None = None
	group: int | None = None

	@staticmethod
	def FromPath(path: Path | str) -> "FileEntry":
		p = Path(path)
		stats = None
		if p.is_dir():
			stats = p.stat()
			return FileEntry(
				type="directory",
				path=list(p.parts)[1:],
				name=p.name,
				stem=p.name,
				createdAt=stats.st_ctime,
				updatedAt=stats.st_mtime,
				mode=stats.st_mode,
				owner=stats.st_uid,
				group=stats.st_gid,
			)
		else:
			stats = p.stat() if p.exists() else None
			return FileEntry(
				type="symlink" if p.is_symlink() else "file",
				path=list(p.parts)[1:],
				name=p.name,
				stem=p.stem,
				extension="".join(p.suffixes),
				contentType=(
					None
					if p.is_dir()
					else (
						mimetypes.guess_type(p.name)[0] or "text/plain"
						if isText(p)
						else "application/octet-stream"
					)
				),
				contentSize=stats.st_size if stats else None,
				createdAt=stats.st_ctime if stats else None,
				updatedAt=stats.st_mtime if stats else None,
				mode=stats.st_mode if stats else None,
				owner=stats.st_uid if stats else None,
				group=stats.st_gid if stats else None,
			)


class DirStats(NamedTuple):
	totalSize: int
	fileCount: int
	folderCount: int
	usedSpace: int
	freeSpace: int
	totalSpace: int


def dstats(path: Path) -> DirStats:
	path = Path(path)
	# Check if path exists and is a directory
	if not path.exists() or not path.is_dir():
		raise ValueError(f"Path {path} does not exist or is not a directory")

	total_size, file_count, folder_count = 0, 0, 0

	# Walk through directory
	for item in path.rglob("*"):
		try:
			if item.is_file():
				total_size += item.stat().st_size
				file_count += 1
			elif item.is_dir():
				folder_count += 1
		except (PermissionError, OSError):
			# Skip files/folders we can't access
			continue

	# Get disk usage information in a cross-platform way
	try:
		total, used, free = shutil.disk_usage(path)
	except Exception:
		total, used, free = 0, 0, 0

	return DirStats(
		totalSize=total_size,
		fileCount=file_count,
		folderCount=folder_count,
		freeSpace=free,
		usedSpace=used,
		totalSpace=total,
	)


def contentType(path: Path | str) -> str:
	"""Guesses the content type from the given path"""
	name = str(path)
	return (
		res
		if (res := MIME_TYPES.get(name.rsplit(".", 1)[-1].lower()))
		else mimetypes.guess_type(path)[0] or "text/plain"
	)


# EOF
