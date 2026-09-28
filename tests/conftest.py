import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def detector():
    from engine import Detector
    langs = ("en", "ru", "ka")
    if not all(os.path.exists(os.path.join(ROOT, "dicts", l + ".bin")) for l in langs):
        import build_dicts
        for lang in langs:
            build_dicts.build(lang)
    return Detector(os.path.join(ROOT, "dicts"))
