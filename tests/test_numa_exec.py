import ctypes
from unittest.mock import patch

import pytest

from alas_headless.numa_exec import bind_memory_to_node


class FakeLibc:
    def __init__(self, result=0, error=0):
        self.result = result
        self.error = error
        self.arguments = None

    def syscall(self, *arguments):
        self.arguments = arguments
        ctypes.set_errno(self.error)
        return self.result


def test_bind_memory_to_node_builds_linux_word_mask():
    libc = FakeLibc()
    with patch("alas_headless.numa_exec.platform.machine", return_value="x86_64"), patch(
        "alas_headless.numa_exec.ctypes.CDLL",
        return_value=libc,
    ):
        bind_memory_to_node(1)

    assert libc.arguments is not None
    assert libc.arguments[0].value == 238
    assert libc.arguments[1].value == 2
    assert ctypes.cast(libc.arguments[2], ctypes.POINTER(ctypes.c_ulong))[0] == 2
    assert libc.arguments[3].value == ctypes.sizeof(ctypes.c_ulong) * 8


@pytest.mark.parametrize("node", [True, -1, "1", 1.0])
def test_bind_memory_to_node_rejects_invalid_node(node):
    with pytest.raises(ValueError, match="NUMA node"):
        bind_memory_to_node(node)


def test_bind_memory_to_node_reports_kernel_failure():
    libc = FakeLibc(result=-1, error=22)
    with patch("alas_headless.numa_exec.platform.machine", return_value="x86_64"), patch(
        "alas_headless.numa_exec.ctypes.CDLL",
        return_value=libc,
    ), pytest.raises(OSError, match="Invalid argument"):
        bind_memory_to_node(1)
