"""Preserve the package facade while keeping focused tools inexpensive."""
import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_focused_runtime_import_does_not_initialize_public_facade():
    code = """
import sys
import alas_headless
assert 'alas_headless._public_api' not in sys.modules
from alas_headless.kvm_local_dev import LocalKvm
assert 'alas_headless._public_api' not in sys.modules
assert callable(LocalKvm)
"""
    subprocess.run([sys.executable, '-c', code], check=True, timeout=30,
                   env={**os.environ, 'PYTHONPATH': str(ROOT/'python')})


def test_every_previous_explicit_export_and_star_export_keeps_identity():
    package = importlib.import_module('alas_headless')
    api = importlib.import_module('alas_headless._public_api')
    tree = ast.parse((ROOT/'python/alas_headless/_public_api.py').read_text())
    names = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
             for alias in node.names}
    for name in names:
        assert getattr(package, name) is getattr(api, name)
    namespace = {}
    exec('from alas_headless import *', namespace)
    assert package.__all__ is api.__all__
    for name in api.__all__:
        assert namespace[name] is getattr(api, name)
    assert names <= set(dir(package))
