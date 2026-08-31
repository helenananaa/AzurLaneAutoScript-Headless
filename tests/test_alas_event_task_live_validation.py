import hashlib
import ast
import base64
import contextlib
import importlib
import io
import os
import json
import py_compile
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from alas_headless.runner_supervision import (
    RECORD_CLEANUP,
    RECORD_RESULT,
    RECORD_WORKER_CONTROL,
    WORKER_CLEANUP_SCHEMA,
    WORKER_RESULT_SCHEMA,
    ConfigFileState,
    ExclusiveFile,
    ForwardLease,
    ForwardRecord,
    FileIdentity,
    ProcessSupervisionResult,
    RunBinding,
    SeedSource,
    WorkerControl,
    WorkerHandles,
    binding_digest,
    bind_record,
    build_config_ownership,
    canonical_json_bytes,
    create_activation_pipe,
    exclusive_create,
    file_identity_from_fd,
    file_identity_from_path,
    inspect_owned_config,
    insert_config_marker,
    send_activation,
    shutdown_worker,
    supervise_process,
    write_owned_file,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.build_alas_patch_series import check_generated_patch
from scripts.python.run_alas_event_task_live_validation import (
    MATERIALIZED_ALAS_CAPABILITY_ID,
    MATERIALIZED_ALAS_CANONICAL_SOURCE_SHA256,
    MATERIALIZED_ALAS_CHANGED,
    MATERIALIZED_ALAS_CONTROL_ENV,
    MATERIALIZED_ALAS_LOADED_SCHEMA,
    MATERIALIZED_ALAS_LOADER_ID,
    MATERIALIZED_ALAS_MODULE_NAME,
    MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
    MATERIALIZED_ALAS_UNPROVEN,
    EVENT_SP_TEMPLATE_CHANGED,
    EVENT_SP_TEMPLATE_SHA256,
    EVENT_SP_TEMPLATE_UNPROVEN,
    RUN_METHODS,
    _classify_event_sp_run_error,
    _clock_delta_seconds,
    _configure,
    _event_sp_clean_start_stop,
    _event_sp_seed_name,
    _event_sp_attempt_observation,
    _execution_budgets,
    _failure_isolated_worker_cleanup,
    _finish_worker_terminal,
    _finalize_parent_resources,
    _confirm_verified_map_operation_loaded,
    _install_verified_map_operation_importer,
    _limit_resources,
    _materialization_control_record,
    _materialized_alas_proof,
    _materialized_alas_support_classification,
    _normalized_ast_sha256,
    _parent_fallback_cleanup,
    _public_error,
    _public_json_bytes,
    _supervise_event_sp,
    _admit_event_sp_template,
    _terminal_wrapper,
    _total_deadline,
    _recover_inherited_dock_full,
    _recover_inherited_preparation,
    _read_worker_event_sp_template,
    _stage_difficulty,
    _validate_event_sp_auto_search_evidence,
    _validate_worker_result,
    _wait_for_startup_surface,
    _worker_materialization_admission,
    main as runner_main,
    run as run_task,
)

TEST_TOKEN = b"alas-headless-test-token-32byte!"[:32]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ALAS_ROOT = PROJECT_ROOT.parent / "AzurLaneAutoScript-upstream-readonly"
PINNED_ALAS_COMMIT = "81ccf63b4540f00241628c82a58c02c7a2bb11af"
CANONICAL_ALAS_PATCH = (
    PROJECT_ROOT / "integration/alas/0001-semantic-oracle-hooks.patch"
)


def authoritative_materialized_map_operation() -> str:
    check_generated_patch(
        PROJECT_ROOT / "integration/alas/series/series.json",
        CANONICAL_ALAS_PATCH,
        root=PROJECT_ROOT,
    )
    with tempfile.TemporaryDirectory(prefix="alas-materialized-test-") as directory:
        root = Path(directory).resolve()
        target = root / "module/map/map_operation.py"
        target.parent.mkdir(parents=True)
        original = subprocess.run(
            [
                "git",
                "-C",
                str(PINNED_ALAS_ROOT),
                "show",
                f"{PINNED_ALAS_COMMIT}:module/map/map_operation.py",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
        target.write_bytes(original)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "apply",
                "--include=module/map/map_operation.py",
                "--whitespace=nowarn",
                str(CANONICAL_ALAS_PATCH),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return target.read_text(encoding="utf-8")


MATERIALIZED_MAP_OPERATION_POSITIVE = authoritative_materialized_map_operation()
PINNED_TEMPLATE_BYTES = subprocess.run(
    [
        "git",
        "-C",
        str(PINNED_ALAS_ROOT),
        "show",
        f"{PINNED_ALAS_COMMIT}:config/template.json",
    ],
    check=True,
    capture_output=True,
    timeout=30,
).stdout
if hashlib.sha256(PINNED_TEMPLATE_BYTES).hexdigest() != (
    "2de0a47643d9ad73417473f66be75dadcc1a82e11d405e1f2421ade3e31eaced"
):
    raise RuntimeError("pinned ALAS template fixture digest changed")

MATERIALIZED_MAP_OPERATION_STALE = MATERIALIZED_MAP_OPERATION_POSITIVE.replace(
    "                                if semantic_adapter.campaign_fleet_preparation_required():\n"
    "                                    self.fleet_preparation()\n",
    "                                self.fleet_preparation()\n",
    1,
)


def write_materialized_map_operation(
    alas_root: Path, source: str = MATERIALIZED_MAP_OPERATION_POSITIVE
) -> Path:
    target = alas_root / "module" / "map" / "map_operation.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8", newline="\n")
    if source == MATERIALIZED_MAP_OPERATION_POSITIVE:
        template = alas_root / "config" / "template.json"
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_bytes(PINNED_TEMPLATE_BYTES)
    return target


def replace_authoritative_once(old: str, new: str) -> str:
    return replace_source_once(MATERIALIZED_MAP_OPERATION_POSITIVE, old, new)


def replace_source_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise AssertionError("authoritative materialization mutation is not unique")
    return source.replace(old, new, 1)


def loaded_materialization(proof: dict[str, str], *, load_count: int = 1):
    return {
        "schema": MATERIALIZED_ALAS_LOADED_SCHEMA,
        "capability_id": MATERIALIZED_ALAS_CAPABILITY_ID,
        "loader_id": MATERIALIZED_ALAS_LOADER_ID,
        "module_name": MATERIALIZED_ALAS_MODULE_NAME,
        "relative_path": "module/map/map_operation.py",
        "canonical_source_sha256": proof["canonical_source_sha256"],
        "semantic_branch_sha256": proof["semantic_branch_sha256"],
        "support_classification": _materialized_alas_support_classification(proof),
        "load_count": load_count,
        "proof": proof,
    }


def semantic_branch_digest(source: str) -> str:
    tree = ast.parse(source)
    map_operation = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MapOperation"
    )
    enter_map = next(
        node
        for node in map_operation.body
        if isinstance(node, ast.FunctionDef) and node.name == "enter_map"
    )
    branch = next(
        node
        for node in ast.walk(enter_map)
        if isinstance(node, ast.If)
        and any(
            isinstance(candidate, ast.Attribute)
            and candidate.attr == "campaign_pre_sortie_active"
            for candidate in ast.walk(node.test)
        )
    )
    return _normalized_ast_sha256(branch)


def synthetic_ownership(binding: RunBinding):
    root = binding.config_path.parent
    return build_config_ownership(
        binding,
        config_root=root,
        root_identity=file_identity_from_path(root),
        initial_identity=FileIdentity(1, 11),
        control_identity=FileIdentity(1, 12),
    )


def synthetic_seed_source(binding: RunBinding) -> SeedSource:
    root = binding.config_path.parent
    return SeedSource(
        capability="alas.eventsp.pinned-template/v1",
        seed_name="template",
        path=root / "template.json",
        root_path=root,
        root_identity=file_identity_from_path(root),
        identity=FileIdentity(1, 13),
        size=50013,
        sha256=("2de0a47643d9ad73417473f66be75dadcc1a82e11d405e1f2421ade3e31eaced"),
    )


def synthetic_materialization_control(binding: RunBinding) -> dict[str, object]:
    return {
        "schema": "alas-headless.test-materialization-control/v1",
        "run_id": binding.run_id,
        "task": binding.task,
        "stage": binding.stage,
        "event": binding.event,
        "deadline_seconds": binding.deadline_seconds,
        "parent_pid": binding.parent_pid,
        "alas_root": str(binding.config_path.parent.parent),
        "proof": {"fixture": True},
    }


def synthetic_execution_budgets() -> dict[str, int]:
    return {
        "stage_entry": 1,
        "fleet_mutation": 4,
        "sortie": 1,
        "combat": 0,
        "grid_click": 0,
        "viewport_swipe": 0,
        "camera_positioning": 0,
        "recovery_total": 0,
    }


def bind_test_control(control: WorkerControl) -> WorkerControl:
    control.bind_activation_token(TEST_TOKEN, verified=False)
    return control


class AlasEventTaskLiveValidationTests(unittest.TestCase):
    def test_limit_resources_do_not_read_event_points_from_main_page(self):
        oracle = Mock()
        self.assertEqual(
            _limit_resources(
                oracle, {"main_page": True, "event_page": False}
            ),
            (None, None),
        )
        oracle.event_points.assert_not_called()
        oracle.campaign_oil.assert_not_called()

    def test_limit_resources_read_both_values_from_event_page(self):
        oracle = Mock()
        oracle.event_points.return_value = 17180
        oracle.campaign_oil.return_value = 10925
        self.assertEqual(
            _limit_resources(
                oracle, {"main_page": False, "event_page": True}
            ),
            (17180, 10925),
        )

    def test_clock_delta_compares_absolute_instants(self):
        self.assertEqual(
            _clock_delta_seconds(
                "2026-08-26T20:24:41+08:00",
                "2026-08-26T12:24:40+0000",
            ),
            1.0,
        )

    @staticmethod
    def event_sp_args(**overrides):
        values = {
            "task": "EventSp",
            "stage": "SP",
            "use_auto_search": True,
            "stage_entry_budget": 1,
            "fleet_mutation_budget": 4,
            "sortie_budget": 1,
            "combat_budget": 0,
            "viewport_swipe_budget": 0,
            "camera_positioning_budget": 0,
            "recovery_total": 0,
            "total_deadline_seconds": 120,
            "seed_config": "template",
            "event": "event_20260813_cn",
            "serial": "emulator-5580",
            "driver_revision": "a" * 40,
            "adb": "adb",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def event_sp_evidence():
        receipt = SimpleNamespace(
            semantic_id="reward/campaign-total/exit",
            generation=40,
            path=(
                "UICamera/Canvas/UIMain/LevelStageTotalRewardPanel(Clone)/"
                "Window/Fixed/ButtonExit"
            ),
        )
        sortie = SimpleNamespace(
            stage_code="sp",
            sortie_generation=10,
            map_generation=20,
            map_root_path="UICamera/Canvas/UIMain/CombatUIStandard(Clone)",
        )
        completion = SimpleNamespace(
            stage_code="sp",
            combat_auto_proven=True,
            passive_after_sortie=True,
            combat_auto_generation=30,
            result_generation=40,
            result_path=receipt.path,
            result_exit_receipt=receipt,
        )
        attempt = {
            "generation": 51,
            "path": (
                "UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/Battle/"
                "MapItems/List/Item(Clone)/Selected/Count"
            ),
            "text": "0/1",
        }
        return sortie, completion, attempt

    def validate_event_sp(self, **overrides):
        sortie, completion, attempt = self.event_sp_evidence()
        values = {
            "task": "EventSp",
            "stage": "SP",
            "use_auto_search": True,
            "sortie_proof": sortie,
            "completion_proof": completion,
            "final_generation": 50,
            "final_surface": {"event_page": True},
            "run_count_before": 1,
            "run_count_after": 0,
            "attempt_observation": attempt,
        }
        values.update(overrides)
        return _validate_event_sp_auto_search_evidence(**values)

    @staticmethod
    def seed(task):
        return {
            "Alas": {
                "Emulator": {
                    "Serial": "auto",
                    "ScreenshotMethod": "auto",
                    "ControlMethod": "MaaTouch",
                }
            },
            task: {
                "Scheduler": {"Command": task, "Enable": False},
                "Campaign": {},
                "StopCondition": {},
                "Fleet": {},
                "Submarine": {},
                "HpControl": {},
                **(
                    {"EventDaily": {}}
                    if task in {"EventA", "EventB", "EventC", "EventD"}
                    else {}
                ),
            },
        }

    def test_direct_event_uses_explicit_stage(self):
        self.assertEqual(RUN_METHODS["EventB"], "event_b")
        self.assertEqual(RUN_METHODS["EventSp"], "event_sp")
        payload = _configure(
            self.seed("Event2"),
            serial="emulator-5580",
            task="Event2",
            event="event_20260813_cn",
            stage="B1",
            use_auto_search=False,
        )
        target = payload["Event2"]
        self.assertEqual(target["Campaign"]["Name"], "B1")
        self.assertEqual(target["Campaign"]["Event"], "event_20260813_cn")
        self.assertEqual(target["StopCondition"]["RunCount"], 1)
        self.assertEqual(target["Fleet"]["Fleet2"], 0)
        self.assertEqual(target["Submarine"]["Mode"], "do_not_use")
        self.assertEqual(
            payload["Alas"]["Emulator"]["Serial"],
            "emulator-5580",
        )
        self.assertEqual(
            payload["Alas"]["Emulator"]["ScreenshotMethod"],
            "ADB",
        )
        self.assertEqual(
            payload["Alas"]["Emulator"]["ControlMethod"],
            "ADB",
        )

    def test_daily_event_uses_single_stage_filter(self):
        payload = _configure(
            self.seed("EventC"),
            serial="emulator-5580",
            task="EventC",
            event="event_20260813_cn",
            stage="C1",
            use_auto_search=False,
        )
        target = payload["EventC"]
        self.assertEqual(target["Campaign"]["Name"], "dynamic")
        self.assertEqual(target["EventDaily"]["StageFilter"], "C1")
        self.assertEqual(target["EventDaily"]["LastStage"], 0)
        self.assertEqual(_stage_difficulty("C1"), "hard")
        self.assertEqual(_stage_difficulty("D3"), "hard")
        self.assertEqual(_stage_difficulty("A1"), "normal")
        self.assertEqual(_stage_difficulty("SP"), "normal")

    def test_auto_search_uses_two_reviewed_role_fleets(self):
        payload = _configure(
            self.seed("Event2"),
            serial="emulator-5580",
            task="Event2",
            event="event_20260813_cn",
            stage="A1",
            use_auto_search=True,
        )
        target = payload["Event2"]
        self.assertEqual(target["Fleet"]["Fleet1"], 1)
        self.assertEqual(target["Fleet"]["Fleet2"], 2)
        self.assertEqual(
            target["Fleet"]["FleetOrder"],
            "fleet1_mob_fleet2_boss",
        )

    def test_task_balancer_isolation_is_written_into_temporary_seed(self):
        seed = self.seed("Event")
        seed["Restart"] = {
            "Scheduler": {
                "Command": "Restart",
                "Enable": True,
                "NextRun": "2020-01-01 00:00:00",
            }
        }
        payload = _configure(
            seed,
            serial="emulator-5580",
            task="Event",
            event="event_20260813_cn",
            stage="D3",
            use_auto_search=True,
            isolate_task_scheduler=True,
        )
        self.assertTrue(payload["Event"]["Scheduler"]["Enable"])
        self.assertFalse(payload["Restart"]["Scheduler"]["Enable"])
        self.assertTrue(seed["Restart"]["Scheduler"]["Enable"])

    def test_event_sp_budgets_are_explicit_fail_closed_and_do_not_leak(self):
        environment_before = dict(os.environ)
        expected = {
            "stage_entry": 1,
            "fleet_mutation": 4,
            "sortie": 1,
            "combat": 0,
            "grid_click": 0,
            "viewport_swipe": 0,
            "camera_positioning": 0,
            "recovery_total": 0,
        }

        self.assertEqual(_execution_budgets(self.event_sp_args()), expected)
        for overrides in (
            {"use_auto_search": False},
            {"stage": "A1"},
            {"stage_entry_budget": None},
            {"fleet_mutation_budget": 0},
            {"fleet_mutation_budget": 5},
            {"sortie_budget": True},
            {"combat_budget": -1},
            {"viewport_swipe_budget": 1},
            {"camera_positioning_budget": 1},
            {"recovery_total": 1},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _execution_budgets(self.event_sp_args(**overrides))
                self.assertEqual(dict(os.environ), environment_before)

        self.assertEqual(_execution_budgets(self.event_sp_args()), expected)
        self.assertEqual(dict(os.environ), environment_before)

    def test_event_sp_deadline_is_explicit_strict_and_precedes_other_preflight(self):
        self.assertEqual(_total_deadline(self.event_sp_args()), 120)
        for value in (None, True, "120", 119, 1801, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _total_deadline(self.event_sp_args(total_deadline_seconds=value))
        for task in ("EventB", "EventC", "EventD"):
            self.assertIsNone(
                _total_deadline(
                    SimpleNamespace(
                        task=task,
                        use_auto_search=False,
                        total_deadline_seconds=None,
                    )
                )
            )

        source = __import__(
            "scripts.python.run_alas_event_task_live_validation",
            fromlist=["run"],
        )
        text = __import__("inspect").getsource(source.run)
        self.assertLess(text.index("_total_deadline(args)"), text.index("resolve()"))
        self.assertLess(text.index("_total_deadline(args)"), text.index("_load_json"))
        self.assertLess(text.index("_total_deadline(args)"), text.index("write_text"))

    def test_event_sp_seed_is_exact_template_and_rejects_before_side_effects(self):
        self.assertEqual(_event_sp_seed_name(self.event_sp_args()), "template")
        for value in (
            None,
            "semantic_e2e",
            "Template",
            "TEMPLATE",
            "./template",
            "config/template",
            "config\\template",
            "template.json",
            Path("template"),
        ):
            probes = [Mock() for _ in range(5)]
            with self.subTest(value=value), self.assertRaises(ValueError):
                _supervise_event_sp(
                    self.event_sp_args(seed_config=value),
                    job_factory=probes[0],
                    forward_inventory=probes[1],
                    verified_pid=probes[2],
                    temporary_directory=probes[3],
                    popen_factory=probes[4],
                )
            for probe in probes:
                probe.assert_not_called()

    def test_template_preflight_rejects_unsafe_bytes_before_runtime_side_effects(self):
        cases = {
            "missing": None,
            "structural": b"{}\n",
            "duplicate": b'{"EventSp":{},"EventSp":{}}\n',
            "nonfinite": b'{"value":NaN}\n',
            "non_utf8": b"\xff\xfe",
            "bom": b"\xef\xbb\xbf{}\n",
            "oversize": b"{" + b" " * (2 * 1024 * 1024) + b"}",
        }
        for case, replacement in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                write_materialized_map_operation(root)
                template = root / "config" / "template.json"
                if replacement is None:
                    template.unlink()
                else:
                    template.write_bytes(replacement)
                job_factory = Mock()
                forward_inventory = Mock()
                verified_pid = Mock()
                popen_factory = Mock()
                temporary_directory = Mock()
                result = _supervise_event_sp(
                    self.event_sp_args(alas_root=root),
                    job_factory=job_factory,
                    forward_inventory=forward_inventory,
                    verified_pid=verified_pid,
                    popen_factory=popen_factory,
                    temporary_directory=temporary_directory,
                )
                self.assertFalse(result["passed"])
                self.assertEqual(
                    result["run_error"]["classification"],
                    EVENT_SP_TEMPLATE_UNPROVEN,
                )
                for operation in (
                    job_factory,
                    forward_inventory,
                    verified_pid,
                    popen_factory,
                    temporary_directory,
                ):
                    operation.assert_not_called()
                self.assertFalse((root / "config" / "semantic_e2e.json").exists())

    def test_structurally_compatible_template_drift_is_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            template = root / "config" / "template.json"
            template.write_bytes(PINNED_TEMPLATE_BYTES + b"\n")

            seed_file, source, value = _admit_event_sp_template(root)
            try:
                self.assertNotEqual(source.sha256, EVENT_SP_TEMPLATE_SHA256)
                self.assertIn("EventSp", value)
            finally:
                seed_file.close_parent()

    @unittest.skipUnless(os.name == "nt", "Windows hardlink seed contract")
    def test_template_preflight_rejects_hardlink_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            template = root / "config" / "template.json"
            alias = root / "config" / "template.alias"
            os.link(template, alias)
            job_factory = Mock()
            result = _supervise_event_sp(
                self.event_sp_args(alas_root=root), job_factory=job_factory
            )
            self.assertEqual(
                result["run_error"]["classification"], EVENT_SP_TEMPLATE_UNPROVEN
            )
            job_factory.assert_not_called()
            self.assertTrue(template.exists())
            self.assertTrue(alias.exists())

    def test_template_preflight_rejects_noncanonical_root_before_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            (root / "shadow").mkdir()
            drifted = root / "shadow" / ".."
            job_factory = Mock()
            result = _supervise_event_sp(
                self.event_sp_args(alas_root=drifted), job_factory=job_factory
            )
            self.assertEqual(
                result["run_error"]["classification"], EVENT_SP_TEMPLATE_UNPROVEN
            )
            job_factory.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows reparse seed contract")
    def test_template_preflight_rejects_reparse_without_skipping_other_root_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            template = root / "config" / "template.json"
            target = root / "template-target.json"
            target.write_bytes(template.read_bytes())
            template.unlink()
            try:
                os.symlink(target, template)
            except OSError as exc:
                self.skipTest(
                    "symlink privilege unavailable: {0}".format(type(exc).__name__)
                )
            job_factory = Mock()
            result = _supervise_event_sp(
                self.event_sp_args(alas_root=root), job_factory=job_factory
            )
            self.assertEqual(
                result["run_error"]["classification"], EVENT_SP_TEMPLATE_UNPROVEN
            )
            job_factory.assert_not_called()
            self.assertTrue(target.exists())

    def test_exact_pinned_template_admission_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            template = root / "config" / "template.json"
            before = template.read_bytes()
            seed_file, source, value = _admit_event_sp_template(root)
            try:
                self.assertEqual(source.seed_name, "template")
                self.assertEqual(source.sha256, EVENT_SP_TEMPLATE_SHA256)
                self.assertIn("EventSp", value)
            finally:
                seed_file.close_parent()
            self.assertEqual(template.read_bytes(), before)
            self.assertFalse((root / "config" / "semantic_e2e.json").exists())

    def test_pinned_seed_and_config_reject_distinct_same_path_root_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            seed_file, source, _value = _admit_event_sp_template(root)
            try:
                run_id = uuid.uuid4().hex
                binding = RunBinding(
                    run_id=run_id,
                    token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                    task="EventSp",
                    stage="SP",
                    event="event_20260813_cn",
                    deadline_seconds=120,
                    parent_pid=1,
                    parent_identity="1:1",
                    worker_pid=2,
                    config_path=source.root_path
                    / ("_codex_event_live_eventsp_" + run_id + ".json"),
                    control_path=root / "control.json",
                    result_path=root / "result.json",
                    cleanup_path=root / "cleanup.json",
                    lease_path=root / "lease.json",
                )
                ownership = synthetic_ownership(binding)
                with self.assertRaisesRegex(ValueError, "root identity"):
                    WorkerControl(
                        binding,
                        ownership,
                        replace(source, root_identity=FileIdentity(9, 9)),
                        "emulator-5580",
                        2703,
                        (),
                        WorkerHandles(100, 101, 102, 103, 104, 105),
                        synthetic_materialization_control(binding),
                        synthetic_execution_budgets(),
                    )
            finally:
                seed_file.close_parent()

    def test_worker_seed_admission_rejects_real_root_replacement_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            seed_file, source, _value = _admit_event_sp_template(root)
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=source.root_path
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                source,
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            control.bind_activation_token(TEST_TOKEN, verified=True)
            seed_file.close_parent()
            original = root / "config-original"
            source.root_path.rename(original)
            source.root_path.mkdir()
            inherited_read = Mock(return_value=(PINNED_TEMPLATE_BYTES, source.identity))
            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.read_bytes_handle",
                    inherited_read,
                ),
                self.assertRaisesRegex(RuntimeError, EVENT_SP_TEMPLATE_CHANGED),
            ):
                _read_worker_event_sp_template(
                    control, self.event_sp_args(alas_root=root)
                )
            inherited_read.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows inherited seed handle contract")
    def test_worker_consumes_exact_inherited_template_handle_without_path_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            template = root / "config" / "template.json"
            before = template.read_bytes()
            seed_file, source, _value = _admit_event_sp_template(root)
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root
                / "config"
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            seed_handle = seed_file.create_child_handle()
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                source,
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, seed_handle),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            control.bind_activation_token(TEST_TOKEN, verified=True)
            try:
                with self.assertRaises(PermissionError):
                    template.write_bytes(before)
                value = _read_worker_event_sp_template(
                    control, self.event_sp_args(alas_root=root)
                )
                seed_file.child_handle = -1
                self.assertEqual(value["EventSp"]["Scheduler"]["Command"], "EventSp")
                with self.assertRaises(PermissionError):
                    template.unlink()
            finally:
                if seed_file.child_handle >= 0:
                    seed_file.close_child_handle()
                seed_file.close_parent()
            self.assertEqual(template.read_bytes(), before)
            self.assertFalse((root / "config" / "semantic_e2e.json").exists())

    def test_worker_rejects_seed_control_path_hash_and_identity_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root
                / "config"
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            source = synthetic_seed_source(binding)
            cases = {
                "path": (
                    replace(source, path=source.root_path / "other.json"),
                    source.identity,
                    EVENT_SP_TEMPLATE_UNPROVEN,
                ),
                "hash": (
                    replace(source, sha256="0" * 64),
                    source.identity,
                    EVENT_SP_TEMPLATE_CHANGED,
                ),
                "identity": (
                    source,
                    FileIdentity(9, 9),
                    EVENT_SP_TEMPLATE_CHANGED,
                ),
            }
            for label, (candidate, inherited_identity, classification) in cases.items():
                control = WorkerControl(
                    binding,
                    synthetic_ownership(binding),
                    candidate,
                    "emulator-5580",
                    2703,
                    (),
                    WorkerHandles(100, 101, 102, 103, 104, 105),
                    synthetic_materialization_control(binding),
                    synthetic_execution_budgets(),
                )
                control.bind_activation_token(TEST_TOKEN, verified=True)
                with (
                    self.subTest(label=label),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.read_bytes_handle",
                        return_value=(PINNED_TEMPLATE_BYTES, inherited_identity),
                    ),
                    self.assertRaisesRegex(RuntimeError, classification),
                ):
                    _read_worker_event_sp_template(
                        control, self.event_sp_args(alas_root=root)
                    )

    def test_direct_event_sp_auto_search_cannot_bypass_worker_activation(self):
        args = self.event_sp_args(
            alas_root=Path("must-not-be-resolved"),
            serial="emulator-5580",
            adb="adb",
            driver_revision="a" * 40,
            seed_config="template",
            event="event_20260813_cn",
        )
        with self.assertRaisesRegex(RuntimeError, "supervised worker activation"):
            run_task(args)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            self_signed = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(self_signed)
            with self.assertRaisesRegex(RuntimeError, "live activation authority"):
                run_task(args, worker_control=self_signed)

    def test_event_sp_budget_preflight_precedes_config_and_alas_construction(self):
        source = __import__(
            "scripts.python.run_alas_event_task_live_validation",
            fromlist=["run"],
        )
        text = __import__("inspect").getsource(source.run)

        self.assertLess(text.index("_execution_budgets(args)"), text.index("resolve()"))
        self.assertLess(
            text.index("_execution_budgets(args)"), text.index("_load_json")
        )
        self.assertLess(
            text.index("_execution_budgets(args)"), text.index("write_text")
        )
        self.assertLess(
            text.index("_execution_budgets(args)"),
            text.index("AzurLaneAutoScript"),
        )

    def test_non_sp_event_budget_defaults_and_recovery_remain_isolated(self):
        for task in ("EventB", "EventC", "EventD"):
            with self.subTest(task=task):
                budgets = _execution_budgets(
                    SimpleNamespace(
                        task=task,
                        stage=task[-1] + "1",
                        use_auto_search=False,
                    )
                )
                self.assertEqual(budgets["fleet_mutation"], 6)
                self.assertEqual(budgets["combat"], 12)
                self.assertEqual(budgets["viewport_swipe"], 4)
                self.assertIsNone(budgets["recovery_total"])

    def test_materialized_fleet_noop_guard_accepts_authoritative_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = write_materialized_map_operation(root)
            self.assertEqual(
                target.read_text(encoding="utf-8").count("self.fleet_preparation()"),
                2,
            )

            proof = _materialized_alas_proof(root)

            self.assertEqual(proof["capability_id"], MATERIALIZED_ALAS_CAPABILITY_ID)
            self.assertEqual(proof["relative_path"], "module/map/map_operation.py")
            self.assertEqual(
                proof["semantic_branch_sha256"],
                MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
            )
            self.assertEqual(
                MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
                "a0ac35cb40e6ad29711c0200598a77a18c88ec0060666adace3d46f30301f4d6",
            )
            self.assertEqual(
                proof["canonical_source_sha256"],
                MATERIALIZED_ALAS_CANONICAL_SOURCE_SHA256,
            )
            self.assertEqual(
                MATERIALIZED_ALAS_CANONICAL_SOURCE_SHA256,
                "0ddeec74cde1a94e686830d0504f07fc789aab85b7552073f4226779992e57f8",
            )
            self.assertEqual(
                proof["canonical_source_sha256"],
                hashlib.sha256(target.read_bytes()).hexdigest(),
            )
            canonical = target.read_bytes()
            self.assertNotIn(b"\r", canonical)
            target.write_bytes(canonical.replace(b"\n", b"\r\n"))
            self.assertEqual(_materialized_alas_proof(root), proof)
            target.write_bytes(b"\xef\xbb\xbf" + canonical)
            with self.assertRaisesRegex(RuntimeError, MATERIALIZED_ALAS_UNPROVEN):
                _materialized_alas_proof(root)

    def test_materialized_fleet_noop_guard_rejects_unsupported_ast_drift(self):
        guarded = (
            "                                if semantic_adapter.campaign_fleet_preparation_required():\n"
            "                                    self.fleet_preparation()\n"
        )
        confirm = "                                semantic_adapter.confirm_campaign_fleet_selection()\n"
        moved_after_confirm = replace_authoritative_once(
            guarded + confirm, confirm + guarded
        )
        enter_map_header = (
            "    def enter_map(self, button, mode='normal', "
            "skip_first_screenshot=True):\n"
        )
        duplicate_method = replace_authoritative_once(
            enter_map_header,
            "    def enter_map(self):\n        pass\n\n" + enter_map_header,
        )
        direct_assignment = (
            "        self.map_clear_percentage_timer.reset()\n"
            "        semantic_adapter = getattr(self.device, "
            "'semantic_adapter', None)\n"
        )
        semantic_log = (
            "                    logger.info("
            "'Semantic pre-sortie: scan fleet preparation')\n"
        )
        class_wrapper = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            enter_map_header,
            "    def _reviewer_fleet_wrapper(self):\n"
            "        self.fleet_preparation()\n\n" + enter_map_header,
        )
        class_wrapper = replace_source_once(
            class_wrapper,
            semantic_log,
            "                    self._reviewer_fleet_wrapper()\n" + semantic_log,
        )
        module_wrapper = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            "class MapOperation(",
            "def reviewer_fleet_wrapper(owner):\n"
            "    owner.fleet_preparation()\n\n\n"
            "class MapOperation(",
        )
        module_wrapper = replace_source_once(
            module_wrapper,
            semantic_log,
            "                    reviewer_fleet_wrapper(self)\n" + semantic_log,
        )
        decorated_wrapper = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            "class MapOperation(",
            "def reviewer_decorator(function):\n"
            "    return function\n\n\n"
            "@reviewer_decorator\n"
            "def reviewer_decorated_wrapper(owner):\n"
            "    owner.fleet_preparation()\n\n\n"
            "class MapOperation(",
        )
        decorated_wrapper = replace_source_once(
            decorated_wrapper,
            semantic_log,
            "                    reviewer_decorated_wrapper(self)\n" + semantic_log,
        )
        callable_wrapper = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            "class MapOperation(",
            "class ReviewerFleetCallable:\n"
            "    def __call__(self, owner):\n"
            "        owner.fleet_preparation()\n\n\n"
            "REVIEWER_FLEET_CALLABLE = ReviewerFleetCallable()\n\n\n"
            "class MapOperation(",
        )
        callable_wrapper = replace_source_once(
            callable_wrapper,
            semantic_log,
            "                    REVIEWER_FLEET_CALLABLE(self)\n" + semantic_log,
        )
        branch_tail = (
            "                    if (\n"
            "                        not self.is_in_auto_search_menu()\n"
            "                        and semantic_adapter.campaign_map_preparation_committed()\n"
            "                    ):\n"
            "                        continue\n"
        )
        call_target_override = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            enter_map_header,
            "    def handle_auto_search_setting(self):\n"
            "        self.fleet_preparation()\n\n" + enter_map_header,
        )
        decorated_enter_map = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            "class MapOperation(",
            "def reviewer_enter_map_decorator(function):\n"
            "    return function\n\n\n"
            "class MapOperation(",
        )
        decorated_enter_map = replace_source_once(
            decorated_enter_map,
            enter_map_header,
            "    @reviewer_enter_map_decorator\n" + enter_map_header,
        )
        dunder_getattribute_override = replace_source_once(
            MATERIALIZED_MAP_OPERATION_POSITIVE,
            enter_map_header,
            "    def __getattribute__(self, name):\n"
            "        if name == 'handle_auto_search_setting':\n"
            "            return lambda: self.fleet_preparation()\n"
            "        return super().__getattribute__(name)\n\n" + enter_map_header,
        )
        module_monkeypatch = (
            MATERIALIZED_MAP_OPERATION_POSITIVE
            + "\nMapOperation.handle_auto_search_setting = (\n"
            "    lambda self: self.fleet_preparation())\n"
        )
        unchanged_branch_attacks = {
            "class-call-target-override": call_target_override,
            "enter-map-decorator": decorated_enter_map,
            "dunder-getattribute-override": dunder_getattribute_override,
            "module-monkeypatch": module_monkeypatch,
        }
        compatible_drift = {
            "comment-byte-drift": (
                MATERIALIZED_MAP_OPERATION_POSITIVE
                + "\n# unreviewed qualification comment\n"
            ),
            "whitespace-byte-drift": replace_authoritative_once(
                "import cv2\n", "import cv2  \n"
            ),
        }
        for source in unchanged_branch_attacks.values():
            self.assertEqual(
                semantic_branch_digest(source),
                MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
            )
        for source in compatible_drift.values():
            self.assertEqual(
                semantic_branch_digest(source),
                MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
            )
        variants = {
            "syntax": "class MapOperation:\n    def enter_map(:\n        pass\n",
            "duplicate-class": MATERIALIZED_MAP_OPERATION_POSITIVE * 2,
            "duplicate-method": duplicate_method,
            "stale-unconditional": MATERIALIZED_MAP_OPERATION_STALE,
            "guard-inversion": replace_authoritative_once(
                "if semantic_adapter.campaign_fleet_preparation_required():",
                "if not semantic_adapter.campaign_fleet_preparation_required():",
            ),
            "guard-alias": replace_authoritative_once(
                "semantic_adapter.campaign_fleet_preparation_required()",
                "adapter.campaign_fleet_preparation_required()",
            ),
            "adapter-alias": replace_authoritative_once(
                direct_assignment,
                "        self.map_clear_percentage_timer.reset()\n"
                "        semantic_adapter = adapter\n",
            ),
            "dead-adapter-assignment": replace_authoritative_once(
                direct_assignment,
                "        self.map_clear_percentage_timer.reset()\n"
                "        if False:\n"
                "            semantic_adapter = getattr(\n"
                "                self.device, 'semantic_adapter', None)\n",
            ),
            "wrong-authorize-receiver": replace_authoritative_once(
                "semantic_adapter.authorize_campaign_fleet_preparation(",
                "adapter.authorize_campaign_fleet_preparation(",
            ),
            "wrong-authorize-method": replace_authoritative_once(
                "authorize_campaign_fleet_preparation(",
                "authorize_campaign_fleets(",
            ),
            "moved-after-confirm": moved_after_confirm,
            "sibling-unconditional": replace_authoritative_once(
                confirm,
                "                                self.fleet_preparation()\n" + confirm,
            ),
            "getattr-unconditional": replace_authoritative_once(
                confirm,
                "                                getattr(\n"
                "                                    self, 'fleet_preparation')()\n"
                + confirm,
            ),
            "alias-unconditional": replace_authoritative_once(
                confirm,
                "                                prepare = self.fleet_preparation\n"
                "                                prepare()\n" + confirm,
            ),
            "lambda-wrapper": replace_authoritative_once(
                confirm,
                "                                prepare = (\n"
                "                                    lambda: self.fleet_preparation())\n"
                "                                prepare()\n" + confirm,
            ),
            **unchanged_branch_attacks,
            "class-level-wrapper-call": class_wrapper,
            "module-level-wrapper-call": module_wrapper,
            "split-getattr-name": replace_authoritative_once(
                semantic_log,
                "                    getattr(\n"
                "                        self, 'fleet_' + 'preparation')()\n"
                + semantic_log,
            ),
            "dunder-dict": replace_authoritative_once(
                semantic_log,
                "                    self.__dict__['fleet_preparation']()\n"
                + semantic_log,
            ),
            "dunder-getattribute": replace_authoritative_once(
                semantic_log,
                "                    self.__getattribute__(\n"
                "                        'fleet_preparation')()\n" + semantic_log,
            ),
            "decorated-wrapper-call": decorated_wrapper,
            "callable-object": callable_wrapper,
            "added-call-before-authorized": replace_authoritative_once(
                semantic_log,
                "                    self.unreviewed_before()\n" + semantic_log,
            ),
            "added-call-after-authorized": replace_authoritative_once(
                branch_tail,
                branch_tail + "                    self.unreviewed_after()\n",
            ),
            "downstream-missing": replace_authoritative_once(
                "                                self.handle_auto_search_setting()\n",
                "",
            ),
            "rollback-stale-frame": replace_authoritative_once(
                "                                    self.enter_map_cancel("
                "skip_first_screenshot=False)\n",
                "                                    self.enter_map_cancel()\n",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaisesRegex(RuntimeError, MATERIALIZED_ALAS_UNPROVEN):
                _materialized_alas_proof(root)
            for label, source in variants.items():
                with self.subTest(label=label):
                    write_materialized_map_operation(root, source)
                    try:
                        _materialized_alas_proof(root)
                    except RuntimeError as exc:
                        self.assertRegex(str(exc), MATERIALIZED_ALAS_UNPROVEN)
                    else:
                        self.fail(f"unsupported materialized drift admitted: {label}")

            for label, source in compatible_drift.items():
                with self.subTest(label=label):
                    target = write_materialized_map_operation(root, source)
                    proof = _materialized_alas_proof(root)
                    self.assertEqual(
                        proof["canonical_source_sha256"],
                        hashlib.sha256(target.read_bytes()).hexdigest(),
                    )
                    self.assertEqual(
                        proof["semantic_branch_sha256"],
                        MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256,
                    )

    def test_materialized_guard_rejects_before_adb_temp_job_or_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root, MATERIALIZED_MAP_OPERATION_STALE)
            job_factory = Mock()
            forward_inventory = Mock()
            verified_pid = Mock()
            popen_factory = Mock()
            temporary_directory = Mock()

            result = _supervise_event_sp(
                self.event_sp_args(
                    alas_root=root,
                    serial="emulator-5580",
                    adb="adb",
                    driver_revision="a" * 40,
                    seed_config="template",
                    event="event_20260813_cn",
                ),
                job_factory=job_factory,
                forward_inventory=forward_inventory,
                verified_pid=verified_pid,
                popen_factory=popen_factory,
                temporary_directory=temporary_directory,
            )

            self.assertFalse(result["passed"])
            self.assertFalse(result["executed"])
            self.assertEqual(
                result["run_error"]["classification"], MATERIALIZED_ALAS_UNPROVEN
            )
            self.assertEqual(
                result["supervision"]["termination_mode"], "worker_not_started"
            )
            for operation in (
                job_factory,
                forward_inventory,
                verified_pid,
                popen_factory,
                temporary_directory,
            ):
                operation.assert_not_called()
            self.assertFalse((root / "config").exists())

    def test_worker_rechecks_bound_materialization_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config_root = root / "config"
            config_root.mkdir()
            target = write_materialized_map_operation(root)
            proof = _materialized_alas_proof(root)
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=config_root
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            record = _materialization_control_record(
                proof,
                run_id=run_id,
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                alas_root=root,
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                record,
                synthetic_execution_budgets(),
            )
            control.bind_activation_token(TEST_TOKEN, verified=True)
            environment = {
                MATERIALIZED_ALAS_CONTROL_ENV: json.dumps(
                    record, separators=(",", ":"), sort_keys=True
                )
            }
            args = self.event_sp_args(alas_root=root)

            verified = _worker_materialization_admission(
                environment, control=control, args=args
            )
            self.assertEqual(verified.proof, proof)
            self.assertEqual(verified.source, target.read_bytes())
            tampered = dict(record)
            tampered["proof"] = {
                **proof,
                "canonical_source_sha256": "0" * 64,
            }
            with self.assertRaisesRegex(RuntimeError, MATERIALIZED_ALAS_UNPROVEN):
                _worker_materialization_admission(
                    {
                        MATERIALIZED_ALAS_CONTROL_ENV: json.dumps(
                            tampered, separators=(",", ":"), sort_keys=True
                        )
                    },
                    control=control,
                    args=args,
                )

            target.write_text(
                MATERIALIZED_MAP_OPERATION_STALE, encoding="utf-8", newline="\n"
            )
            with self.assertRaisesRegex(RuntimeError, MATERIALIZED_ALAS_CHANGED):
                _worker_materialization_admission(
                    environment, control=control, args=args
                )

    def test_verified_loader_ignores_replaced_source_and_timestamp_valid_pyc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config_root = root / "config"
            config_root.mkdir()
            target = write_materialized_map_operation(root)
            proof = _materialized_alas_proof(root)
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=config_root
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            record = _materialization_control_record(
                proof,
                run_id=run_id,
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                alas_root=root,
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                record,
                synthetic_execution_budgets(),
            )
            control.bind_activation_token(TEST_TOKEN, verified=True)
            verified = _worker_materialization_admission(
                {
                    MATERIALIZED_ALAS_CONTROL_ENV: json.dumps(
                        record, separators=(",", ":"), sort_keys=True
                    )
                },
                control=control,
                args=self.event_sp_args(alas_root=root),
            )
            importer = _install_verified_map_operation_importer(verified)
            malicious = b"LOADED_FROM_DRIFT = True\n"
            malicious += b"#" * (len(verified.source) - len(malicious))
            target.write_bytes(malicious)
            pyc = Path(importlib.util.cache_from_source(str(target)))
            pyc.parent.mkdir(exist_ok=True)
            py_compile.compile(str(target), cfile=str(pyc), doraise=True)
            self.assertTrue(pyc.is_file())

            class Timer:
                def __init__(self, *_args, **_kwargs):
                    pass

            def package(name: str, path: Path | None = None) -> ModuleType:
                item = ModuleType(name)
                item.__path__ = [] if path is None else [str(path)]
                return item

            modules = {
                "module": package("module", root / "module"),
                "module.map": package("module.map", root / "module/map"),
                "module.base": package("module.base"),
                "module.handler": package("module.handler"),
                "module.retire": package("module.retire"),
                "module.ui": package("module.ui"),
                "cv2": ModuleType("cv2"),
                "module.base.timer": ModuleType("module.base.timer"),
                "module.exception": ModuleType("module.exception"),
                "module.handler.fast_forward": ModuleType(
                    "module.handler.fast_forward"
                ),
                "module.handler.mystery": ModuleType("module.handler.mystery"),
                "module.logger": ModuleType("module.logger"),
                "module.map.assets": ModuleType("module.map.assets"),
                "module.map.map_fleet_preparation": ModuleType(
                    "module.map.map_fleet_preparation"
                ),
                "module.retire.retirement": ModuleType("module.retire.retirement"),
                "module.ui.assets": ModuleType("module.ui.assets"),
            }
            modules["module.base.timer"].Timer = Timer
            for name in ("CampaignEnd", "RequestHumanTakeover", "ScriptEnd"):
                setattr(modules["module.exception"], name, type(name, (Exception,), {}))
            modules["module.handler.fast_forward"].FastForwardHandler = type(
                "FastForwardHandler", (), {}
            )
            modules["module.handler.mystery"].MysteryHandler = type(
                "MysteryHandler", (), {}
            )
            modules["module.logger"].logger = SimpleNamespace()
            modules["module.map.assets"].__all__ = ()
            modules["module.map.map_fleet_preparation"].FleetPreparation = type(
                "FleetPreparation", (), {}
            )
            modules["module.retire.retirement"].Retirement = type("Retirement", (), {})
            modules["module.ui.assets"].BACK_ARROW = object()
            modules["module.ui.assets"].DAILY_CHECK = object()
            try:
                sys.modules.pop(MATERIALIZED_ALAS_MODULE_NAME, None)
                with patch.dict(sys.modules, modules, clear=False):
                    loaded = importlib.import_module(MATERIALIZED_ALAS_MODULE_NAME)
                    self.assertFalse(hasattr(loaded, "LOADED_FROM_DRIFT"))
                    receipt = _confirm_verified_map_operation_loaded(importer)
                    self.assertEqual(receipt, loaded_materialization(proof))
                    reloaded = importlib.reload(loaded)
                    self.assertIs(reloaded.__loader__, importer)
                    receipt = _confirm_verified_map_operation_loaded(importer)
                    self.assertEqual(
                        receipt, loaded_materialization(proof, load_count=2)
                    )
            finally:
                sys.modules.pop(MATERIALIZED_ALAS_MODULE_NAME, None)
                if importer in sys.meta_path:
                    sys.meta_path.remove(importer)

    def test_materialization_check_is_inside_total_deadline_and_before_side_effects(
        self,
    ):
        source = __import__(
            "scripts.python.run_alas_event_task_live_validation",
            fromlist=["_supervise_event_sp_impl"],
        )
        text = __import__("inspect").getsource(source._supervise_event_sp_impl)
        deadline = text.index("absolute_deadline = monotonic() + deadline_seconds")
        root_resolve = text.index("alas_root = provided_root.resolve")
        admission = text.index("materialization_proof = _materialized_alas_proof")
        seed_admission = text.index("_admit_event_sp_template", admission)
        second_deadline = text.index(
            "remaining_seconds(absolute_deadline, monotonic)", seed_admission
        )
        self.assertLess(deadline, root_resolve)
        self.assertLess(root_resolve, admission)
        self.assertLess(admission, seed_admission)
        self.assertLess(seed_admission, second_deadline)
        self.assertLess(second_deadline, text.index("job = job_factory()"))
        self.assertLess(admission, text.index("job = job_factory()"))
        self.assertLess(admission, text.index("starting_forwards = forward_inventory("))
        self.assertLess(admission, text.index("process = popen_factory("))

    def test_deadline_expiry_after_materialization_never_creates_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_materialized_map_operation(root)
            job_factory = Mock()
            forward_inventory = Mock()
            verified_pid = Mock()
            popen_factory = Mock()

            result = _supervise_event_sp(
                self.event_sp_args(
                    alas_root=root,
                    serial="emulator-5580",
                    adb="adb",
                    driver_revision="a" * 40,
                    seed_config="template",
                    event="event_20260813_cn",
                ),
                job_factory=job_factory,
                forward_inventory=forward_inventory,
                verified_pid=verified_pid,
                popen_factory=popen_factory,
                monotonic=Mock(side_effect=(0.0, 0.0, 121.0)),
            )

            self.assertFalse(result["passed"])
            self.assertFalse(result["executed"])
            self.assertEqual(
                result["supervision"]["termination_mode"], "worker_not_started"
            )
            job_factory.assert_not_called()
            forward_inventory.assert_not_called()
            verified_pid.assert_not_called()
            popen_factory.assert_not_called()

    def test_worker_cleanup_attempts_every_item_after_session_close_failure(self):
        class Session:
            def close(self):
                raise RuntimeError("cleanup-" + TEST_TOKEN.hex().upper())

        # _close_semantic_session intentionally uses instance.__dict__ to avoid
        # constructing a lazy ALAS device during cleanup.
        instance = SimpleNamespace(device=SimpleNamespace(semantic_adapter=Session()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "owned.json"
            config.write_text("{}", encoding="utf-8")
            previous = os.environ.get("ALAS_SEMANTIC_MODE")
            os.environ["ALAS_SEMANTIC_MODE"] = "changed"
            try:
                report = _failure_isolated_worker_cleanup(
                    instance=instance,
                    prior_cwd=Path.cwd(),
                    config_path=config,
                    prior_env={"ALAS_SEMANTIC_MODE": previous},
                )
            finally:
                if previous is None:
                    os.environ.pop("ALAS_SEMANTIC_MODE", None)
                else:
                    os.environ["ALAS_SEMANTIC_MODE"] = previous
            self.assertFalse(report["completed"])
            self.assertEqual(report["errors"][0]["item"], "semantic_session_close")
            self.assertFalse(config.exists())
            self.assertIn("cwd_restore", report["actions"])
            self.assertIn("temp_config_remove", report["actions"])
            self.assertIn("environment_restore", report["actions"])
            serialized = json.dumps(report, sort_keys=True)
            self.assertNotIn(TEST_TOKEN.hex(), serialized)
            self.assertNotIn(TEST_TOKEN.hex().upper(), serialized)

    def test_worker_cleanup_preserves_stop_for_top_level_after_all_items(self):
        runner_stop = __import__(
            "alas_headless.runner_supervision", fromlist=["RunnerStopRequested"]
        ).RunnerStopRequested

        class Session:
            def close(self):
                raise runner_stop("scripted cooperative stop during cleanup")

        instance = SimpleNamespace(device=SimpleNamespace(semantic_adapter=Session()))
        terminal_errors = []
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "owned.json"
            config.write_text("{}", encoding="utf-8")
            report = _failure_isolated_worker_cleanup(
                instance=instance,
                prior_cwd=Path.cwd(),
                config_path=config,
                prior_env={},
                terminal_errors=terminal_errors,
            )
        self.assertFalse(report["completed"])
        self.assertFalse(config.exists())
        self.assertIn("cwd_restore", report["actions"])
        self.assertIn("temp_config_remove", report["actions"])
        self.assertIn("environment_restore", report["actions"])
        self.assertEqual(len(terminal_errors), 1)
        self.assertIsInstance(terminal_errors[0], runner_stop)

    def test_system_exit_is_overridden_by_stop_during_final_config_inspection(self):
        runner_stop = __import__(
            "alas_headless.runner_supervision", fromlist=["RunnerStopRequested"]
        ).RunnerStopRequested
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            status = SimpleNamespace(
                phase="pre_init",
                execution_state="not_started",
                cleanup=None,
                seed_handle_consumed=False,
            )
            written = []
            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.close_inherited_handle"
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.inspect_owned_config",
                    side_effect=runner_stop("stop during config inspection"),
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_json_handle"
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                    side_effect=lambda _handle, payload: written.append(payload),
                ),
            ):
                rc = _finish_worker_terminal(control, status, SystemExit(1))
            self.assertEqual(rc, 124)
            self.assertIsNotNone(status.cleanup)
            self.assertIn(
                "temp_config_state_capture",
                [item["item"] for item in status.cleanup["errors"]],
            )
            wrapper = json.loads(written[0].decode("utf-8"))["payload"]
            self.assertEqual(wrapper["terminal_kind"], "stop_requested")
            terminal = wrapper["terminal"]["payload"]
            self.assertEqual(
                terminal["classification"],
                "runner.worker_stop_requested",
            )

    @staticmethod
    def _supervisor_args(alas_root):
        alas_root = Path(alas_root)
        if not alas_root.is_absolute():
            raise AssertionError("test ALAS root must be an isolated absolute path")
        source = alas_root / "module" / "map" / "map_operation.py"
        if not source.exists():
            write_materialized_map_operation(Path(alas_root))
        return AlasEventTaskLiveValidationTests.event_sp_args(
            alas_root=alas_root,
            serial="emulator-5580",
            adb="adb",
            driver_revision="a" * 40,
            seed_config="template",
            event="event_20260813_cn",
        )

    def test_supervised_deadline_activates_only_after_containment_and_preserves_old_forward(
        self,
    ):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            old = ForwardRecord(
                "emulator-5580", "tcp:2078", "localabstract:alas.g3.2703"
            )
            inventory = Mock(side_effect=((old,), (old,)))
            control_root = Path(control_parent).resolve() / "control"
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: setattr(job, "closed", True)
            process = SimpleNamespace(pid=43210, poll=lambda: 124)
            activation_calls = []

            def activate(pipe, _control, _path, **_kwargs):
                self.assertTrue(job.assigned)
                activation_calls.append("activated")
                pipe.close_parent_write()

            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=inventory,
                verified_pid=Mock(return_value=2703),
                remove_forward=Mock(),
                supervise=Mock(
                    return_value=ProcessSupervisionResult(
                        reason="deadline",
                        termination_mode="deadline_terminated_job",
                        returncode=124,
                        termination_confirmed=True,
                        cooperative_stop_requested=True,
                        forced_terminate=True,
                        forced_kill=False,
                    )
                ),
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=activate,
                identity_getter=lambda pid: f"{pid}:12345",
            )

            self.assertEqual(activation_calls, ["activated"])
            self.assertFalse(result["passed"])
            self.assertIsNone(result["executed"])
            self.assertEqual(result["execution_state"], "unknown")
            self.assertEqual(
                result["run_error"]["classification"],
                "event_sp.runner_deadline_exceeded",
            )
            self.assertTrue(result["supervision"]["deadline_triggered"])
            self.assertIn(
                "observer_forward_already_absent",
                result["supervision"]["parent_cleanup"]["actions"],
            )

    def test_parent_final_root_identity_admission_precedes_activation(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: setattr(job, "closed", True)
            process = SimpleNamespace(pid=43210, poll=lambda: 1)
            stopped = ProcessSupervisionResult(
                reason="supervision_error",
                termination_mode="root_identity_rejected",
                returncode=1,
                termination_confirmed=True,
                cooperative_stop_requested=True,
                forced_terminate=False,
                forced_kill=False,
            )
            activation = Mock()
            supervisor = Mock()
            shutdown = Mock(return_value=stopped)
            with patch(
                "scripts.python.run_alas_event_task_live_validation.validate_worker_control_root",
                side_effect=RuntimeError("config root identity changed"),
            ):
                result = _supervise_event_sp(
                    self._supervisor_args(alas_root),
                    worker_argv=["python", "worker.py"],
                    popen_factory=Mock(return_value=process),
                    forward_inventory=Mock(return_value=()),
                    verified_pid=Mock(return_value=2703),
                    supervise=supervisor,
                    shutdown=shutdown,
                    monotonic=Mock(return_value=10.0),
                    temporary_directory=Mock(
                        side_effect=lambda **_kwargs: (
                            control_root.mkdir() or str(control_root)
                        )
                    ),
                    job_factory=Mock(return_value=job),
                    activation_sender=activation,
                    identity_getter=lambda pid: f"{pid}:12345",
                )
            self.assertTrue(job.assigned)
            activation.assert_not_called()
            supervisor.assert_not_called()
            shutdown.assert_called_once_with(process, job, reason="supervision_error")
            self.assertFalse(result["passed"])
            self.assertFalse(result["executed"])
            self.assertEqual(result["execution_state"], "not_started")
            retained = list(
                (alas_root / "config").glob("_codex_event_live_eventsp_*.json")
            )
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0].read_bytes(), b"")

    @unittest.skipUnless(os.name == "nt", "Windows non-reading worker contract")
    def test_fixed_activation_cannot_block_before_stalled_worker_supervision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            alas_root = root / ("alas-" + "a" * 80)
            (alas_root / "config").mkdir(parents=True)
            control_root = root / ("control-" + "c" * 80)
            self.assertGreater(len(str(alas_root)), 100)
            self.assertGreater(len(str(control_root)), 100)
            old = ForwardRecord(
                "emulator-5580", "tcp:2078", "localabstract:alas.g3.2703"
            )
            inventory = Mock(side_effect=((old,), (old,)))
            remove = Mock()
            supervisor_reached = []
            child_code = (
                "import signal,time;"
                "signal.signal(signal.SIGBREAK,signal.SIG_IGN);"
                "time.sleep(60)"
            )

            def create_control_root(**_kwargs):
                control_root.mkdir()
                return str(control_root)

            def bounded_supervise(process, job, **_kwargs):
                supervisor_reached.append(time.monotonic())
                return supervise_process(
                    process,
                    job,
                    absolute_deadline=time.monotonic() + 0.2,
                    shutdown=lambda owned_process, owned_job, reason: shutdown_worker(
                        owned_process,
                        owned_job,
                        reason=reason,
                        cleanup_grace_seconds=0.2,
                        force_stop_grace_seconds=1.0,
                    ),
                )

            started = time.monotonic()
            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=[sys.executable, "-c", child_code],
                forward_inventory=inventory,
                verified_pid=Mock(return_value=2703),
                remove_forward=remove,
                supervise=bounded_supervise,
                temporary_directory=create_control_root,
            )
            elapsed = time.monotonic() - started

            self.assertEqual(len(supervisor_reached), 1)
            self.assertLess(elapsed, 5.0)
            self.assertFalse(result["passed"])
            self.assertIsNone(result["executed"])
            self.assertEqual(result["execution_state"], "unknown")
            self.assertEqual(
                result["run_error"]["classification"],
                "event_sp.runner_deadline_exceeded",
            )
            self.assertTrue(result["supervision"]["termination_confirmed"])
            self.assertIn(
                result["supervision"]["termination_mode"],
                ("deadline_cooperative", "deadline_terminated_job"),
            )
            self.assertTrue(control_root.exists())
            self.assertIn(
                "runner.cleanup.config_final_state_malformed",
                result["validation_errors"],
            )
            self.assertEqual(
                len(
                    list(
                        (alas_root / "config").glob("_codex_event_live_eventsp_*.json")
                    )
                ),
                1,
            )
            remove.assert_not_called()
            self.assertEqual(inventory.call_count, 2)

    def test_parent_cleanup_removes_only_exact_bound_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            alas_config = root / "alas" / "config"
            alas_config.mkdir(parents=True)
            control_root = root / "control"
            control_root.mkdir()
            run_id = uuid.uuid4().hex
            paths = {
                "config": alas_config
                / ("_codex_event_live_eventsp_" + run_id + ".json"),
                "control": control_root / "control.json",
                "result": control_root / "result.json",
                "cleanup": control_root / "cleanup.json",
                "lease": control_root / "lease.json",
            }
            owned_files = {
                label: exclusive_create(path, inheritable=False)
                for label, path in paths.items()
            }
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=paths["config"],
                control_path=paths["control"],
                result_path=paths["result"],
                cleanup_path=paths["cleanup"],
                lease_path=paths["lease"],
            )
            old = ForwardRecord(
                "emulator-5580", "tcp:2078", "localabstract:alas.g3.2703"
            )
            exact = ForwardRecord(
                "emulator-5580", "tcp:12339", "localabstract:alas.g3.2703"
            )
            control = WorkerControl(
                binding,
                build_config_ownership(
                    binding,
                    config_root=alas_config,
                    root_identity=file_identity_from_path(alas_config),
                    initial_identity=file_identity_from_fd(owned_files["config"].fd),
                    control_identity=file_identity_from_fd(owned_files["control"].fd),
                ),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (old,),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            write_owned_file(
                owned_files["control"], canonical_json_bytes(control.to_mapping())
            )
            config_payload = {"EventSp": {"Storage": {"Storage": {}}}}
            insert_config_marker(
                config_payload, control.binding, control.config_ownership
            )
            write_owned_file(
                owned_files["config"], canonical_json_bytes(config_payload)
            )
            owned_files["config"].close_parent()
            config_state = inspect_owned_config(control)
            worker_cleanup = {
                "completed": True,
                "actions": ["temp_config_state_captured"],
                "errors": [],
                "temp_config_path": str(binding.config_path),
                "temp_config_present_after": True,
                "config_state": config_state.to_mapping(),
            }
            lease = ForwardLease(
                binding=binding,
                serial=control.serial,
                local=exact.local,
                remote=exact.remote,
                verified_game_pid=2703,
                starting_forwards=(old,),
            )
            write_owned_file(
                owned_files["lease"],
                canonical_json_bytes(lease.to_bound_mapping(control)),
            )
            inventory = Mock(side_effect=((old, exact), (old,)))
            remove = Mock()
            report = _parent_fallback_cleanup(
                control,
                owned_files=owned_files,
                control_root=control_root,
                termination_confirmed=True,
                worker_activated=True,
                worker_cleanup=worker_cleanup,
                cleanup_deadline=100.0,
                monotonic=lambda: 0.0,
                adb="adb",
                forward_inventory=inventory,
                remove_forward=remove,
            )
            self.assertTrue(report["completed"])
            remove.assert_called_once_with("adb", exact, timeout_seconds=100.0)
            self.assertFalse(paths["config"].exists())
            self.assertFalse(control_root.exists())
            self.assertIn("observer_forward_removed", report["actions"])

    def test_completed_worker_requires_full_bound_result(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            job = SimpleNamespace(assigned=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: None
            process = SimpleNamespace(pid=43210, poll=lambda: 0)
            captured = []
            created = {}

            def make_file(path, *, inheritable):
                item = exclusive_create(path, inheritable=inheritable)
                created[path.name] = item
                return item

            def activate(pipe, control, _path, **_kwargs):
                captured.append(control)
                pipe.close_parent_write()

            def complete(_process, _job, **_kwargs):
                control_object = captured[0]
                binding = control_object.binding.to_mapping()
                config_payload = {"EventSp": {"Storage": {"Storage": {}}}}
                insert_config_marker(
                    config_payload,
                    control_object.binding,
                    control_object.config_ownership,
                )
                Path(binding["config_path"]).write_text(
                    json.dumps(config_payload), encoding="utf-8"
                )
                config_state = inspect_owned_config(control_object)
                cleanup = {
                    "completed": True,
                    "actions": ["environment_restore", "temp_config_state_captured"],
                    "errors": [],
                    "temp_config_path": binding["config_path"],
                    "temp_config_present_after": True,
                    "config_state": config_state.to_mapping(),
                }
                cleanup_wrapper = bind_record(
                    control_object,
                    RECORD_CLEANUP,
                    {
                        "schema": WORKER_CLEANUP_SCHEMA,
                        "binding": binding,
                        "binding_digest": binding_digest(control_object.binding),
                        "cleanup": cleanup,
                    },
                )
                write_owned_file(
                    created["worker-cleanup.json"],
                    canonical_json_bytes(cleanup_wrapper),
                )
                payload = {
                    "schema": "alas-headless.event-task-live-validation/v1",
                    "passed": True,
                    "executed": True,
                    "capability_promotion": True,
                    "started_at": "2026-08-24T00:00:00Z",
                    "finished_at": "2026-08-24T00:01:00Z",
                    "task": "EventSp",
                    "stage": "SP",
                    "event": "event_20260813_cn",
                    "serial": "emulator-5580",
                    "driver_revision": "a" * 40,
                    "use_auto_search": True,
                    "materialized_alas": loaded_materialization(
                        _materialized_alas_proof(alas_root)
                    ),
                    "run_result": True,
                    "run_error": None,
                    "validation_errors": [],
                    "raw_input_fallback_used": False,
                    "budgets": {},
                    "event_sp_auto_search_evidence": {},
                    "final_surface": {"event_page": True},
                    "worker_cleanup": cleanup,
                }
                write_owned_file(
                    created["worker-result.json"],
                    canonical_json_bytes(
                        bind_record(
                            control_object,
                            RECORD_RESULT,
                            {
                                "schema": WORKER_RESULT_SCHEMA,
                                "binding": binding,
                                "binding_digest": binding_digest(
                                    control_object.binding
                                ),
                                "terminal_kind": "completed",
                                "result": payload,
                            },
                        )
                    ),
                )
                return ProcessSupervisionResult(
                    reason="completed",
                    termination_mode="completed",
                    returncode=0,
                    termination_confirmed=True,
                    cooperative_stop_requested=False,
                    forced_terminate=False,
                    forced_kill=False,
                )

            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=Mock(side_effect=((), ())),
                verified_pid=Mock(return_value=2703),
                remove_forward=Mock(),
                supervise=complete,
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=activate,
                exclusive_file_factory=make_file,
                identity_getter=lambda pid: f"{pid}:12345",
            )
            self.assertTrue(result["passed"])
            self.assertTrue(result["executed"])
            self.assertTrue(result["capability_promotion"])
            self.assertEqual(
                result["materialized_alas"]["capability_id"],
                MATERIALIZED_ALAS_CAPABILITY_ID,
            )
            self.assertEqual(
                result["materialized_alas"]["canonical_source_sha256"],
                _materialized_alas_proof(alas_root)["canonical_source_sha256"],
            )
            self.assertEqual(
                result["materialized_alas_admission"],
                _materialized_alas_proof(alas_root),
            )
            materialization_control = result["supervision"]["materialization_control"]
            self.assertEqual(
                materialization_control["proof"],
                result["materialized_alas_admission"],
            )

    def test_minimal_and_cross_run_worker_results_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            minimal = {
                "schema": WORKER_RESULT_SCHEMA,
                "binding": binding.to_mapping(),
                "result": {"passed": True, "executed": True, "run_id": run_id},
            }
            with self.assertRaises(ValueError):
                _validate_worker_result(
                    minimal, control, self._supervisor_args(root), {}
                )
            mutations = {
                "token_digest": "0" * 64,
                "task": "EventB",
                "stage": "sp",
                "event": "event_other",
                "deadline_seconds": 121,
                "parent_pid": 3,
                "parent_identity": "3:3",
                "worker_pid": 4,
                "config_path": str(root / "foreign-config.json"),
                "result_path": str(root / "foreign-result.json"),
                "cleanup_path": str(root / "foreign-cleanup.json"),
                "lease_path": str(root / "foreign-lease.json"),
            }
            for field, changed_value in mutations.items():
                wrong = dict(binding.to_mapping())
                wrong[field] = changed_value
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, "binding"),
                ):
                    _validate_worker_result(
                        bind_record(
                            control,
                            RECORD_RESULT,
                            {
                                "schema": WORKER_RESULT_SCHEMA,
                                "binding": wrong,
                                "binding_digest": binding_digest(binding),
                                "terminal_kind": "completed",
                                "result": {},
                            },
                        ),
                        control,
                        self._supervisor_args(root),
                        {},
                    )

    def test_preexisting_run_paths_are_never_overwritten_or_deleted(self):
        run_id = "1" * 32
        for collision in ("config", "control", "result", "lease"):
            with (
                self.subTest(collision=collision),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                alas_root = root / "alas"
                (alas_root / "config").mkdir(parents=True)
                control_root = root / "control"
                control_root.mkdir()
                paths = {
                    "config": alas_root
                    / "config"
                    / ("_codex_event_live_eventsp_" + run_id + ".json"),
                    "control": control_root / "worker-control.json",
                    "result": control_root / "worker-result.json",
                    "lease": control_root / "forward-lease.json",
                }
                paths[collision].write_text("owned-by-somebody-else", encoding="utf-8")
                job = SimpleNamespace(closed=False)
                job.close = lambda: setattr(job, "closed", True)
                with patch(
                    "scripts.python.run_alas_event_task_live_validation.uuid.uuid4",
                    return_value=SimpleNamespace(hex=run_id),
                ):
                    result = _supervise_event_sp(
                        self._supervisor_args(alas_root),
                        forward_inventory=Mock(return_value=()),
                        verified_pid=Mock(return_value=2703),
                        temporary_directory=Mock(return_value=str(control_root)),
                        job_factory=Mock(return_value=job),
                    )
                self.assertFalse(result["passed"])
                self.assertEqual(
                    result["run_error"]["classification"], "runner.setup_failed"
                )
                self.assertEqual(
                    paths[collision].read_text(encoding="utf-8"),
                    "owned-by-somebody-else",
                )
                self.assertTrue(job.closed)

    def test_absolute_deadline_starts_before_preflight_and_timeouts_decrease(self):
        events = []
        clock_values = iter((10.0, 11.0, 12.0, 13.0, 14.0))
        alas_root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

        def clock():
            value = next(clock_values)
            events.append(("clock", value))
            return value

        job = SimpleNamespace()
        job.close = lambda: None

        def make_job():
            events.append(("job", None))
            return job

        def inventory(_adb, _serial, *, timeout_seconds):
            events.append(("inventory", timeout_seconds))
            return ()

        def pid(_adb, _serial, _package, *, timeout_seconds):
            events.append(("pid", timeout_seconds))
            raise RuntimeError("scripted pid failure")

        result = _supervise_event_sp(
            self._supervisor_args(alas_root),
            monotonic=clock,
            job_factory=make_job,
            forward_inventory=inventory,
            verified_pid=pid,
            temporary_directory=Mock(
                side_effect=AssertionError("temp creation must not occur")
            ),
        )
        self.assertEqual(events[0], ("clock", 10.0))
        self.assertEqual(events[1], ("clock", 11.0))
        self.assertEqual(events[2], ("clock", 12.0))
        self.assertEqual(events[3], ("job", None))
        self.assertIn(("inventory", 117.0), events)
        self.assertEqual(events[-2:], [("clock", 14.0), ("pid", 116.0)])
        self.assertEqual(next(item[1] for item in events if item[0] == "pid"), 116.0)
        self.assertEqual(result["run_error"]["classification"], "runner.setup_failed")

    def test_setup_ctrl_c_returns_distinct_receipt_without_temp_artifacts(self):
        alas_root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        job = SimpleNamespace(closed=False)
        job.close = lambda: setattr(job, "closed", True)
        result = _supervise_event_sp(
            self._supervisor_args(alas_root),
            monotonic=Mock(return_value=10.0),
            job_factory=Mock(return_value=job),
            forward_inventory=Mock(side_effect=KeyboardInterrupt()),
            temporary_directory=Mock(
                side_effect=AssertionError("temp creation must not occur")
            ),
        )
        self.assertEqual(result["run_error"]["classification"], "runner.interrupted")
        self.assertFalse(result["executed"])
        self.assertEqual(result["execution_state"], "not_started")
        self.assertTrue(job.closed)

    def test_control_serialization_failure_shuts_down_and_cleans_exact_artifacts(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            job = SimpleNamespace(assigned=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: None
            process = SimpleNamespace(pid=43210, poll=lambda: 1)
            stopped = ProcessSupervisionResult(
                reason="supervision_error",
                termination_mode="supervision_error_cooperative",
                returncode=1,
                termination_confirmed=True,
                cooperative_stop_requested=True,
                forced_terminate=False,
                forced_kill=False,
            )
            shutdown = Mock(return_value=stopped)
            activation = Mock()
            def fail_control_serialization(value):
                if value.get("purpose") == RECORD_WORKER_CONTROL:
                    raise TypeError("scripted serialization failure")
                return canonical_json_bytes(value)

            with patch(
                "scripts.python.run_alas_event_task_live_validation.canonical_json_bytes",
                side_effect=fail_control_serialization,
            ):
                result = _supervise_event_sp(
                    self._supervisor_args(alas_root),
                    worker_argv=["python", "worker.py"],
                    popen_factory=Mock(return_value=process),
                    forward_inventory=Mock(return_value=()),
                    verified_pid=Mock(return_value=2703),
                    monotonic=Mock(return_value=10.0),
                    temporary_directory=Mock(
                        side_effect=lambda **_kwargs: (
                            control_root.mkdir() or str(control_root)
                        )
                    ),
                    job_factory=Mock(return_value=job),
                    activation_sender=activation,
                    identity_getter=lambda pid: f"{pid}:12345",
                    shutdown=shutdown,
                )
            shutdown.assert_called_once_with(process, job, reason="supervision_error")
            activation.assert_not_called()
            self.assertEqual(
                result["run_error"]["classification"],
                "runner.worker_supervision_failed",
            )
            self.assertFalse(control_root.exists())
            self.assertFalse(
                any((alas_root / "config").glob("_codex_event_live_eventsp_*.json"))
            )

    def test_supervise_exception_always_enters_shutdown(self):
        for failure, reason, classification in (
            (
                RuntimeError("supervisor wait failed"),
                "supervision_error",
                "runner.worker_supervision_failed",
            ),
            (KeyboardInterrupt(), "interrupted", "runner.interrupted"),
        ):
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as alas_directory,
                tempfile.TemporaryDirectory() as control_parent,
            ):
                alas_root = Path(alas_directory).resolve()
                (alas_root / "config").mkdir()
                control_root = Path(control_parent).resolve() / "control"
                job = SimpleNamespace(assigned=False)
                job.assign = lambda _process: setattr(job, "assigned", True)
                job.active_process_count = lambda: 0
                job.close = lambda: None
                process = SimpleNamespace(pid=43210, poll=lambda: 1)
                stopped = ProcessSupervisionResult(
                    reason=reason,
                    termination_mode=reason + "_cooperative",
                    returncode=1,
                    termination_confirmed=True,
                    cooperative_stop_requested=True,
                    forced_terminate=False,
                    forced_kill=False,
                )
                shutdown = Mock(return_value=stopped)
                activation = Mock(
                    side_effect=lambda pipe, _control, _path, **_kwargs: (
                        pipe.close_parent_write()
                    )
                )
                result = _supervise_event_sp(
                    self._supervisor_args(alas_root),
                    worker_argv=["python", "worker.py"],
                    popen_factory=Mock(return_value=process),
                    forward_inventory=Mock(side_effect=((), ())),
                    verified_pid=Mock(return_value=2703),
                    supervise=Mock(side_effect=failure),
                    shutdown=shutdown,
                    monotonic=Mock(return_value=10.0),
                    temporary_directory=Mock(
                        side_effect=lambda **_kwargs: (
                            control_root.mkdir() or str(control_root)
                        )
                    ),
                    job_factory=Mock(return_value=job),
                    activation_sender=activation,
                    identity_getter=lambda pid: f"{pid}:12345",
                )
                shutdown.assert_called_once_with(process, job, reason=reason)
                self.assertEqual(result["run_error"]["classification"], classification)
                activation.assert_called_once()
                self.assertIsNone(result["executed"])
                self.assertEqual(result["execution_state"], "unknown")
                self.assertTrue(control_root.exists())
                self.assertIn(
                    "runner.cleanup.config_final_state_malformed",
                    result["validation_errors"],
                )

    def test_unconfirmed_worker_retains_artifacts_and_skips_forward_cleanup(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            job = SimpleNamespace(assigned=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: None
            process = SimpleNamespace(pid=43210, poll=lambda: None)
            inventory = Mock(return_value=())
            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=inventory,
                verified_pid=Mock(return_value=2703),
                supervise=Mock(
                    return_value=ProcessSupervisionResult(
                        reason="deadline",
                        termination_mode="deadline_unconfirmed",
                        returncode=None,
                        termination_confirmed=True,
                        cooperative_stop_requested=True,
                        forced_terminate=True,
                        forced_kill=False,
                    )
                ),
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=lambda pipe, _control, _path, **_kwargs: pipe.close_parent_write(),
                identity_getter=lambda pid: f"{pid}:12345",
            )
            self.assertEqual(inventory.call_count, 1)
            self.assertFalse(result["supervision"]["termination_confirmed"])
            self.assertIsNone(result["executed"])
            self.assertEqual(result["execution_state"], "unknown")
            self.assertIn(
                "runner.worker_termination_unconfirmed",
                result["validation_errors"],
            )
            retained = result["supervision"]["parent_cleanup"]["details"][
                "artifacts_retained"
            ]
            self.assertTrue(retained)
            self.assertTrue(all(Path(item).exists() for item in retained))

    def test_activation_full_delivery_then_raise_still_reconciles_exact_forward(self):
        class DeferredReadPipe:
            def __init__(self):
                self.inner = create_activation_pipe()
                self.read_handle = self.inner.read_handle
                self.write_fd = self.inner.write_fd
                self.read_close_calls = 0

            def close_parent_read(self):
                self.read_close_calls += 1
                if self.read_close_calls >= 2:
                    self.inner.close_parent_read()

            def close_parent_write(self):
                self.inner.close_parent_write()

        for failure, reason, classification in (
            (
                RuntimeError("raised after full activation EOF"),
                "supervision_error",
                "runner.worker_supervision_failed",
            ),
            (KeyboardInterrupt(), "interrupted", "runner.interrupted"),
        ):
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as alas_directory,
                tempfile.TemporaryDirectory() as control_parent,
            ):
                alas_root = Path(alas_directory).resolve()
                (alas_root / "config").mkdir()
                control_root = Path(control_parent).resolve() / "control"
                old = ForwardRecord(
                    "emulator-5580", "tcp:2078", "localabstract:alas.g3.2703"
                )
                exact = ForwardRecord(
                    "emulator-5580", "tcp:12339", "localabstract:alas.g3.2703"
                )
                inventory = Mock(side_effect=((old,), (old, exact), (old,)))
                remove = Mock()
                process = SimpleNamespace(pid=43210, poll=lambda: 1)
                job = SimpleNamespace(assigned=False, closed=False)
                job.assign = lambda _process: setattr(job, "assigned", True)
                job.active_process_count = lambda: 0
                job.close = lambda: setattr(job, "closed", True)
                activation = DeferredReadPipe()

                def deliver_then_raise(pipe, control, path, **kwargs):
                    send_activation(pipe, control, path, **kwargs)
                    raise failure

                def stop(_process, _job, *, reason):
                    return ProcessSupervisionResult(
                        reason=reason,
                        termination_mode=reason + "_cooperative",
                        returncode=1,
                        termination_confirmed=True,
                        cooperative_stop_requested=True,
                        forced_terminate=False,
                        forced_kill=False,
                    )

                result = _supervise_event_sp(
                    self._supervisor_args(alas_root),
                    worker_argv=["python", "worker.py"],
                    popen_factory=Mock(return_value=process),
                    forward_inventory=inventory,
                    verified_pid=Mock(return_value=2703),
                    remove_forward=remove,
                    shutdown=stop,
                    monotonic=Mock(return_value=10.0),
                    temporary_directory=Mock(
                        side_effect=lambda **_kwargs: (
                            control_root.mkdir() or str(control_root)
                        )
                    ),
                    job_factory=Mock(return_value=job),
                    activation_factory=Mock(return_value=activation),
                    activation_sender=deliver_then_raise,
                    identity_getter=lambda pid: f"{pid}:12345",
                )
                self.assertEqual(result["run_error"]["classification"], classification)
                self.assertIsNone(result["executed"])
                self.assertEqual(result["execution_state"], "unknown")
                remove.assert_called_once()
                self.assertEqual(remove.call_args.args[1], exact)
                self.assertEqual(inventory.call_count, 3)
                self.assertTrue(control_root.exists())
                self.assertIn(
                    "runner.cleanup.config_final_state_malformed",
                    result["validation_errors"],
                )
                self.assertTrue(job.closed)
                self.assertGreaterEqual(activation.read_close_calls, 2)

    def test_activation_delivery_exception_with_unconfirmed_death_retains_all(self):
        class DeferredReadPipe:
            def __init__(self):
                self.inner = create_activation_pipe()
                self.read_handle = self.inner.read_handle
                self.write_fd = self.inner.write_fd
                self.read_close_calls = 0

            def close_parent_read(self):
                self.read_close_calls += 1
                if self.read_close_calls >= 2:
                    self.inner.close_parent_read()

            def close_parent_write(self):
                self.inner.close_parent_write()

        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            activation = DeferredReadPipe()
            inventory = Mock(return_value=())
            process = SimpleNamespace(pid=43210, poll=lambda: None)
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 1
            job.close = lambda: setattr(job, "closed", True)

            def sender(pipe, control, path, **kwargs):
                send_activation(pipe, control, path, **kwargs)
                raise RuntimeError("raised after activation EOF")

            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=inventory,
                verified_pid=Mock(return_value=2703),
                remove_forward=Mock(),
                shutdown=Mock(
                    return_value=ProcessSupervisionResult(
                        reason="supervision_error",
                        termination_mode="supervision_error_unconfirmed",
                        returncode=None,
                        termination_confirmed=False,
                        cooperative_stop_requested=True,
                        forced_terminate=True,
                        forced_kill=False,
                    )
                ),
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_factory=Mock(return_value=activation),
                activation_sender=sender,
                identity_getter=lambda pid: f"{pid}:12345",
            )
            self.assertEqual(inventory.call_count, 1)
            self.assertIsNone(result["executed"])
            self.assertEqual(result["execution_state"], "unknown")
            self.assertIn(
                "runner.worker_termination_unconfirmed", result["validation_errors"]
            )
            retained = result["supervision"]["parent_cleanup"]["details"][
                "artifacts_retained"
            ]
            self.assertTrue(all(Path(item).exists() for item in retained))
            self.assertTrue(job.closed)

    def test_malformed_lease_scalar_is_stable_blocker_and_finalizes_handles(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            created = []
            captured = []

            def make_file(path, *, inheritable):
                item = exclusive_create(path, inheritable=inheritable)
                created.append(item)
                return item

            process = SimpleNamespace(pid=43210, poll=lambda: 124)
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: setattr(job, "closed", True)

            def completed(_process, _job, **_kwargs):
                binding = captured[0].binding.to_mapping()
                lease_file = next(
                    item for item in created if item.path.name == "forward-lease.json"
                )
                write_owned_file(
                    lease_file,
                    canonical_json_bytes(
                        {
                            "schema": "alas-headless.runner-forward-lease/v2",
                            "binding": binding,
                            "serial": "emulator-5580",
                            "local": 12339,
                            "remote": "localabstract:alas.g3.2703",
                            "verified_game_pid": 2703,
                            "starting_forwards": [],
                        }
                    ),
                )
                return ProcessSupervisionResult(
                    reason="deadline",
                    termination_mode="deadline_late_exit",
                    returncode=124,
                    termination_confirmed=True,
                    cooperative_stop_requested=False,
                    forced_terminate=False,
                    forced_kill=False,
                )

            inventory = Mock(return_value=())

            def activate(pipe, control, _path, **_kwargs):
                captured.append(control)
                pipe.close_parent_write()

            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=inventory,
                verified_pid=Mock(return_value=2703),
                supervise=completed,
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=activate,
                exclusive_file_factory=make_file,
                identity_getter=lambda pid: f"{pid}:12345",
            )
            self.assertIn(
                "runner.cleanup.forward_lease_malformed", result["validation_errors"]
            )
            self.assertEqual(inventory.call_count, 1)
            self.assertTrue(job.closed)
            self.assertTrue(all(item.fd == -1 for item in created))

    def test_missing_or_malformed_cleanup_and_result_are_execution_unknown(self):
        for malformed in ("cleanup", "result", "missing_cleanup", "missing_result"):
            with (
                self.subTest(malformed=malformed),
                tempfile.TemporaryDirectory() as alas_directory,
                tempfile.TemporaryDirectory() as control_parent,
            ):
                alas_root = Path(alas_directory).resolve()
                (alas_root / "config").mkdir()
                control_root = Path(control_parent).resolve() / "control"
                created = {}
                captured = []
                process = SimpleNamespace(pid=43210, poll=lambda: 0)
                job = SimpleNamespace(assigned=False, closed=False)
                job.assign = lambda _process: setattr(job, "assigned", True)
                job.active_process_count = lambda: 0
                job.close = lambda: setattr(job, "closed", True)

                def make_file(path, *, inheritable):
                    item = exclusive_create(path, inheritable=inheritable)
                    created[path.name] = item
                    return item

                def activate(pipe, control, _path, **_kwargs):
                    captured.append(control)
                    pipe.close_parent_write()

                def completed(_process, _job, **_kwargs):
                    control_object = captured[0]
                    binding = control_object.binding.to_mapping()
                    config_payload = {"EventSp": {"Storage": {"Storage": {}}}}
                    insert_config_marker(
                        config_payload,
                        control_object.binding,
                        control_object.config_ownership,
                    )
                    Path(binding["config_path"]).write_text(
                        json.dumps(config_payload), encoding="utf-8"
                    )
                    config_state = inspect_owned_config(control_object)
                    cleanup = {
                        "completed": True,
                        "actions": ["temp_config_state_captured"],
                        "errors": [],
                        "temp_config_path": binding["config_path"],
                        "temp_config_present_after": True,
                        "config_state": config_state.to_mapping(),
                    }
                    cleanup_wrapper = bind_record(
                        control_object,
                        RECORD_CLEANUP,
                        {
                            "schema": WORKER_CLEANUP_SCHEMA,
                            "binding": binding,
                            "binding_digest": binding_digest(control_object.binding),
                            "cleanup": cleanup,
                        },
                    )
                    if malformed == "cleanup":
                        cleanup_wrapper["binding"] = 7
                        cleanup_wrapper["cleanup"] = "scalar"
                    if malformed != "missing_cleanup":
                        write_owned_file(
                            created["worker-cleanup.json"],
                            canonical_json_bytes(cleanup_wrapper),
                        )
                    result_wrapper = bind_record(
                        control_object,
                        RECORD_RESULT,
                        {
                            "schema": WORKER_RESULT_SCHEMA,
                            "binding": binding,
                            "binding_digest": binding_digest(control_object.binding),
                            "terminal_kind": "completed",
                            "result": "scalar",
                        },
                    )
                    if malformed == "result":
                        result_wrapper["binding"] = 8
                    if malformed != "missing_result":
                        write_owned_file(
                            created["worker-result.json"],
                            canonical_json_bytes(result_wrapper),
                        )
                    return ProcessSupervisionResult(
                        reason="completed",
                        termination_mode="completed",
                        returncode=1,
                        termination_confirmed=True,
                        cooperative_stop_requested=False,
                        forced_terminate=False,
                        forced_kill=False,
                    )

                result = _supervise_event_sp(
                    self._supervisor_args(alas_root),
                    worker_argv=["python", "worker.py"],
                    popen_factory=Mock(return_value=process),
                    forward_inventory=Mock(side_effect=((), ())),
                    verified_pid=Mock(return_value=2703),
                    supervise=completed,
                    monotonic=Mock(return_value=10.0),
                    temporary_directory=Mock(
                        side_effect=lambda **_kwargs: (
                            control_root.mkdir() or str(control_root)
                        )
                    ),
                    job_factory=Mock(return_value=job),
                    activation_sender=activate,
                    exclusive_file_factory=make_file,
                    identity_getter=lambda pid: f"{pid}:12345",
                )
                self.assertFalse(result["passed"])
                self.assertIsNone(result["executed"])
                self.assertEqual(result["execution_state"], "unknown")
                self.assertTrue(job.closed)
                if malformed in ("cleanup", "missing_cleanup"):
                    self.assertTrue(control_root.exists())
                    self.assertIn(
                        "runner.cleanup.config_final_state_malformed",
                        result["validation_errors"],
                    )
                    self.assertIn(
                        "runner.cleanup.worker_status_malformed",
                        result["validation_errors"],
                    )
                else:
                    self.assertFalse(control_root.exists())
                    self.assertEqual(
                        result["run_error"]["classification"],
                        (
                            "runner.worker_result_missing_or_malformed"
                            if malformed == "missing_result"
                            else "runner.worker_result_identity_or_shape_mismatch"
                        ),
                    )

    def test_optional_json_path_check_and_read_errors_are_receipted(self):
        cases = ("path_check", "read")
        for case in cases:
            with (
                self.subTest(case=case),
                tempfile.TemporaryDirectory() as alas_directory,
                tempfile.TemporaryDirectory() as control_parent,
            ):
                alas_root = Path(alas_directory).resolve()
                (alas_root / "config").mkdir()
                control_root = Path(control_parent).resolve() / "control"
                created = {}
                process = SimpleNamespace(pid=43210, poll=lambda: 124)
                job = SimpleNamespace(assigned=False, closed=False)
                job.assign = lambda _process: setattr(job, "assigned", True)
                job.active_process_count = lambda: 0
                job.close = lambda: setattr(job, "closed", True)

                def make_file(path, *, inheritable):
                    item = exclusive_create(path, inheritable=inheritable)
                    created[path.name] = item
                    return item

                def completed(_process, _job, **_kwargs):
                    if case == "read":
                        write_owned_file(created["forward-lease.json"], b"{}")
                    return ProcessSupervisionResult(
                        reason="deadline",
                        termination_mode="deadline_late_exit",
                        returncode=124,
                        termination_confirmed=True,
                        cooperative_stop_requested=False,
                        forced_terminate=False,
                        forced_kill=False,
                    )

                patcher = (
                    patch.object(
                        ExclusiveFile,
                        "validate_master",
                        side_effect=OSError("owned handle validation failed"),
                    )
                    if case == "path_check"
                    else patch(
                        "scripts.python.run_alas_event_task_live_validation.read_owned_file",
                        side_effect=OSError("read failed"),
                    )
                )
                with patcher:
                    result = _supervise_event_sp(
                        self._supervisor_args(alas_root),
                        worker_argv=["python", "worker.py"],
                        popen_factory=Mock(return_value=process),
                        forward_inventory=Mock(return_value=()),
                        verified_pid=Mock(return_value=2703),
                        supervise=completed,
                        monotonic=Mock(return_value=10.0),
                        temporary_directory=Mock(
                            side_effect=lambda **_kwargs: (
                                control_root.mkdir() or str(control_root)
                            )
                        ),
                        job_factory=Mock(return_value=job),
                        activation_sender=lambda pipe, _control, _path, **_kwargs: pipe.close_parent_write(),
                        exclusive_file_factory=make_file,
                        identity_getter=lambda pid: f"{pid}:12345",
                    )
                self.assertFalse(result["passed"])
                self.assertTrue(job.closed)
                self.assertIn(
                    "runner.cleanup.forward_lease_malformed",
                    result["validation_errors"],
                )

    def test_post_supervision_cleanup_raise_and_keyboard_interrupt_finalize(self):
        for failure, target, expected in (
            (
                RuntimeError("cleanup exploded"),
                "scripts.python.run_alas_event_task_live_validation._parent_fallback_cleanup",
                "runner.cleanup.parent_cleanup_failed",
            ),
            (
                KeyboardInterrupt(),
                "scripts.python.run_alas_event_task_live_validation._optional_owned_json",
                "runner.interrupted",
            ),
            (
                KeyboardInterrupt(),
                "scripts.python.run_alas_event_task_live_validation._parent_fallback_cleanup",
                "runner.interrupted",
            ),
        ):
            with (
                self.subTest(expected=expected),
                tempfile.TemporaryDirectory() as alas_directory,
                tempfile.TemporaryDirectory() as control_parent,
            ):
                alas_root = Path(alas_directory).resolve()
                (alas_root / "config").mkdir()
                control_root = Path(control_parent).resolve() / "control"
                created = []

                def make_file(path, *, inheritable):
                    item = exclusive_create(path, inheritable=inheritable)
                    created.append(item)
                    return item

                process = SimpleNamespace(pid=43210, poll=lambda: 124)
                job = SimpleNamespace(assigned=False, closed=False)
                job.assign = lambda _process: setattr(job, "assigned", True)
                job.active_process_count = lambda: 0
                job.close = lambda: setattr(job, "closed", True)
                completed = ProcessSupervisionResult(
                    reason="deadline",
                    termination_mode="deadline_late_exit",
                    returncode=124,
                    termination_confirmed=True,
                    cooperative_stop_requested=False,
                    forced_terminate=False,
                    forced_kill=False,
                )
                with patch(target, side_effect=failure):
                    result = _supervise_event_sp(
                        self._supervisor_args(alas_root),
                        worker_argv=["python", "worker.py"],
                        popen_factory=Mock(return_value=process),
                        forward_inventory=Mock(return_value=()),
                        verified_pid=Mock(return_value=2703),
                        supervise=Mock(return_value=completed),
                        monotonic=Mock(return_value=10.0),
                        temporary_directory=Mock(
                            side_effect=lambda **_kwargs: (
                                control_root.mkdir() or str(control_root)
                            )
                        ),
                        job_factory=Mock(return_value=job),
                        activation_sender=lambda pipe, _control, _path, **_kwargs: pipe.close_parent_write(),
                        exclusive_file_factory=make_file,
                        identity_getter=lambda pid: f"{pid}:12345",
                    )
                self.assertTrue(job.closed)
                self.assertTrue(all(item.fd == -1 for item in created))
                if isinstance(failure, RuntimeError):
                    self.assertIn(expected, result["validation_errors"])
                else:
                    self.assertEqual(result["run_error"]["classification"], expected)

    def test_invalid_supervise_result_is_shutdown_and_receipted(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            process = SimpleNamespace(pid=43210, poll=lambda: 1)
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 0
            job.close = lambda: setattr(job, "closed", True)
            shutdown = Mock(
                return_value=ProcessSupervisionResult(
                    reason="supervision_error",
                    termination_mode="supervision_error_cooperative",
                    returncode=1,
                    termination_confirmed=True,
                    cooperative_stop_requested=True,
                    forced_terminate=False,
                    forced_kill=False,
                )
            )
            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=Mock(side_effect=((), ())),
                verified_pid=Mock(return_value=2703),
                supervise=Mock(return_value=None),
                shutdown=shutdown,
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=lambda pipe, _control, _path, **_kwargs: pipe.close_parent_write(),
                identity_getter=lambda pid: f"{pid}:12345",
            )
            shutdown.assert_called_once()
            self.assertEqual(
                result["run_error"]["classification"],
                "runner.worker_supervision_failed",
            )
            self.assertTrue(job.closed)

    def test_one_exclusive_close_failure_does_not_skip_other_finalizers(self):
        with (
            tempfile.TemporaryDirectory() as alas_directory,
            tempfile.TemporaryDirectory() as control_parent,
        ):
            alas_root = Path(alas_directory).resolve()
            (alas_root / "config").mkdir()
            control_root = Path(control_parent).resolve() / "control"
            created = []
            original_first_close = []

            def make_file(path, *, inheritable):
                item = exclusive_create(path, inheritable=inheritable)
                created.append(item)
                if not original_first_close:
                    original_first_close.append(item.close_parent)

                    def fail_close():
                        raise OSError("scripted first descriptor close failure")

                    item.close_parent = fail_close
                return item

            process = SimpleNamespace(pid=43210, poll=lambda: None)
            job = SimpleNamespace(assigned=False, closed=False)
            job.assign = lambda _process: setattr(job, "assigned", True)
            job.active_process_count = lambda: 1
            job.close = lambda: setattr(job, "closed", True)
            activation_sender = Mock()

            result = _supervise_event_sp(
                self._supervisor_args(alas_root),
                worker_argv=["python", "worker.py"],
                popen_factory=Mock(return_value=process),
                forward_inventory=Mock(return_value=()),
                verified_pid=Mock(return_value=2703),
                supervise=Mock(
                    return_value=ProcessSupervisionResult(
                        reason="deadline",
                        termination_mode="deadline_unconfirmed",
                        returncode=None,
                        termination_confirmed=False,
                        cooperative_stop_requested=True,
                        forced_terminate=True,
                        forced_kill=False,
                    )
                ),
                monotonic=Mock(return_value=10.0),
                temporary_directory=Mock(
                    side_effect=lambda **_kwargs: (
                        control_root.mkdir() or str(control_root)
                    )
                ),
                job_factory=Mock(return_value=job),
                activation_sender=activation_sender,
                exclusive_file_factory=make_file,
                identity_getter=lambda pid: f"{pid}:12345",
            )
            self.assertTrue(job.closed)
            self.assertIn(
                "runner.worker_termination_unconfirmed", result["validation_errors"]
            )
            self.assertIn(
                "runner.cleanup.resource_close_failed", result["validation_errors"]
            )
            activation_sender.assert_not_called()
            self.assertGreaterEqual(created[0].fd, 0)
            self.assertTrue(all(item.fd == -1 for item in created[1:]))
            original_first_close[0]()

    def test_native_handle_close_failures_do_not_skip_pipe_or_file_finalizers(self):
        calls = []

        class Job:
            def close(self):
                calls.append("job_close")
                raise OSError("scripted job CloseHandle failure")

        class ProcessHandle:
            closed = False

            def Close(self):
                calls.append("process_handle_close")
                raise OSError("scripted process CloseHandle failure")

        class Pipe:
            def close_parent_read(self):
                calls.append("activation_read_close")

            def close_parent_write(self):
                calls.append("activation_write_close")

        with tempfile.TemporaryDirectory() as directory:
            first = exclusive_create(
                Path(directory).resolve() / "first.json", inheritable=False
            )
            second = exclusive_create(
                Path(directory).resolve() / "second.json", inheritable=False
            )
            errors = _finalize_parent_resources(
                process=SimpleNamespace(_handle=ProcessHandle()),
                job=Job(),
                owned_files={"first": first, "second": second},
                activation_pipe=Pipe(),
            )

        self.assertEqual(
            [item["item"] for item in errors],
            ["job_close", "worker_process_handle_close"],
        )
        self.assertEqual(
            calls,
            [
                "job_close",
                "process_handle_close",
                "activation_read_close",
                "activation_write_close",
            ],
        )
        self.assertEqual(first.fd, -1)
        self.assertEqual(second.fd, -1)

    def test_deadline_failure_precedes_parent_adb_and_temp_side_effects(self):
        inventory = Mock(side_effect=AssertionError("ADB must not run"))
        temporary_directory = Mock(
            side_effect=AssertionError("temp directory must not be created")
        )
        with self.assertRaises(ValueError):
            _supervise_event_sp(
                self.event_sp_args(
                    total_deadline_seconds=None,
                    alas_root=Path("unused"),
                    serial="emulator-5580",
                    adb="adb",
                    driver_revision="a" * 40,
                    event="event_20260813_cn",
                ),
                forward_inventory=inventory,
                temporary_directory=temporary_directory,
            )
        inventory.assert_not_called()
        temporary_directory.assert_not_called()

    def test_event_sp_evidence_accepts_complete_monotonic_same_process_chain(self):
        self.assertEqual(self.validate_event_sp(), ())

    def test_event_sp_evidence_classifies_missing_stale_and_consumed_bundles(self):
        errors = self.validate_event_sp(
            sortie_proof=None,
            completion_proof=None,
            attempt_observation=None,
            bundle_errors=("evidence_bundle_missing_or_consumed",),
        )
        self.assertIn("event_sp.evidence_bundle_missing_or_consumed", errors)
        self.assertIn("event_sp.sortie_proof_missing", errors)
        self.assertIn("event_sp.completion_proof_missing", errors)

        _sortie, completion, _attempt = self.event_sp_evidence()
        completion.result_exit_receipt.generation = 39
        errors = self.validate_event_sp(completion_proof=completion)
        self.assertIn("event_sp.result_exit_receipt_stale", errors)

        _sortie, completion, _attempt = self.event_sp_evidence()
        completion.combat_auto_proven = False
        completion.combat_auto_generation = 20
        completion.result_generation = 20
        completion.result_path = "unreviewed/result"
        errors = self.validate_event_sp(completion_proof=completion)
        self.assertIn("event_sp.official_combat_auto_not_proven", errors)
        self.assertIn("event_sp.combat_auto_generation_not_advanced", errors)
        self.assertIn("event_sp.total_result_generation_not_advanced", errors)
        self.assertIn("event_sp.total_result_path_unreviewed", errors)

        sortie, completion, attempt = self.event_sp_evidence()
        sortie.sortie_generation = True
        completion.result_exit_receipt.generation = True
        attempt["generation"] = True
        errors = self.validate_event_sp(
            sortie_proof=sortie,
            completion_proof=completion,
            final_generation=True,
            attempt_observation=attempt,
        )
        self.assertIn("event_sp.auto_search_start_generation_not_advanced", errors)
        self.assertIn("event_sp.result_exit_receipt_stale", errors)
        self.assertIn("event_sp.final_surface_generation_not_advanced", errors)
        self.assertIn("event_sp.final_attempt_snapshot_incoherent", errors)

        # A failed/consumed transaction cannot poison the next complete one.
        self.assertEqual(self.validate_event_sp(), ())

    def test_event_sp_run_errors_have_stable_stage_classifications(self):
        self.assertEqual(
            _classify_event_sp_run_error(
                RuntimeError("campaign auto-search result target is ambiguous")
            ),
            "event_sp.total_result_target_ambiguous",
        )
        self.assertEqual(
            _classify_event_sp_run_error(
                RuntimeError("official combat automation was not proven")
            ),
            "event_sp.official_combat_auto_not_proven",
        )
        self.assertEqual(
            _classify_event_sp_run_error(RuntimeError("observer state is stale")),
            "event_sp.semantic_snapshot_stale",
        )

    def test_event_sp_failure_contract_is_isolated_from_other_event_tasks(self):
        self.assertEqual(
            _validate_event_sp_auto_search_evidence(
                task="EventD",
                stage="D1",
                use_auto_search=True,
                sortie_proof=None,
                completion_proof=None,
                final_generation=-1,
                final_surface={},
                run_count_before=1,
                run_count_after=1,
                attempt_observation=None,
                bundle_errors=("evidence_bundle_missing_or_consumed",),
            ),
            (),
        )

    def test_event_sp_attempt_observation_requires_coherent_unique_typed_text(self):
        text = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/Battle/"
                "MapItems/List/Item(Clone)/Selected/Count"
            ),
            text="0/1",
            active_in_hierarchy=True,
            active_and_enabled=True,
            truncated=False,
        )
        oracle = SimpleNamespace(
            read_ui_state=Mock(
                return_value=SimpleNamespace(generation=51, texts=(text,))
            )
        )
        observation, errors = _event_sp_attempt_observation(
            oracle, minimum_generation=50
        )
        self.assertEqual(errors, ())
        self.assertEqual(observation["text"], "0/1")
        live_text = SimpleNamespace(
            **{
                **vars(text),
                "path": (
                    "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_2050041/"
                    "main/triesLimit/Text"
                ),
                "text": "<color=#FF5C5CFF>0/1</color>",
            }
        )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=51, texts=(live_text,)
        )
        live_observation, live_errors = _event_sp_attempt_observation(
            oracle, minimum_generation=50
        )
        self.assertEqual(live_errors, ())
        self.assertEqual(live_observation["text"], "0/1")
        self.assertEqual(
            live_observation["raw_text"],
            "<color=#FF5C5CFF>0/1</color>",
        )
        non_clone = SimpleNamespace(
            **{
                **vars(text),
                "path": text.path.replace("Item(Clone)", "Item"),
            }
        )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=51, texts=(non_clone,)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
            (),
        )

        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=49, texts=(text,)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
            ("event_sp.final_attempt_snapshot_incoherent",),
        )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=53, texts=(text,)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
            ("event_sp.final_attempt_snapshot_incoherent",),
        )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=True, texts=(text,)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=0)[1],
            ("event_sp.final_attempt_snapshot_incoherent",),
        )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=51, texts=(text,)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=True)[1],
            ("event_sp.final_attempt_snapshot_incoherent",),
        )
        for invalid in (
            SimpleNamespace(**{**vars(text), "text": "1/1"}),
            SimpleNamespace(
                **{
                    **vars(text),
                    "path": text.path.replace(
                        "LevelSelectSPFullUI(Clone)", "OtherEventUI(Clone)"
                    ),
                }
            ),
            SimpleNamespace(
                **{
                    **vars(text),
                    "path": (
                        "UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/Battle/"
                        "Nodes/Chapter_1/info/bk/limit"
                    ),
                }
            ),
        ):
            oracle.read_ui_state.return_value = SimpleNamespace(
                generation=51, texts=(invalid,)
            )
            self.assertEqual(
                _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
                ("event_sp.final_attempt_text_absent_or_ambiguous",),
            )
        oracle.read_ui_state.return_value = SimpleNamespace(
            generation=51, texts=(text, text)
        )
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
            ("event_sp.final_attempt_text_absent_or_ambiguous",),
        )

        class StaleSnapshot(RuntimeError):
            pass

        StaleSnapshot.__name__ = "SemanticGateClosed"
        oracle.read_ui_state.side_effect = StaleSnapshot("observer state is stale")
        self.assertEqual(
            _event_sp_attempt_observation(oracle, minimum_generation=50)[1],
            ("event_sp.final_attempt_snapshot_unavailable",),
        )

    def test_inherited_fleet_and_map_preparation_are_closed_in_order(self):
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(
                side_effect=(
                    SimpleNamespace(kind="fleet"),
                    SimpleNamespace(kind="map"),
                    SimpleNamespace(kind="map"),
                    None,
                )
            ),
            cancel_campaign_fleet_preparation=Mock(),
            cancel_campaign_map_preparation=Mock(),
        )

        self.assertEqual(_recover_inherited_preparation(oracle, "A1"), 2)
        oracle.cancel_campaign_fleet_preparation.assert_called_once_with("a1")
        oracle.cancel_campaign_map_preparation.assert_called_once_with("a1")

    def test_inherited_d3_dock_full_is_left_for_alas_retirement_flow(self):
        oracle = SimpleNamespace(
            campaign_dock_full_visible=Mock(return_value=True),
            campaign_preparation_state=Mock(return_value=None),
            cancel_campaign_fleet_preparation=Mock(),
            cancel_campaign_map_preparation=Mock(),
        )

        self.assertEqual(_recover_inherited_preparation(oracle, "D3"), 0)
        oracle.campaign_preparation_state.assert_not_called()
        oracle.cancel_campaign_fleet_preparation.assert_not_called()
        oracle.cancel_campaign_map_preparation.assert_not_called()

    def test_inherited_d3_dock_full_uses_alas_one_click_retirement(self):
        oracle = SimpleNamespace(
            campaign_dock_full_visible=Mock(return_value=True),
            click_campaign_dock_full_choice=Mock(),
            retirement_selection_state=Mock(return_value=SimpleNamespace()),
        )
        handler = SimpleNamespace(_retire_handler=Mock(return_value=10))
        factory = Mock(return_value=handler)
        instance = SimpleNamespace(
            config=SimpleNamespace(Retirement_RetireMode="one_click_retire"),
            device=object(),
        )

        self.assertEqual(
            _recover_inherited_dock_full(
                instance,
                oracle,
                "D3",
                retirement_factory=factory,
            ),
            1,
        )
        oracle.click_campaign_dock_full_choice.assert_called_once_with(
            "d3", "organize"
        )
        handler._retire_handler.assert_called_once_with(mode="one_click_retire")

    def test_inherited_hard_preparation_resolves_shared_normal_stage(self):
        class IdentityChanged(RuntimeError):
            pass

        IdentityChanged.__name__ = "SemanticGateClosed"
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(
                side_effect=(
                    IdentityChanged("campaign map-preparation stage identity changed"),
                    SimpleNamespace(kind="map"),
                    IdentityChanged("campaign map-preparation stage identity changed"),
                    None,
                    IdentityChanged("campaign map-preparation stage identity changed"),
                    None,
                )
            ),
            cancel_campaign_fleet_preparation=Mock(),
            cancel_campaign_map_preparation=Mock(),
        )

        self.assertEqual(_recover_inherited_preparation(oracle, "C1"), 1)
        oracle.cancel_campaign_map_preparation.assert_called_once_with("a1")

    def test_event_sp_clean_start_accepts_only_absent_inherited_state(self):
        session = SimpleNamespace(
            orphan_combat_result_visible=Mock(return_value=False),
            recover_orphan_combat_result=Mock(
                side_effect=AssertionError("recovery input is forbidden")
            ),
        )
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(return_value=None),
            cancel_campaign_fleet_preparation=Mock(
                side_effect=AssertionError("cancel input is forbidden")
            ),
            cancel_campaign_map_preparation=Mock(
                side_effect=AssertionError("cancel input is forbidden")
            ),
        )

        self.assertIsNone(
            _event_sp_clean_start_stop(session, oracle, {"login": False}, "SP")
        )
        session.recover_orphan_combat_result.assert_not_called()
        oracle.cancel_campaign_fleet_preparation.assert_not_called()
        oracle.cancel_campaign_map_preparation.assert_not_called()

    def test_event_sp_inherited_start_states_stop_without_input(self):
        for label, login, orphan, preparation in (
            ("login", True, False, None),
            ("orphan_result", False, True, None),
            ("inherited_fleet_preparation", False, False, "fleet"),
            ("inherited_map_preparation", False, False, "map"),
        ):
            with self.subTest(label=label):
                session = SimpleNamespace(
                    orphan_combat_result_visible=Mock(return_value=orphan),
                    recover_orphan_combat_result=Mock(
                        side_effect=AssertionError("recovery input is forbidden")
                    ),
                )
                oracle = SimpleNamespace(
                    campaign_preparation_state=Mock(
                        return_value=(
                            None
                            if preparation is None
                            else SimpleNamespace(kind=preparation)
                        )
                    ),
                    cancel_campaign_fleet_preparation=Mock(
                        side_effect=AssertionError("cancel input is forbidden")
                    ),
                    cancel_campaign_map_preparation=Mock(
                        side_effect=AssertionError("cancel input is forbidden")
                    ),
                )

                stop = _event_sp_clean_start_stop(
                    session, oracle, {"login": login}, "SP"
                )

                self.assertEqual(stop, "event_sp.clean_start." + label)
                session.recover_orphan_combat_result.assert_not_called()
                oracle.cancel_campaign_fleet_preparation.assert_not_called()
                oracle.cancel_campaign_map_preparation.assert_not_called()
                if login:
                    session.orphan_combat_result_visible.assert_not_called()
                    oracle.campaign_preparation_state.assert_not_called()
                elif orphan:
                    oracle.campaign_preparation_state.assert_not_called()

    def test_event_sp_exhausted_selector_stops_without_stage_input(self):
        session = SimpleNamespace(
            orphan_combat_result_visible=Mock(return_value=False),
        )
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(return_value=None),
            campaign_stage_state=Mock(
                return_value=SimpleNamespace(remaining_attempts=0)
            ),
            click_campaign_stage=Mock(
                side_effect=AssertionError("stage input is forbidden")
            ),
        )

        stop = _event_sp_clean_start_stop(
            session,
            oracle,
            {"login": False, "event_page": True},
            "SP",
        )

        self.assertEqual(stop, "event_sp.clean_start.attempt_exhausted")
        oracle.campaign_stage_state.assert_called_once_with("SP")
        oracle.click_campaign_stage.assert_not_called()

    def test_startup_session_frame_is_available_without_ui_projection(self):
        source = __import__(
            "scripts.python.run_alas_event_task_live_validation",
            fromlist=["run"],
        )
        text = __import__("inspect").getsource(source._wait_for_startup_surface)

        self.assertIn(
            "semantic_session.refresh_frame(include_ui=False)",
            text,
        )
        self.assertNotIn("oracle.read_state()", text)

    def test_cold_start_waits_for_a_reviewed_surface(self):
        class NotReviewed(RuntimeError):
            pass

        NotReviewed.__name__ = "SemanticGateClosed"
        empty_oracle = SimpleNamespace(
            main_page_visible=Mock(return_value=False),
            campaign_is_in_map=Mock(side_effect=NotReviewed("not reviewed")),
            event_campaign_page_visible=Mock(return_value=False),
            enabled=Mock(return_value=False),
            login_update_download_available=Mock(return_value=False),
            login_update_in_progress=Mock(return_value=False),
            login_update_restart_prompt_available=Mock(return_value=False),
        )
        ready_oracle = SimpleNamespace(
            main_page_visible=Mock(return_value=True),
            campaign_is_in_map=Mock(return_value=False),
            event_campaign_page_visible=Mock(return_value=False),
            enabled=Mock(return_value=False),
            login_update_download_available=Mock(return_value=False),
            login_update_in_progress=Mock(return_value=False),
            login_update_restart_prompt_available=Mock(return_value=False),
        )
        session = SimpleNamespace(
            refresh_frame=Mock(
                side_effect=(
                    SimpleNamespace(generation=1),
                    SimpleNamespace(generation=7),
                )
            ),
            open=Mock(
                side_effect=(
                    SimpleNamespace(oracle=empty_oracle),
                    SimpleNamespace(oracle=ready_oracle),
                )
            ),
        )

        with __import__("unittest.mock").mock.patch(
            "scripts.python.run_alas_event_task_live_validation.time.sleep"
        ):
            frame, oracle, surfaces = _wait_for_startup_surface(
                session, timeout_seconds=1.0
            )

        self.assertEqual(frame.generation, 7)
        self.assertIs(oracle, ready_oracle)
        self.assertTrue(surfaces["main_page"])

    def _assert_event_sp_strict_startup_failure(self, message):
        failure = SemanticGateClosed(message)
        oracle = SimpleNamespace(
            main_page_visible=Mock(return_value=True),
            campaign_is_in_map=Mock(side_effect=failure),
            event_campaign_page_visible=Mock(return_value=True),
            enabled=Mock(return_value=False),
            login_update_download_available=Mock(return_value=False),
            login_update_in_progress=Mock(return_value=False),
            login_update_restart_prompt_available=Mock(return_value=False),
        )
        session = SimpleNamespace(
            refresh_frame=Mock(return_value=SimpleNamespace(generation=7)),
            open=Mock(return_value=SimpleNamespace(oracle=oracle)),
            bind_next_campaign_evidence_owner=Mock(),
            recover_orphan_combat_result=Mock(),
        )

        with self.assertRaises(SemanticGateClosed) as raised:
            _wait_for_startup_surface(
                session,
                timeout_seconds=1.0,
                strict=True,
            )

        self.assertIs(raised.exception, failure)
        oracle.event_campaign_page_visible.assert_not_called()
        session.bind_next_campaign_evidence_owner.assert_not_called()
        session.recover_orphan_combat_result.assert_not_called()

    def test_event_sp_strict_startup_propagates_stale_campaign_probe(self):
        self._assert_event_sp_strict_startup_failure("observer snapshot is stale")

    def test_event_sp_strict_startup_propagates_ambiguous_campaign_probe(self):
        self._assert_event_sp_strict_startup_failure(
            "campaign official surface is ambiguous"
        )

    def test_worker_main_serializes_fatal_stop_and_result_serialization(self):
        class FatalProbe(BaseException):
            pass

        runner_stop = __import__(
            "alas_headless.runner_supervision", fromlist=["RunnerStopRequested"]
        ).RunnerStopRequested
        cases = (
            (
                "system_exit",
                SystemExit(1),
                "fatal",
                "runner.worker_system_exit",
                "task_run",
                "started",
                1,
            ),
            (
                "fatal_pre_init",
                FatalProbe("fatal probe"),
                "fatal",
                "runner.worker_fatal",
                "pre_init",
                "not_started",
                1,
            ),
            (
                "fatal_post_run",
                FatalProbe("post-run fatal probe"),
                "fatal",
                "runner.worker_fatal",
                "post_run",
                "finished",
                1,
            ),
            (
                "stop",
                runner_stop("stop"),
                "stop_requested",
                "runner.worker_stop_requested",
                "task_run",
                "started",
                124,
            ),
            (
                "keyboard_interrupt",
                KeyboardInterrupt(),
                "fatal",
                "runner.worker_keyboard_interrupt",
                "cleanup",
                "unknown",
                1,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            args = self.event_sp_args()
            for (
                name,
                failure,
                terminal_kind,
                classification,
                phase,
                execution_state,
                expected_rc,
            ) in cases:
                written = []

                def fail_run(_args, *, worker_control, _worker_status):
                    self.assertIs(worker_control, control)
                    _worker_status.phase = phase
                    _worker_status.execution_state = execution_state
                    _worker_status.cleanup = {"completed": True, "actions": []}
                    raise failure

                with (
                    self.subTest(name=name),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.parse_args",
                        return_value=args,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                        return_value=control,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                        return_value=lambda: None,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.run",
                        side_effect=fail_run,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                        side_effect=lambda _handle, payload: written.append(payload),
                    ),
                ):
                    self.assertEqual(runner_main(), expected_rc)
                self.assertEqual(len(written), 1)
                wrapper = json.loads(written[0].decode("utf-8"))["payload"]
                self.assertEqual(wrapper["terminal_kind"], terminal_kind)
                terminal = wrapper["terminal"]["payload"]
                self.assertEqual(terminal["classification"], classification)
                self.assertEqual(terminal["phase"], phase)
                self.assertEqual(
                    terminal["execution_state"], execution_state
                )
                self.assertFalse(terminal["passed"])
                self.assertFalse(terminal["capability_promotion"])

            written = []

            def nonserializable(_args, *, worker_control, _worker_status):
                _worker_status.cleanup = {"completed": True, "actions": []}
                _worker_status.execution_state = "finished"
                return {
                    "passed": False,
                    "qualification_stop": None,
                    "nonserializable": object(),
                }

            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.parse_args",
                    return_value=args,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                    return_value=control,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                    return_value=lambda: None,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.run",
                    side_effect=nonserializable,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                    side_effect=lambda _handle, payload: written.append(payload),
                ),
            ):
                self.assertEqual(runner_main(), 1)
            wrapper = json.loads(written[0].decode("utf-8"))["payload"]
            self.assertEqual(wrapper["terminal_kind"], "fatal")
            terminal = wrapper["terminal"]["payload"]
            self.assertEqual(terminal["phase"], "result_serialize")
            self.assertEqual(
                terminal["classification"], "runner.worker_fatal"
            )

            cleanup_payloads = []
            result_payloads = []
            absent_state = ConfigFileState(
                exists=False,
                identity=None,
                attributes=None,
                link_count=None,
                size=None,
                is_directory=False,
                is_reparse_point=False,
                marker_verified=False,
                marker_error=None,
            )
            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.parse_args",
                    return_value=args,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                    return_value=control,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                    return_value=lambda: None,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.run",
                    side_effect=FatalProbe("fatal before run cleanup scope"),
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.close_inherited_handle"
                ) as close_config,
                patch(
                    "scripts.python.run_alas_event_task_live_validation.inspect_owned_config",
                    return_value=absent_state,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_json_handle",
                    side_effect=lambda _handle, value: cleanup_payloads.append(value),
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                    side_effect=lambda _handle, payload: result_payloads.append(
                        payload
                    ),
                ),
            ):
                self.assertEqual(runner_main(), 1)
            self.assertEqual(
                close_config.call_args_list,
                [
                    unittest.mock.call(control.handles.seed),
                    unittest.mock.call(control.handles.config),
                ],
            )
            self.assertEqual(len(cleanup_payloads), 1)
            self.assertEqual(len(result_payloads), 1)
            cleanup_wrapper = cleanup_payloads[0]["payload"]
            result_wrapper = json.loads(result_payloads[0].decode("utf-8"))["payload"]
            self.assertEqual(cleanup_wrapper["schema"], WORKER_CLEANUP_SCHEMA)
            self.assertTrue(cleanup_wrapper["cleanup"]["completed"])
            self.assertEqual(result_wrapper["terminal_kind"], "fatal")
            terminal = result_wrapper["terminal"]["payload"]
            self.assertEqual(terminal["phase"], "pre_init")
            self.assertEqual(
                terminal["execution_state"], "not_started"
            )
            self.assertEqual(
                terminal["cleanup_digest"],
                __import__("hashlib")
                .sha256(canonical_json_bytes(cleanup_wrapper["cleanup"]))
                .hexdigest(),
            )

    def test_worker_main_consumes_activation_without_adb_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            args = self.event_sp_args()
            written = []
            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.parse_args",
                    return_value=args,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                    return_value=control,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.resolve_adb_serial",
                    side_effect=AssertionError("worker must not enumerate ADB"),
                ) as resolve_serial,
                patch(
                    "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                    return_value=lambda: None,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.run",
                    return_value={"passed": True, "qualification_stop": None},
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                    side_effect=lambda _handle, payload: written.append(payload),
                ),
            ):
                self.assertEqual(runner_main(), 0)
            resolve_serial.assert_not_called()
            self.assertEqual(len(written), 1)

    def test_worker_public_artifacts_and_streams_never_expose_token_forms(self):
        class FatalProbe(BaseException):
            pass

        token_forms = {
            TEST_TOKEN.decode("ascii"),
            TEST_TOKEN.hex(),
            TEST_TOKEN.hex().upper(),
            base64.b64encode(TEST_TOKEN).decode("ascii"),
            base64.b64encode(TEST_TOKEN).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(TEST_TOKEN).decode("ascii"),
            base64.urlsafe_b64encode(TEST_TOKEN).decode("ascii").rstrip("="),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            secret_body = "prefix-" + TEST_TOKEN.hex().upper() + "-suffix"
            cleanup = {
                "completed": False,
                "actions": [],
                "errors": [
                    {
                        "item": "cleanup_probe",
                        **_public_error(
                            RuntimeError(secret_body), purpose="cleanup_probe"
                        ),
                    }
                ],
            }
            cleanup_wrapper = bind_record(
                control,
                RECORD_CLEANUP,
                {
                    "schema": WORKER_CLEANUP_SCHEMA,
                    "binding": binding.to_mapping(),
                    "binding_digest": binding_digest(binding),
                    "cleanup": cleanup,
                },
            )
            terminal_wrapper = _terminal_wrapper(
                control,
                SimpleNamespace(
                    phase="task_run", execution_state="started", cleanup=cleanup
                ),
                SystemExit(secret_body),
                terminal_kind="fatal",
                classification="runner.worker_system_exit",
            )
            lease = ForwardLease(
                binding=binding,
                serial="emulator-5580",
                local="tcp:2704",
                remote="localabstract:alas.g3.2703",
                verified_game_pid=2703,
                starting_forwards=(),
            )
            public_payloads = (
                control.to_mapping(),
                cleanup_wrapper,
                terminal_wrapper,
                lease.to_bound_mapping(control),
                bind_record(
                    control,
                    RECORD_RESULT,
                    {
                        "schema": WORKER_RESULT_SCHEMA,
                        "binding": binding.to_mapping(),
                        "binding_digest": binding_digest(binding),
                        "terminal_kind": "completed",
                        "result": {
                            "run_error": _public_error(
                                RuntimeError(secret_body), purpose="task_run_probe"
                            )
                        },
                    },
                ),
            )
            for payload in public_payloads:
                serialized = _public_json_bytes(payload, control).decode("utf-8")
                for token_form in token_forms:
                    self.assertNotIn(token_form, serialized)

            args = self.event_sp_args()
            for failure in (
                SystemExit(TEST_TOKEN.decode("ascii")),
                FatalProbe(base64.b64encode(TEST_TOKEN).decode("ascii")),
            ):
                written = []

                def fail_run(_args, *, worker_control, _worker_status):
                    _worker_status.phase = "task_run"
                    _worker_status.execution_state = "started"
                    _worker_status.cleanup = cleanup
                    raise failure

                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.parse_args",
                        return_value=args,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                        return_value=control,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                        return_value=lambda: None,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.run",
                        side_effect=fail_run,
                    ),
                    patch(
                        "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                        side_effect=lambda _handle, payload: written.append(payload),
                    ),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    self.assertEqual(runner_main(), 1)
                joined = (
                    b"".join(written).decode("utf-8")
                    + stdout.getvalue()
                    + stderr.getvalue()
                )
                for token_form in token_forms:
                    self.assertNotIn(token_form, joined)

            written = []
            public_json_calls = 0

            def completed_run(_args, *, worker_control, _worker_status):
                _worker_status.phase = "post_run"
                _worker_status.execution_state = "finished"
                _worker_status.cleanup = cleanup
                return {"passed": False, "qualification_stop": None}

            def serialization_probe(value, active_control):
                nonlocal public_json_calls
                public_json_calls += 1
                if public_json_calls == 1:
                    raise RuntimeError(TEST_TOKEN.hex())
                return _public_json_bytes(value, active_control)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch(
                    "scripts.python.run_alas_event_task_live_validation.parse_args",
                    return_value=args,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                    return_value=control,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.install_worker_stop_handler",
                    return_value=lambda: None,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.run",
                    side_effect=completed_run,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation._public_json_bytes",
                    side_effect=serialization_probe,
                ),
                patch(
                    "scripts.python.run_alas_event_task_live_validation.write_bytes_handle",
                    side_effect=lambda _handle, payload: written.append(payload),
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(runner_main(), 1)
            self.assertEqual(public_json_calls, 2)
            joined = (
                b"".join(written).decode("utf-8")
                + stdout.getvalue()
                + stderr.getvalue()
            )
            for token_form in token_forms:
                self.assertNotIn(token_form, joined)

    def test_final_receipt_redacts_secret_from_finalization_failure(self):
        token_forms = (
            TEST_TOKEN.decode("ascii"),
            TEST_TOKEN.hex(),
            TEST_TOKEN.hex().upper(),
            base64.b64encode(TEST_TOKEN).decode("ascii"),
            base64.urlsafe_b64encode(TEST_TOKEN).decode("ascii").rstrip("="),
        )

        def fake_impl(_args, *, _ownership, **_kwargs):
            _ownership.activation_token = TEST_TOKEN
            return {
                "schema": "alas-headless.event-task-live-validation/v1",
                "passed": False,
                "executed": None,
                "execution_state": "unknown",
                "capability_promotion": False,
                "validation_errors": [],
                "supervision": {
                    "parent_cleanup": {
                        "completed": True,
                        "blockers": [],
                        "details": {},
                    }
                },
                "leak_probe": list(token_forms),
            }

        finalization_errors = [
            {
                "item": "job_close",
                "type": "RuntimeError",
                "message": "finalizer-" + token_forms[2],
            }
        ]
        args = self.event_sp_args()
        args.output = None
        with (
            patch(
                "scripts.python.run_alas_event_task_live_validation.parse_args",
                return_value=args,
            ),
            patch(
                "scripts.python.run_alas_event_task_live_validation.resolve_adb_serial",
                return_value=args.serial,
            ),
            patch(
                "scripts.python.run_alas_event_task_live_validation.worker_control_from_activation",
                return_value=None,
            ),
            patch(
                "scripts.python.run_alas_event_task_live_validation._supervise_event_sp_impl",
                side_effect=fake_impl,
            ),
            patch(
                "scripts.python.run_alas_event_task_live_validation._finalize_parent_resources",
                return_value=finalization_errors,
            ),
            contextlib.redirect_stdout(stdout := io.StringIO()),
            contextlib.redirect_stderr(stderr := io.StringIO()),
        ):
            self.assertEqual(runner_main(), 1)
        serialized = stdout.getvalue() + stderr.getvalue()
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["execution_state"], "unknown")
        for token_form in token_forms:
            self.assertNotIn(token_form, serialized)
        self.assertIn("[redacted-secret]", serialized)

    def test_parent_accepts_bound_fatal_without_inventing_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run_id = uuid.uuid4().hex
            binding = RunBinding(
                run_id=run_id,
                token_digest=hashlib.sha256(TEST_TOKEN).hexdigest(),
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=1,
                parent_identity="1:1",
                worker_pid=2,
                config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                control_path=root / "control.json",
                result_path=root / "result.json",
                cleanup_path=root / "cleanup.json",
                lease_path=root / "lease.json",
            )
            control = WorkerControl(
                binding,
                synthetic_ownership(binding),
                synthetic_seed_source(binding),
                "emulator-5580",
                2703,
                (),
                WorkerHandles(100, 101, 102, 103, 104, 105),
                synthetic_materialization_control(binding),
                synthetic_execution_budgets(),
            )
            bind_test_control(control)
            status_type = __import__(
                "scripts.python.run_alas_event_task_live_validation",
                fromlist=["_WorkerRunStatus"],
            )._WorkerRunStatus
            status = status_type(
                phase="task_run",
                execution_state="started",
                cleanup={"completed": True, "actions": []},
            )
            wrapper = _terminal_wrapper(
                control,
                status,
                SystemExit(1),
                terminal_kind="fatal",
                classification="runner.worker_system_exit",
            )
            result = _validate_worker_result(
                wrapper,
                control,
                self.event_sp_args(
                    driver_revision="a" * 40,
                    event="event_20260813_cn",
                ),
                status.cleanup,
            )
            self.assertFalse(result["passed"])
            self.assertIsNone(result["executed"])
            self.assertEqual(result["execution_state"], "started")
            self.assertEqual(
                result["run_error"]["classification"],
                "runner.worker_system_exit",
            )


if __name__ == "__main__":
    unittest.main()
