import os
import tempfile
from pathlib import Path

from extra.services.files import FileService


failed = 0

with tempfile.TemporaryDirectory(prefix="extra-sec-root-") as tmp_root:
	with tempfile.TemporaryDirectory(prefix="extra-sec-out-") as tmp_out:
		root = Path(tmp_root)
		outside = Path(tmp_out) / "secret.txt"
		inside = root / "ok.txt"

		outside.write_text("outside", encoding="utf8")
		inside.write_text("inside", encoding="utf8")

		svc = FileService(root=root)

		resolved_inside, _ = svc.resolvePath("ok.txt")
		if resolved_inside != inside.resolve():
			print("FAIL: expected inside file to resolve")
			failed += 1

		resolved_outside, _ = svc.resolvePath("../secret.txt")
		if resolved_outside is not None:
			print("FAIL: traversal path should be rejected")
			failed += 1

		link_path = root / "link.txt"
		try:
			os.symlink(outside, link_path)
			resolved_link, _ = svc.resolvePath("link.txt")
			if resolved_link is not None:
				print("FAIL: symlink escape should be rejected")
				failed += 1
		except OSError:
			# Symlink may be unavailable in restricted environments.
			pass

if failed:
	print(f"FAIL {failed} tests failed")
	print("ERR")
else:
	print("OK! All tests passed")
	print("EOK")


# EOF
