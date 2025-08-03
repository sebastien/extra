import random
import urllib.request
import urllib.error
from hashlib import sha256
import time
import sys


def sha(data: bytes) -> str:
	return sha256(data).hexdigest()


def log(*message):
	print("[client]", *(str(_) for _ in message))


random.seed(512)


def run():
	errors = 0
	t = time.monotonic()
	for base in (100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000):
		count = base + random.randint(0, base)
		body = b"-".join(b"%d" % (_) for _ in range(count))
		log(f"--- Iterating base={base} count={count}")
		sent = f"{sha(body)} {len(body)}"
		log(f"=== Sending:  {sent}")
		for port in [8000, 8001]:
			req = urllib.request.Request(f"http://localhost:{port}/upload", data=body)
			try:
				with urllib.request.urlopen(req) as resp:
					received = resp.read()
					assert received.decode().startswith(f"Read:{sha(body)}")
					log(f"=== Received: {received}")
					break
			except urllib.error.HTTPError as e:
				if port == 8001:  # Last port attempt
					log(f"!!! FAIL HTTP Error {e.code}: {e.reason}")
					errors += 1
			except Exception as e:
				if port == 8001:  # Last port attempt
					log(f"!!! FAIL {e}")
					errors += 1

	elapsed = time.monotonic() - t
	log(f"... Duration: {elapsed:0.2f}")
	if errors:
		log("EFAIL")
		return 1
	else:
		log("EOK")
		return 0


sys.exit(run())

# EOF
