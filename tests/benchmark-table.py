#!/usr/bin/env python3
import argparse
import re


ROW_RE = re.compile(
	r"^(?P<name>[\w\-]+)\s+ops=\s*(?P<ops>\d+)\s+time=\s*(?P<time>[\d\.]+)ms\s+ns/op=\s*(?P<nsop>[\d\.]+)\s+ops/s=\s*(?P<opss>[\d\.]+)"
)


def parse(path: str) -> list[tuple[str, int, float, float]]:
	rows: list[tuple[str, int, float, float]] = []
	with open(path, "rt", encoding="utf8") as f:
		for line in f:
			text = line.strip()
			if not text or text.startswith("benchmark-"):
				continue
			match = ROW_RE.search(text)
			if match:
				rows.append(
					(
						match.group("name"),
						int(match.group("ops")),
						float(match.group("nsop")),
						float(match.group("opss")),
					)
				)
	return rows


def print_table(title: str, rows: list[tuple[str, int, float, float]]) -> None:
	print(title)
	print("+------------+-----------+------------+-------------+")
	print("| scenario   | ops       | ns/op      | ops/s       |")
	print("+------------+-----------+------------+-------------+")
	for name, ops, nsop, opss in rows:
		print(f"| {name:<10} | {ops:>9d} | {nsop:>10.1f} | {opss:>11.1f} |")
	print("+------------+-----------+------------+-------------+")


def main() -> None:
	parser = argparse.ArgumentParser(description="Render benchmark output as table")
	parser.add_argument("--routing", required=True)
	parser.add_argument("--reqres", required=True)
	parser.add_argument("--label", default="baseline")
	args = parser.parse_args()

	label = args.label.capitalize()
	print_table(f"Routing {label}", parse(args.routing))
	print()
	print_table(f"ReqRes {label}", parse(args.reqres))


if __name__ == "__main__":
	main()


# EOF
