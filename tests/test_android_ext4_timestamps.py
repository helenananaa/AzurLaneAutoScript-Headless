from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


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


def test_inspection_identity_does_not_bind_build_root() -> None:
    superblock = """\
Filesystem created:       Wed Nov 13 03:15:10 2024
Last write time:          Wed Nov 13 03:15:10 2024
"""
    inode = """\
 ctime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
 atime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
 mtime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
crtime: 0x673419be:00000000 -- Wed Nov 13 03:15:10 2024
"""
    with patch.object(MODULE, "command", side_effect=(superblock, inode)):
        value = MODULE.inspect(Path("/independent/build-1/system.img"), 1731467710)

    assert value["image"] == "system.img"
    assert "path" not in value
