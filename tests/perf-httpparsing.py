import bz2
from pathlib import Path
from extra.http.parser import HTTPParser

BASE = Path(__file__).absolute().parent.parent
data_file = BASE / "data/csic_2010-normalTrafficTraining.txt.bz2"

if not data_file.exists():
	print(f"SKIPPED: Data file {data_file} not found")
	exit(0)

with bz2.open(data_file) as f:
	parser = HTTPParser("localhost", 8000)
	while True:
		chunk = f.read(1024)
		read = parser.feed(chunk)
		print("READ", read, "/", len(chunk))
		break
