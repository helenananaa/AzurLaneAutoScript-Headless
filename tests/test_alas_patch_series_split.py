import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALAS = ROOT / "integration" / "alas"
SERIES = ALAS / "series"
DIFF_PATTERN = re.compile(r"^diff --git a/(.+) b/(.+)$")
INDEX_PATTERN = re.compile(
    r"^index ([0-9a-f]+)\.\.([0-9a-f]+)(?: [0-7]{6})?$"
)

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
        "module/handler/auto_search.py",
        "module/map/map_fleet_preparation.py",
        "module/ui/ui.py",
    },
    "0050-combat-flow-ports.patch": {
        "module/campaign/campaign_base.py",
        "module/campaign/run.py",
        "module/combat/combat.py",
        "module/combat/hp_balancer.py",
        "module/exercise/combat.py",
        "module/handler/info_handler.py",
        "module/handler/strategy.py",
        "module/map/camera.py",
        "module/map/fleet.py",
        "module/map/map_operation.py",
    },
    "0060-shop-flow-ports.patch": {
        "module/shop/base.py",
        "module/shop/clerk.py",
        "module/shop/shop_medal.py",
        "module/shop/ui.py",
    },
    "0070-shipyard-flow-ports.patch": {
        "module/shipyard/ui.py",
    },
    "0080-current-task-flow-ports.patch": {
        "campaign/event_20260813_cn/a1.py",
        "campaign/event_20260813_cn/a2.py",
        "campaign/event_20260813_cn/a3.py",
        "campaign/event_20260813_cn/b1.py",
        "campaign/event_20260813_cn/b2.py",
        "campaign/event_20260813_cn/b3.py",
        "campaign/event_20260813_cn/c1.py",
        "campaign/event_20260813_cn/c2.py",
        "campaign/event_20260813_cn/c3.py",
        "campaign/event_20260813_cn/d1.py",
        "campaign/event_20260813_cn/d2.py",
        "campaign/event_20260813_cn/d3.py",
        "campaign/event_20260813_cn/sp.py",
        "module/campaign/campaign_ui.py",
        "module/daily/daily.py",
        "module/eventstory/eventstory.py",
        "module/freebies/supply_pack.py",
        "module/handler/ambush.py",
        "module/handler/enemy_searching.py",
        "module/handler/mystery.py",
        "module/hard/hard.py",
        "module/minigame/minigame.py",
        "module/minigame/new_year_challenge.py",
    },
    "0090-operation-siren-flow-ports.patch": {
        "module/os/fleet.py",
        "module/os/globe_camera.py",
        "module/os/globe_operation.py",
        "module/os/map.py",
        "module/os/tasks/archive.py",
        "module/os/tasks/hazard_leveling.py",
        "module/os/tasks/meowfficer_farming.py",
        "module/os/tasks/month_boss.py",
        "module/os/tasks/voucher.py",
        "module/os_ash/ash.py",
        "module/os_handler/enemy_searching.py",
        "module/os_handler/map_event.py",
        "module/os_handler/mission.py",
        "module/os_handler/port.py",
        "module/os_handler/storage.py",
        "module/os_shop/port_shop.py",
        "module/os_shop/shop.py",
        "module/shop/shop_voucher.py",
        "module/ui/scroll.py",
    },
    "0100-tool-flow-ports.patch": {
        "module/config/argument/args.json",
        "module/daemon/benchmark.py",
        "module/daemon/daemon.py",
        "module/daemon/game_manager.py",
        "module/daemon/os_daemon.py",
        "module/daemon/uncensored.py",
    },
    "0110-stop-condition-ports.patch": {
        "module/combat/level.py",
        "module/handler/fast_forward.py",
    },
    "0120-retirement-flow-ports.patch": {
        "module/retire/retirement.py",
    },
    "0130-enhancement-flow-ports.patch": {
        "module/retire/enhancement.py",
    },
    "0140-scheduler-contract.patch": {
        "module/config/config.py",
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
        expected_tasks = set().union(*FLOW_PATHS.values())
        self.assertEqual(set(tasks), expected_tasks)
        self.assertFalse(set(core) & set(lifecycle))
        self.assertFalse(set(core) & set(tasks))
        self.assertFalse(set(lifecycle) & set(tasks))
        self.assertEqual(set(core) | set(lifecycle) | set(tasks), set(legacy))

    def test_split_target_blobs_match_generated_combined_patch(self):
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
            set(),
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
            self.assertEqual(len(promoted) + len(residual), 20)

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
