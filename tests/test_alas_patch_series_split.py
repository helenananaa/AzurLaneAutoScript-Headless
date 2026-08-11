import json
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
FLOW_PATHS = {
    "0010-mission-mail-flow-ports.patch": {
        "module/freebies/mail_white.py",
        "module/reward/reward.py",
    },
    "0020-commission-tactical-flow-ports.patch": {
        "module/commission/commission.py",
        "module/commission/project.py",
        "module/tactical/tactical_class.py",
    },
    "0030-research-dorm-build-flow-ports.patch": {
        "module/dorm/dorm.py",
        "module/gacha/gacha_reward.py",
        "module/research/project.py",
        "module/research/research.py",
        "module/research/rqueue.py",
        "module/research/selector.py",
        "module/research/series.py",
        "module/research/ui.py",
    },
    "0040-campaign-flow-ports.patch": {
        "module/campaign/campaign_ocr.py",
        "module/campaign/campaign_status.py",
        "module/map/map_fleet_preparation.py",
    },
    "0050-combat-flow-ports.patch": {
        "module/campaign/run.py",
        "module/map/camera.py",
        "module/map/map_operation.py",
    },
}


def manifest_patch_names():
    document = json.loads((SERIES / "series.json").read_text(encoding="utf-8"))
    return tuple(Path(member["path"]).name for member in document["members"])


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
        task_members = manifest_patch_names()[2:]
        tasks = {}
        for name in task_members:
            tasks.update(target_blobs(SERIES / name))
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
        for name in manifest_patch_names():
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

    def test_each_promoted_flow_has_exact_ownership_and_residual_is_disjoint(self):
        promoted = set()
        names = set(manifest_patch_names())
        self.assertEqual(names & set(FLOW_PATHS), set(FLOW_PATHS))
        self.assertNotIn("0090-legacy-task-hooks.patch", names)
        for name, expected_paths in FLOW_PATHS.items():
            if name in names:
                actual = set(target_blobs(SERIES / name))
                self.assertEqual(actual, expected_paths)
                self.assertFalse(promoted & actual)
                promoted.update(actual)
        if "0090-legacy-task-hooks.patch" in names:
            residual = set(
                target_blobs(SERIES / "0090-legacy-task-hooks.patch")
            )
            self.assertFalse(promoted & residual)
            self.assertEqual(len(promoted) + len(residual), 19)

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
