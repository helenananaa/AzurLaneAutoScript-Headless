#!/usr/bin/env python3
"""Capture an immutable Redroid OCI image/container identity over read-only SSH."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "alas-headless.oci-image-identity/v1"


def ssh_json(ssh: Path, target: str, arguments: Sequence[str]) -> Any:
    completed = subprocess.run(
        [str(ssh), "-o", "BatchMode=yes", target] + list(arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("remote inspect failed: {0}".format(" ".join(arguments[:2])))
    return json.loads(completed.stdout)


def only_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError("{0} inspect must return exactly one object".format(label))
    return value[0]


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    if args.output.exists():
        parser.error("--output must not already exist")
    if not args.ssh.is_file():
        parser.error("--ssh must be a file")

    container = only_mapping(
        ssh_json(args.ssh, args.target, ("docker", "inspect", args.container)),
        "container",
    )
    image_id = str(container.get("Image", ""))
    image = only_mapping(
        ssh_json(args.ssh, args.target, ("docker", "image", "inspect", image_id)),
        "image",
    )
    config = container.get("Config", {})
    descriptor = container.get("ImageManifestDescriptor", {})
    if not isinstance(config, dict) or not isinstance(descriptor, dict):
        raise ValueError("container image metadata is incomplete")
    reference = str(config.get("Image", ""))
    digest = str(descriptor.get("digest", ""))
    repo_digests = image.get("RepoDigests", [])
    immutable = (
        "@sha256:" in reference
        and reference.rsplit("@", 1)[1] == digest
        and isinstance(repo_digests, list)
        and reference in repo_digests
    )
    if not immutable:
        raise ValueError("container is not bound to its inspected OCI manifest digest")

    mounts = container.get("Mounts", [])
    host_config = container.get("HostConfig", {})
    network = container.get("NetworkSettings", {})
    document = {
        "schema": SCHEMA,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_host": args.target,
        "container_name": str(container.get("Name", "")).lstrip("/"),
        "container_id": container.get("Id"),
        "container_running": container.get("State", {}).get("Running"),
        "image_reference": reference,
        "image_id": image_id,
        "manifest_digest": digest,
        "repo_digests": repo_digests,
        "architecture": image.get("Architecture"),
        "os": image.get("Os"),
        "image_created": image.get("Created"),
        "immutable": immutable,
        "privileged": host_config.get("Privileged") if isinstance(host_config, dict) else None,
        "command": list(container.get("Args", [])),
        "mounts": mounts if isinstance(mounts, list) else [],
        "ports": network.get("Ports", {}) if isinstance(network, dict) else {},
        "game_artifact_included": False,
        "alas_workload_used": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
