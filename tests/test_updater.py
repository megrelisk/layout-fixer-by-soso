import hashlib
import io
import json
import os

import pytest

import updater
import version

EXE_BYTES = b"MZ new version" * 100


def release_json(commit="abc123", data=EXE_BYTES, digest=True):
    asset = {"name": "LayoutFixer.exe", "size": len(data),
             "browser_download_url": "https://example/LayoutFixer.exe"}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
    return {"target_commitish": commit, "published_at": "2026-10-11T00:00:00Z",
            "assets": [{"name": "other.zip"}, asset]}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_for(payload):
    return lambda req, timeout=None: Resp(payload)


def test_parse_and_compare(monkeypatch):
    rel = updater.parse_release(release_json("abc123"))
    assert rel.url.endswith("LayoutFixer.exe") and len(rel.sha256) == 64
    monkeypatch.setattr(version, "COMMIT", "abc123")
    assert not updater.is_newer(rel)
    monkeypatch.setattr(version, "COMMIT", "old999")
    assert updater.is_newer(rel)


def test_release_without_exe_is_an_error():
    with pytest.raises(updater.UpdateError):
        updater.parse_release({"assets": []})


def test_fetch_release_reads_github_json():
    rel = updater.fetch_release(opener_for(json.dumps(release_json()).encode()))
    assert rel.commit == "abc123"


def test_network_error_becomes_update_error():
    def broken(req, timeout=None):
        raise OSError("no network")
    with pytest.raises(updater.UpdateError):
        updater.fetch_release(broken)


def test_download_checks_size_and_hash(tmp_path):
    dest = str(tmp_path / "LayoutFixer.new.exe")
    rel = updater.parse_release(release_json())
    updater.download(rel, dest, opener=opener_for(EXE_BYTES))
    assert open(dest, "rb").read() == EXE_BYTES


@pytest.mark.parametrize("payload", [EXE_BYTES[:-5], EXE_BYTES[:-1] + b"X"])
def test_damaged_download_is_rejected(tmp_path, payload):
    dest = str(tmp_path / "LayoutFixer.new.exe")
    rel = updater.parse_release(release_json())
    with pytest.raises(updater.UpdateError):
        updater.download(rel, dest, opener=opener_for(payload))
    assert os.listdir(tmp_path) == []


def test_install_swaps_files_and_starts_new_version(tmp_path):
    exe = str(tmp_path / "LayoutFixer.exe")
    new_exe, old_exe = updater.paths(exe)
    open(exe, "wb").write(b"old")
    open(new_exe, "wb").write(b"new")
    started = []
    updater.install(new_exe, exe, launch=lambda args, **kw: started.append(args))
    assert open(exe, "rb").read() == b"new"
    assert open(old_exe, "rb").read() == b"old"
    assert started == [[exe, "--updated"]]
    assert updater.cleanup_after_update(exe, attempts=1)
    assert sorted(os.listdir(tmp_path)) == ["LayoutFixer.exe"]


def test_source_checkout_does_not_update():
    assert not updater.can_update()


def test_version_json_is_used_and_the_api_is_not_needed():
    seen = []

    def opener(req, timeout=None):
        seen.append(req.full_url)
        if req.full_url.endswith("version.json"):
            return Resp(json.dumps({"commit": "abc", "size": 5, "sha256": "x" * 64}).encode())
        raise OSError("HTTP Error 403: rate limit exceeded")

    rel = updater.fetch_release(opener)
    assert rel.commit == "abc" and rel.url.endswith("/releases/latest/download/LayoutFixer.exe")
    assert not any("api.github.com" in u for u in seen)


def test_api_is_the_fallback_when_version_json_is_missing():
    def opener(req, timeout=None):
        if req.full_url.endswith("version.json"):
            raise OSError("HTTP Error 404")
        return Resp(json.dumps(release_json("def")).encode())

    assert updater.fetch_release(opener).commit == "def"


def test_a_locked_new_file_is_retried(tmp_path, monkeypatch):
    exe = str(tmp_path / "LayoutFixer.exe")
    new_exe, _ = updater.paths(exe)
    open(exe, "wb").write(b"old")
    open(new_exe, "wb").write(b"new")
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(src)
        if src == new_exe and calls.count(new_exe) < 3:   # antivirus scanning it
            raise PermissionError("in use")
        real(src, dst)

    monkeypatch.setattr(updater.os, "replace", flaky)
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    updater.install(new_exe, exe, launch=lambda args: None)
    assert open(exe, "rb").read() == b"new"


def test_failed_start_puts_the_old_version_back(tmp_path):
    exe = str(tmp_path / "LayoutFixer.exe")
    new_exe, old_exe = updater.paths(exe)
    open(exe, "wb").write(b"old")
    open(new_exe, "wb").write(b"new")

    def broken(args):
        raise OSError("cannot start")

    with pytest.raises(OSError):
        updater.install(new_exe, exe, launch=broken)
    assert open(exe, "rb").read() == b"old" and not os.path.exists(old_exe)


def test_new_version_is_started_with_a_fresh_pyinstaller_environment(monkeypatch):
    got = {}
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: got.update(kw, args=args))
    updater.start_detached(["LayoutFixer.exe", "--updated"])
    assert got["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert got["stdin"] == updater.subprocess.DEVNULL
