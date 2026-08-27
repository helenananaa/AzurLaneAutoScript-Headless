from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "verify_redroid_partition_runtime_components.py"
)
SPEC = importlib.util.spec_from_file_location("redroid_runtime_components", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def elf(machine: int, payload: bytes) -> bytes:
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 2
    header[5] = 1
    struct.pack_into("<H", header, 18, machine)
    return bytes(header) + payload


class RedroidPartitionRuntimeComponentTests(unittest.TestCase):
    def tree(self, root: Path, stale: bool = False) -> tuple[Path, ...]:
        system = root / "mounted-system" / "system" / "lib64"
        vendor = root / "mounted-vendor" / "lib64" / "hw"
        product_system = root / "product" / "system" / "lib64"
        product_vendor = root / "product" / "vendor" / "lib64" / "hw"
        for path in (system, vendor, product_system, product_vendor):
            path.mkdir(parents=True)
        libegl = elf(183, b"loader:_alasx.so")
        pastel = elf(183, b"process-lived-pastel")
        (product_system / "libEGL.so").write_bytes(libegl)
        (product_vendor / "vulkan.pastel.so").write_bytes(pastel)
        (system / "libEGL.so").write_bytes(
            elf(183, b"loader:_angle.so") if stale else libegl
        )
        (vendor / "vulkan.pastel.so").write_bytes(
            elf(183, b"old-pastel") if stale else pastel
        )
        return (
            root / "mounted-system",
            root / "mounted-vendor",
            product_system / "libEGL.so",
            product_vendor / "vulkan.pastel.so",
        )

    def test_matching_partition_components_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result = MODULE.verify(*self.tree(Path(raw)), "arm64-v8a", "a" * 64)
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(result["blockers"], [])

    def test_stale_partition_components_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result = MODULE.verify(
                *self.tree(Path(raw), stale=True), "arm64-v8a", "b" * 64
            )
        self.assertEqual(result["outcome"], "blocked")
        self.assertIn("libEGL.so-partition-image-stale", result["blockers"])
        self.assertIn("vulkan.pastel.so-partition-image-stale", result["blockers"])

    def test_cli_preserves_blocked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            paths = self.tree(root, stale=True)
            output = root / "result.json"
            rc = MODULE.main([
                "--system-root", str(paths[0]),
                "--vendor-root", str(paths[1]),
                "--expected-libegl", str(paths[2]),
                "--expected-pastel", str(paths[3]),
                "--abi", "arm64-v8a",
                "--source-lock-sha256", "c" * 64,
                "--output", str(output),
            ])
            value = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(rc, 1)
        self.assertEqual(value["outcome"], "blocked")


if __name__ == "__main__":
    unittest.main()
