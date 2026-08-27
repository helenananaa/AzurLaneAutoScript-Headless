"""Pinned KVM/Goldfish image profile for a KVM-owned AOSP checkout."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


KVM_BUILD_SCHEMA = "alas-headless.kvm-image-build-profile/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KvmImageBuildProfileError(ValueError):
    pass


@dataclass(frozen=True)
class KvmImageBuildProfile:
    document: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "KvmImageBuildProfile":
        if not isinstance(value, Mapping):
            raise KvmImageBuildProfileError("KVM build profile must be an object")
        document = json.loads(json.dumps(value))
        if set(document) != {
            "schema",
            "backend",
            "source_lock_sha256",
            "product",
            "build",
            "runtime",
        }:
            raise KvmImageBuildProfileError("KVM build profile fields differ")
        if document.get("schema") != KVM_BUILD_SCHEMA:
            raise KvmImageBuildProfileError("KVM build profile schema mismatch")
        if document.get("backend") != "kvm":
            raise KvmImageBuildProfileError("KVM build profile backend must be kvm")
        if SHA256.fullmatch(str(document.get("source_lock_sha256", ""))) is None:
            raise KvmImageBuildProfileError("KVM source lock must be sha256")

        expected_product = {
            "abi": "x86_64",
            "lunch": "alas_kvm_x86_64-trunk_staging-userdebug",
            "product_out": "emu64x",
        }
        if document.get("product") != expected_product:
            raise KvmImageBuildProfileError(
                "KVM product must be the exact ALAS 64-bit Goldfish target"
            )

        if document.get("build") != {
            "target": "emu_img_zip",
            "separate_output_required": True,
            "relax_uses_library_check": True,
            "dynamic_partitions_size_bytes": 1342177280,
            "super_partition_size_bytes": 1350565888,
        }:
            raise KvmImageBuildProfileError("KVM build contract differs")

        if document.get("runtime") != {
            "emulator": "prebuilts/android-emulator/linux-x86_64/emulator",
            "emulator_check": "prebuilts/android-emulator/linux-x86_64/emulator-check",
            "adb": "prebuilts/runtime/adb",
            "userdata_scope": "per-instance",
            "console_port": 5588,
        }:
            raise KvmImageBuildProfileError("KVM runtime contract differs")

        canonical = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return cls(
            MappingProxyType(document), hashlib.sha256(canonical).hexdigest()
        )
