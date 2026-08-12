from __future__ import annotations

import io
import json
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_image_oci import AndroidImageOciError
from alas_headless.android_image_oci import create_redroid_oci_archive


class AndroidImageOciTests(unittest.TestCase):
    def layer(self, path: Path, content: bytes = b"init") -> None:
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as archive:
            info = tarfile.TarInfo("init")
            info.size = len(content)
            info.mode = 0o755
            info.mtime = 123
            archive.addfile(info, io.BytesIO(content))

    def test_same_inputs_produce_byte_identical_oci_archives(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            layer = directory / "rootfs.tar"
            self.layer(layer)
            first = create_redroid_oci_archive(
                layer, "arm64-v8a", "a" * 64, "redroid/test", 1746403200,
                directory / "first.oci.tar",
            )
            second = create_redroid_oci_archive(
                layer, "arm64-v8a", "a" * 64, "redroid/test", 1746403200,
                directory / "second.oci.tar",
            )
            self.assertEqual(first["archive"]["sha256"], second["archive"]["sha256"])
            self.assertEqual(first["manifest_digest"], second["manifest_digest"])
            self.assertFalse(first["game_artifact_included"])

    def test_archive_is_valid_single_platform_oci_layout(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            layer = directory / "rootfs.tar"
            self.layer(layer)
            value = create_redroid_oci_archive(
                layer, "x86_64", "b" * 64, "redroid/x86", 1746403200,
                directory / "image.tar",
            )
            with tarfile.open(directory / "image.tar") as archive:
                index = json.load(archive.extractfile("index.json"))
                layout = json.load(archive.extractfile("oci-layout"))
            self.assertEqual(layout["imageLayoutVersion"], "1.0.0")
            self.assertEqual(index["manifests"][0]["platform"]["architecture"], "amd64")
            self.assertEqual(index["manifests"][0]["digest"], value["manifest_digest"])
            self.assertEqual(
                index["manifests"][0]["annotations"]["io.containerd.image.name"],
                "docker.io/alasheadless/redroid-x86-64:latest",
            )

    def test_rejects_tag_like_source_lock_and_existing_output(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            layer = directory / "rootfs.tar"
            self.layer(layer)
            with self.assertRaisesRegex(AndroidImageOciError, "source lock"):
                create_redroid_oci_archive(
                    layer, "arm64-v8a", "latest", "fp", 1, directory / "image.tar"
                )
            output = directory / "exists.tar"
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(AndroidImageOciError, "must not already exist"):
                create_redroid_oci_archive(
                    layer, "arm64-v8a", "a" * 64, "fp", 1, output
                )


if __name__ == "__main__":
    unittest.main()
