import os
import re
import sys
from pathlib import Path

from setuptools import find_packages, setup


def read_version() -> str:
	version_file = Path(__file__).parent / "src" / "py" / "extra" / "__version__.py"
	content = version_file.read_text(encoding="utf-8")
	match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
	if not match:
		raise RuntimeError(
			"Unable to find version string in src/py/extra/__version__.py"
		)
	return match.group(1)


VERSION = read_version()

# Try to import mypyc, make it optional
try:
	from mypyc.build import mypycify

	MYPYC_AVAILABLE = True
except ImportError:
	MYPYC_AVAILABLE = False


def readme():
	with open("README.md", "r", encoding="utf-8") as fh:
		return fh.read()


def list_ext_modules(base_path="src/py/extra"):
	python_files = []
	for root, _, files in os.walk(base_path):
		for file in files:
			if file.endswith(".py"):
				python_files.append(os.path.join(root, file))
	return python_files


# Determine if we should use mypyc compilation
USE_MYPYC = MYPYC_AVAILABLE and "--use-mypyc" in sys.argv and "sdist" not in sys.argv

# Remove our custom flag from sys.argv to avoid confusing setuptools
if "--use-mypyc" in sys.argv:
	sys.argv.remove("--use-mypyc")

# Prepare ext_modules
ext_modules = []
if USE_MYPYC:
	print("=" * 60)
	print("MyPyC compilation is enabled.")
	print("This may take a few minutes to compile all Python files...")
	print("=" * 60)
	ext_modules = mypycify(list_ext_modules())
elif MYPYC_AVAILABLE and "sdist" not in sys.argv:
	print(
		"Note: Use --use-mypyc flag to enable MyPyC compilation for better performance."
	)


setup(
	name="extra-http",
	version=VERSION,
	author="Sébastien Pierre",
	author_email="sebastien.pierre@gmail.com",
	license="BSD-3-Clause",
	description="A toolkit to write HTTP/1.1 web services and applications, with first class support for streaming",
	long_description=readme(),
	long_description_content_type="text/markdown",
	url="https://github.com/sebastien/extra",
	project_urls={
		"Bug Tracker": "https://github.com/sebastien/extra/issues",
		"Documentation": "https://github.com/sebastien/extra",
		"Source Code": "https://github.com/sebastien/extra",
	},
	packages=find_packages(where="src/py"),
	package_dir={"": "src/py"},
	# SEE: https://pypi.org/classifiers/
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Intended Audience :: Developers",
		"Operating System :: OS Independent",
		"Programming Language :: Python :: 3",
		"Programming Language :: Python :: 3.8",
		"Programming Language :: Python :: 3.9",
		"Programming Language :: Python :: 3.10",
		"Programming Language :: Python :: 3.11",
		"Programming Language :: Python :: 3.12",
		"Topic :: Internet :: WWW/HTTP :: HTTP Servers",
		"Topic :: Software Development :: Libraries :: Python Modules",
		"Topic :: System :: Networking",
	],
	python_requires=">=3.8",
	install_requires=[
		"mypy-extensions",
		"toon-python",
	],
	extras_require={
		"dev": [
			"mypy",
			"flake8",
			"bandit",
		],
		"passkeys": [
			"webauthn",
		],
	},
	entry_points={
		"console_scripts": [
			"extra=extra.__main__:main",
		],
	},
	include_package_data=True,
	zip_safe=False,
	# NOTE: mypyc compilation is optional and experimental
	ext_modules=ext_modules,
)
