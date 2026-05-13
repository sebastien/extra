"""
SSI (Server Side Includes) Example

This demonstrates serving a full .shtml template with SSI directives.
Features shown:
- SSI include via virtual paths
- SSI set/echo variables
- SSI conditional blocks
- FileService automatic .shtml processing

Usage:
	python ssi.py

Test with:
	curl http://localhost:8000/
	curl http://localhost:8000/index.shtml
"""
# EXPECT: Starting SSI demo server
# EXPECT: Open http://localhost:8000/index.shtml

from pathlib import Path

from extra import run
from extra.services.files import FileService
from extra.utils.logging import info


if __name__ == "__main__":
	site_root = Path(__file__).with_name("ssi-site")
	info("Starting SSI demo server", Root=str(site_root))
	info("Open http://localhost:8000/index.shtml")
	run(FileService(root=site_root))

# EOF
