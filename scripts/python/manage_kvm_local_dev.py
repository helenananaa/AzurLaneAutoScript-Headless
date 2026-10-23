"""Start, inspect or stop the local KVM development runtime."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from alas_headless.kvm_local_dev import main

if __name__ == '__main__':
    raise SystemExit(main())
