import hashlib
import tempfile
import unittest
from pathlib import Path

from alas_headless.android_update_lab import AndroidUpdateLabError
from alas_headless.android_update_lab import parse_range_header
from alas_headless.android_update_lab import sha256_file
from alas_headless.android_update_lab import write_deterministic_payload


class AndroidUpdateLabTests(unittest.TestCase):
    def test_deterministic_payload_has_exact_size_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.bin"
            second = Path(directory) / "second.bin"
            first_hash = write_deterministic_payload(first, 1024 * 1024 + 17, "seed")
            second_hash = write_deterministic_payload(second, 1024 * 1024 + 17, "seed")
            self.assertEqual(first.stat().st_size, 1024 * 1024 + 17)
            self.assertEqual(first_hash, second_hash)
            self.assertEqual(first_hash, sha256_file(first))

    def test_range_parser_accepts_resume_and_rejects_invalid_ranges(self):
        self.assertIsNone(parse_range_header(None, 100))
        self.assertEqual(parse_range_header("bytes=20-", 100), (20, 99))
        self.assertEqual(parse_range_header("bytes=20-29", 100), (20, 29))
        for value in ("bytes=-20", "items=1-2", "bytes=100-", "bytes=20-10"):
            with self.assertRaises(AndroidUpdateLabError):
                parse_range_header(value, 100)


if __name__ == "__main__":
    unittest.main()
