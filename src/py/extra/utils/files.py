import mimetypes
from pathlib import Path
from typing import NamedTuple

mimetypes.init()

MIME_TYPES: dict[str, str] = dict(
	bz2="application/x-bzip",
	gz="application/x-gzip",
)


def isText(path: Path | str, size=1024):
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


def contentType(path: Path | str) -> str:
	"""Guesses the content type from the given path"""
	name = str(path)
	return (
		res
		if (res := MIME_TYPES.get(name.rsplit(".", 1)[-1].lower()))
		else mimetypes.guess_type(path)[0] or "text/plain"
	)


# EOF
