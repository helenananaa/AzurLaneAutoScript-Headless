from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "python" / "verify_android_ext4_timestamps.py"
SPEC = importlib.util.spec_from_file_location("verify_android_ext4_timestamps", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inode_time_parser_accepts_debugfs_indentation() -> None:
    output = """\
 ctime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
 atime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
 mtime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
crtime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
"""

    assert dict(MODULE.INODE_TIME.findall(output)) == {
        "c": "673419be",
        "a": "673419be",
        "m": "673419be",
        "cr": "673419be",
    }
