"""Apply a Linux NUMA memory policy, then replace this process."""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
from typing import Optional, Sequence


_MPOL_BIND = 2
_SET_MEMPOLICY_SYSCALLS = {
    "x86_64": 238,
}


def bind_memory_to_node(node: int) -> None:
    if isinstance(node, bool) or not isinstance(node, int) or node < 0:
        raise ValueError("NUMA node must be a non-negative integer")
    machine = platform.machine().lower()
    syscall_number = _SET_MEMPOLICY_SYSCALLS.get(machine)
    if syscall_number is None:
        raise RuntimeError("NUMA memory binding is unsupported on this architecture")

    word_bits = ctypes.sizeof(ctypes.c_ulong) * 8
    word_count = node // word_bits + 1
    mask_type = ctypes.c_ulong * word_count
    mask = mask_type()
    mask[node // word_bits] = 1 << (node % word_bits)

    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(syscall_number),
        ctypes.c_int(_MPOL_BIND),
        ctypes.byref(mask),
        ctypes.c_ulong(word_count * word_bits),
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True, type=int)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv)
    if arguments.node < 0:
        parser.error("--node must be non-negative")

    command = list(arguments.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if arguments.check and command:
        parser.error("--check does not accept a command")
    if not arguments.check and not command:
        parser.error("a command is required unless --check is used")

    bind_memory_to_node(arguments.node)
    if arguments.check:
        return 0
    os.execvpe(command[0], command, dict(os.environ))
    raise AssertionError("exec returned unexpectedly")


if __name__ == "__main__":
    raise SystemExit(main())
