import bz2
from pathlib import Path
from extra.protocols.http import HTTPParser

BASE = Path(__file__).absolute().parent.parent

with bz2.open(BASE / "data/csic_2010-normalTrafficTraining.txt.bz2") as f:
    parser = HTTPParser("localhost", 8000)
    while True:
        chunk = f.read(1024)
        read = parser.feed(chunk)
        print("READ", read, "/", len(chunk))
        break
