import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALAS = ROOT / "integration" / "alas"
SERIES = ALAS / "series"
DIFF_PATTERN = re.compile(r"^diff --git a/(.+) b/(.+)$")
INDEX_PATTERN = re.compile(r"^index ([0-9a-f]+)\.\.([0-9a-f]+) [0-7]{6}$")

CORE_PATHS = {
    "module/base/base.py",
    "module/device/control.py",
    "module/device/screenshot.py",
    "module/ocr/ocr.py",
}
LIFECYCLE_PATHS = {
    "module/device/device.py",
    "module/handler/login.py",
}


def target_blobs(path):
    result = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = DIFF_PATTERN.fullmatch(line)
        if match is not None:
            if match.group(1) != match.group(2):
                raise AssertionError("renamed patch paths are outside the split contract")
            current = match.group(1)
            continue
        match = INDEX_PATTERN.fullmatch(line)
        if match is not None and current is not None:
            result[current] = match.group(2)
            current = None
    return result


def file_mutations(path):
    result = {}
    current = None
    additions = []
    deletions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = DIFF_PATTERN.fullmatch(line)
        if match is not None:
            if current is not None:
                result[current] = (tuple(additions), tuple(deletions))
            current = match.group(1)
            additions = []
            deletions = []
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])
        elif current is not None and line.startswith("-") and not line.startswith("---"):
            deletions.append(line[1:])
    if current is not None:
        result[current] = (tuple(additions), tuple(deletions))
    return result


class AlasPatchSeriesSplitTests(unittest.TestCase):
    def test_split_members_are_disjoint_and_cover_legacy_surface(self):
        core = target_blobs(SERIES / "0001-core-ports.patch")
        lifecycle = target_blobs(SERIES / "0002-session-lifecycle.patch")
        tasks = target_blobs(SERIES / "0090-legacy-task-hooks.patch")
        legacy = target_blobs(ALAS / "0001-semantic-oracle-hooks.patch")

        self.assertEqual(set(core), CORE_PATHS)
        self.assertEqual(set(lifecycle), LIFECYCLE_PATHS)
        self.assertEqual(len(tasks), 19)
        self.assertFalse(set(core) & set(lifecycle))
        self.assertFalse(set(core) & set(tasks))
        self.assertFalse(set(lifecycle) & set(tasks))
        self.assertEqual(set(core) | set(lifecycle) | set(tasks), set(legacy))

    def test_split_transformations_match_legacy_including_stale_index_cases(self):
        legacy = target_blobs(ALAS / "0001-semantic-oracle-hooks.patch")
        split = {}
        split_mutations = {}
        for name in (
            "0001-core-ports.patch",
            "0002-session-lifecycle.patch",
            "0090-legacy-task-hooks.patch",
        ):
            split.update(target_blobs(SERIES / name))
            split_mutations.update(file_mutations(SERIES / name))
        legacy_mutations = file_mutations(
            ALAS / "0001-semantic-oracle-hooks.patch"
        )
        self.assertEqual(set(split), set(legacy))
        stale_legacy_indices = set()
        for path, legacy_abbreviation in legacy.items():
            if not split[path].startswith(legacy_abbreviation):
                stale_legacy_indices.add(path)
                self.assertEqual(split_mutations[path], legacy_mutations[path])
        self.assertEqual(
            stale_legacy_indices,
            {"module/map/camera.py", "module/map/map_operation.py"},
        )

    def test_core_prefix_contains_no_task_module(self):
        core_prefix = set(target_blobs(SERIES / "0001-core-ports.patch"))
        core_prefix.update(target_blobs(SERIES / "0002-session-lifecycle.patch"))
        forbidden = (
            "module/campaign/",
            "module/commission/",
            "module/dorm/",
            "module/freebies/",
            "module/gacha/",
            "module/map/",
            "module/research/",
            "module/reward/",
            "module/tactical/",
        )
        self.assertFalse(
            any(path.startswith(forbidden) for path in core_prefix)
        )


if __name__ == "__main__":
    unittest.main()
