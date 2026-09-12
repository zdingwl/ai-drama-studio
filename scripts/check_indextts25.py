#!/usr/bin/env python3
import json
import os
import sys
from urllib.error import URLError
from urllib.request import urlopen

MODEL = "IndexTeam/IndexTTS-2.5"
BASE_URL = os.getenv("AI_DRAMA_P14_INDEXTTS_BASE_URL", "http://127.0.0.1:8092/v1").rstrip("/")

try:
    with urlopen(f"{BASE_URL}/models", timeout=3) as response:
        payload = json.load(response)
except (OSError, URLError, ValueError) as exc:
    print(f"NOT READY: cannot query {BASE_URL}/models: {exc}")
    sys.exit(1)

model_ids = {
    str(item.get("id"))
    for item in payload.get("data", [])
    if isinstance(item, dict) and item.get("id")
}
if MODEL not in model_ids:
    print(f"NOT READY: service responded but {MODEL} is not loaded. Models: {sorted(model_ids)}")
    sys.exit(2)

print(f"READY: {MODEL} is available at {BASE_URL}")
