from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
(ROOT / ".ci-tmp").mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _isolate_secrets(tmp_path, monkeypatch):
    import stlibs.secrets as secrets

    monkeypatch.setattr(secrets, 'SECRETS_DIR', str(tmp_path / '.env'))


@pytest.fixture(scope='session')
def repo_root() -> Path:
    return ROOT
