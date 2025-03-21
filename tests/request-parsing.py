from pathlib import Path
from extra.http.parser import HTTPParser
import json

TEST_DATA = Path(__file__).absolute().parent / "data"

for item in TEST_DATA.glob("*.json"):
    with open(item, "rt") as f:
        payload = json.load(f).encode("utf8")
        parser = HTTPParser()
        for atom in parser.feed(payload):
            print(atom)

# EOF
