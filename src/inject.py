"""Splice payload.json into template.html to produce the project's index.html.

    python inject.py

Reads src/template.html (looks for the marker __PAYLOAD_B64GZ__), gzips
../payload.json, base64-encodes it, and writes the result to ../index.html.
Then runs wrap_for_pages.py and add_catalog_link.py, per PUBLISHING.md's
instruction that a project's own injector should always do those two steps
last -- otherwise a re-run of this script silently drops both.
"""
import base64
import gzip
import json
import subprocess
import sys
from datetime import date, timezone, datetime
from pathlib import Path

SRC = Path(__file__).parent
ROOT = SRC.parent
CATALOG_TOOLS = ROOT.parent.parent / "catalog" / "tools"

TEMPLATE = SRC / "template.html"
PAYLOAD = ROOT / "payload.json"
OUT = ROOT / "index.html"


def main():
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    payload["generated"] = date.today().isoformat()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=9)
    b64 = base64.b64encode(gz).decode("ascii")
    print(f"payload: {len(raw):,} bytes raw -> {len(gz):,} bytes gzip -> {len(b64):,} bytes base64")

    template = TEMPLATE.read_text(encoding="utf-8")
    if "__PAYLOAD_B64GZ__" not in template:
        sys.exit("template.html has no __PAYLOAD_B64GZ__ marker -- refusing to write a broken page")
    out = template.replace("__PAYLOAD_B64GZ__", b64)
    out = out.replace("__BUILT_DATE__", payload["generated"])
    OUT.write_text(out, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")

    subprocess.run([sys.executable, str(CATALOG_TOOLS / "wrap_for_pages.py"), str(OUT)], check=True)
    subprocess.run([sys.executable, str(CATALOG_TOOLS / "add_catalog_link.py"), str(OUT)], check=True)


if __name__ == "__main__":
    main()
