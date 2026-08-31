#!/usr/bin/env bash
set -euo pipefail

echo "Redroid builds are disabled in the KVM control repository." >&2
echo "Run the v2 dual-domain Redroid entrypoint from the Redroid control repository." >&2
echo "This legacy wrapper never accepts a source tree or starts a build." >&2
exit 2
