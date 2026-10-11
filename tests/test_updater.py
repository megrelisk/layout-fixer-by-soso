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
