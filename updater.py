"""Self-update from the GitHub release.

Every build on main publishes LayoutFixer.exe as the "latest" release and
stamps the commit it was built from into version.py. The program compares that
commit with the release's, downloads the new exe, checks its SHA-256 against
the digest GitHub reports, and swaps it in:

    LayoutFixer.exe      -> LayoutFixer.old.exe   (a running exe can be renamed)
    LayoutFixer.new.exe  -> LayoutFixer.exe
    start LayoutFixer.exe --updated, then exit

The new process waits for the old one to quit and deletes LayoutFixer.old.exe.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass

import version

REPO = "megrelisk/layout-fixer-by-soso"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "LayoutFixer.exe"
TIMEOUT = 30


class UpdateError(Exception):
    pass


@dataclass
class Release:
    commit: str
    url: str
    size: int
    sha256: str          # may be empty if GitHub did not report a digest
    published: str


def parse_release(data):
    for asset in data.get("assets", []):
        if asset.get("name") == ASSET:
            digest = asset.get("digest") or ""
            return Release(
                commit=data.get("target_commitish", ""),
                url=asset["browser_download_url"],
                size=int(asset.get("size", 0)),
                sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
                published=data.get("published_at", ""),
            )
    raise UpdateError("в релизе нет LayoutFixer.exe")


def fetch_release(opener=urllib.request.urlopen):
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "LayoutFixer"})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            return parse_release(json.load(resp))
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"не удалось связаться с GitHub: {e}") from e


def is_newer(release):
    return bool(release.commit) and release.commit != version.COMMIT


def can_update():
    """Only the built exe updates itself; running from source does not."""
    return getattr(sys, "frozen", False) and version.COMMIT != "dev"


def download(release, dest, opener=urllib.request.urlopen, progress=None):
    tmp = dest + ".part"
    sha = hashlib.sha256()
    got = 0
    req = urllib.request.Request(release.url, headers={"User-Agent": "LayoutFixer"})
    try:
        with opener(req, timeout=TIMEOUT) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, release.size)
    except Exception as e:
        _remove(tmp)
        raise UpdateError(f"не удалось скачать обновление: {e}") from e
    if release.size and got != release.size:
        _remove(tmp)
        raise UpdateError(f"файл скачался не полностью ({got} из {release.size} байт)")
    if release.sha256 and sha.hexdigest() != release.sha256:
        _remove(tmp)
        raise UpdateError("контрольная сумма не совпала, файл повреждён")
    os.replace(tmp, dest)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def paths(exe):
    base, _ = os.path.splitext(exe)
    return base + ".new.exe", base + ".old.exe"


def install(new_exe, exe, launch=subprocess.Popen):
    """Put new_exe in place of the running exe and start it."""
    _, old_exe = paths(exe)
    _remove(old_exe)
    os.replace(exe, old_exe)            # allowed while exe is running
    try:
        os.replace(new_exe, exe)
    except OSError:
        os.replace(old_exe, exe)        # put the working version back
        raise
    launch([exe, "--updated"], close_fds=True)


def cleanup_after_update(exe, attempts=20, delay=0.5):
    """In the new process: remove the old exe once the old process has quit."""
    new_exe, old_exe = paths(exe)
    _remove(new_exe)
    for _ in range(attempts):
        if not os.path.exists(old_exe):
            return True
        try:
            os.remove(old_exe)
            return True
        except OSError:
            time.sleep(delay)
    return False


def update(progress=None):
    """Check, download and install. Returns None if already up to date, else the
    Release that is now starting. The caller exits the app right after."""
    release = fetch_release()
    if not is_newer(release):
        return None
    exe = sys.executable
    new_exe, _ = paths(exe)
    download(release, new_exe, progress=progress)
    install(new_exe, exe)
    return release
