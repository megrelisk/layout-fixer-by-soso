"""Write version.json for a built exe: the commit, size and SHA-256 the app's
updater checks. Published next to LayoutFixer.exe in the release.

    python tools/version_json.py dist/LayoutFixer.exe dist/version.json
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import version  # noqa: E402


def main(exe, out):
    sha = hashlib.sha256()
    with open(exe, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    data = {"commit": version.COMMIT, "built": version.BUILT,
            "size": os.path.getsize(exe), "sha256": sha.hexdigest()}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print(data)


if __name__ == "__main__":
    main(*sys.argv[1:3])
