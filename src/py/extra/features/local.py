from ..utils.shell import shellstream


# FIXME: Does not detect when saved
def watch(paths: list[str]) -> None:
	for atom in shellstream(
		[
			"inotifywait",
			"-m",
			"-r",
			"-e",
			"modify,create,delete,move,moved_to,moved_from,attrib,close_write",
			"--format",
			"[%e]%w%f",
		]
		+ paths
	):
		print("><>>>", atom)


if __name__ == "__main__":
	import sys

	watch(sys.argv[1:])

# EOF
