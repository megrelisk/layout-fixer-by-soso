"""Self-update from the GitHub release.

Every build on main publishes LayoutFixer.exe as the "latest" release and
stamps the commit it was built from into version.py. The program compares that
commit with the release's, downloads the new exe, checks its SHA-256 against
the digest GitHub reports, and swaps it in:

    LayoutFixer.exe      -> LayoutFixer.old.exe   (a running exe can be renamed)
    LayoutFixer.new.exe  -> LayoutFixer.exe
    start LayoutFixer.exe --updated, then exit

The new process waits for the old one to quit and deletes LayoutFixer.old.exe.

The version is read from version.json, published next to the exe, through
GitHub's plain "latest release" download links. Those are not rate limited.
GitHub's API allows 60 requests an hour per internet address, and providers
often put many customers behind one address, so the API is only a fallback.
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
LATEST = f"https://github.com/{REPO}/releases/latest/download/"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "LayoutFixer.exe"
TIMEOUT = 30
REPLACE_TRIES = 20          # an antivirus may hold the new file for a few seconds


class UpdateError(Exception):
    """key: what failed ("network", "no_exe", "download", "size", "hash"),
    shown to the user through i18n as update.err.<key>."""

    def __init__(self, key, detail=""):
        super().__init__(f"{key}: {detail}" if detail else key)
        self.key, self.detail = key, detail


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
    raise UpdateError("no_exe")


def _get_json(url, opener, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "LayoutFixer", **(headers or {})})
    with opener(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def fetch_release(opener=urllib.request.urlopen):
    """The latest release: from version.json, or from the API if that is missing."""
    errors = []
    try:
        data = _get_json(LATEST + "version.json", opener)
        return Release(commit=data["commit"], url=LATEST + ASSET, size=int(data["size"]),
                       sha256=data["sha256"], published=data.get("built", ""))
    except Exception as e:
        errors.append(f"version.json: {e}")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):          # CI only
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        return parse_release(_get_json(API, opener, headers))
    except UpdateError:
        raise
    except Exception as e:
        errors.append(f"api: {e}")
        raise UpdateError("network", "; ".join(errors)) from e


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
        raise UpdateError("download", str(e)) from e
    if release.size and got != release.size:
        _remove(tmp)
        raise UpdateError("size", f"{got} / {release.size}")
    if release.sha256 and sha.hexdigest() != release.sha256:
        _remove(tmp)
        raise UpdateError("hash")
    os.replace(tmp, dest)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def paths(exe):
    base, _ = os.path.splitext(exe)
    return base + ".new.exe", base + ".old.exe"


def _replace(src, dst, tries=REPLACE_TRIES, delay=0.5):
    for attempt in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(delay)


def start_detached(args):
    """Start the new version on its own.

    PYINSTALLER_RESET_ENVIRONMENT: without it a one-file exe started by
    another one-file exe would reuse the parent's unpacked files, which are
    deleted as soon as the parent quits. No console handles: the app has none."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    flags = 0x00000008 | 0x00000200     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(args, env=env, close_fds=True, creationflags=flags,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def install(new_exe, exe, launch=start_detached):
    """Put new_exe in place of the running exe and start it."""
    _, old_exe = paths(exe)
    _remove(old_exe)
    try:
        _replace(exe, old_exe)          # allowed while exe is running
    except PermissionError as e:
        raise UpdateError("access", os.path.dirname(exe)) from e
    try:
        _replace(new_exe, exe)
    except OSError as e:
        os.replace(old_exe, exe)        # put the working version back
        raise UpdateError("access", str(e)) from e
    try:
        launch([exe, "--updated"])
    except OSError:
        os.replace(exe, new_exe)        # could not start it: back to the old one
        os.replace(old_exe, exe)
        raise


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
    if not os.access(os.path.dirname(exe), os.W_OK):
        raise UpdateError("access", os.path.dirname(exe))
    download(release, new_exe, progress=progress)
    install(new_exe, exe)
    return release
