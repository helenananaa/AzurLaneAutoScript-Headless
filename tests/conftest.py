"""Keep ALAS' process-local import and working-directory changes in each test."""
import os
import sys
from pathlib import Path

import pkg_resources
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def restore_alas_process_environment():
    # A few retained ALAS imports also change cwd during collection.
    os.chdir(ROOT)
    # Collection can itself import an ALAS Device. Keep the genuine package
    # captured before collection, rather than capturing an already leaked shim.
    sys.modules['pkg_resources'] = pkg_resources
    try:
        yield
    finally:
        os.chdir(ROOT)
        # ALAS installs its small distribution shim for adbutils. It does not
        # provide pytest's namespace-package fixup; do not leak it to the next
        # test's monkeypatch.syspath_prepend.
        sys.modules['pkg_resources'] = pkg_resources
