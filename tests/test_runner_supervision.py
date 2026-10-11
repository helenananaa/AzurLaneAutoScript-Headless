import hashlib
import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from dataclasses import replace
from unittest import mock
from pathlib import Path

from alas_headless.runner_supervision import (
    ACTIVATION_RECORD_BYTES,
    BOUND_RECORD_SCHEMA,
    RECORD_CLEANUP,
    RECORD_FORWARD_LEASE,
    RECORD_RESULT,
    RECORD_TERMINAL,
    RECORD_WORKER_CONTROL,
    CONFIG_MARKER_FIELD,
    MAX_TOTAL_DEADLINE_SECONDS,
    MIN_TOTAL_DEADLINE_SECONDS,
    WORKER_ACTIVATION_HANDLE_ENV,
    WORKER_CLEANUP_HANDLE_ENV,
    WORKER_CONFIG_HANDLE_ENV,
    WORKER_CONTROL_ENV,
    WORKER_CONTROL_HANDLE_ENV,
    WORKER_CONTROL_SCHEMA,
    WORKER_ACTIVATION_SCHEMA,
    WORKER_LEASE_HANDLE_ENV,
    WORKER_RESULT_HANDLE_ENV,
    WORKER_ROLE_ENV,
    WORKER_SEED_HANDLE_ENV,
    ForwardLease,
    ForwardRecord,
    FileIdentity,
    ProcessSupervisionResult,
    RunBinding,
    SeedSource,
    WindowsWorkerJob,
    WorkerControl,
    WorkerHandles,
    WorkerTerminal,
    _read_activation_handle,
    build_config_ownership,
    bind_record,
    canonical_json_bytes,
    create_activation_pipe,
    activation_pipe_write_is_blocking,
    delete_owned_config_windows,
    exclusive_create,
    file_identity_from_fd,
    file_identity_from_path,
    inspect_owned_config,
    insert_config_marker,
    parse_forward_inventory,
    public_exception_descriptor,
    read_owned_file,
    select_forward_cleanup,
    send_activation,
    strict_json_mapping_bytes,
    supervise_process,
    validate_total_deadline,
    worker_control_from_activation,
    validate_config_basename,
    validate_config_marker,
    validate_control_lease,
    validate_worker_control_root,
    verify_bound_record,
    write_bytes_handle,
    write_owned_file,
)

TEST_TEMPLATE_SHA256 = (
    "2de0a47643d9ad73417473f66be75dadcc1a82e11d405e1f2421ade3e31eaced"
)
TEST_BUDGETS = {
    "stage_entry": 1,
    "fleet_mutation": 0,
    "sortie": 1,
    "combat": 0,
    "grid_click": 0,
    "viewport_swipe": 0,
    "camera_positioning": 0,
    "recovery_total": 0,
}


def make_materialization_control(binding: RunBinding) -> dict[str, object]:
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


def make_seed_source(root: Path, *, identity: FileIdentity | None = None) -> SeedSource:
    return SeedSource(
        capability="alas.eventsp.pinned-template/v1",
        seed_name="template",
        path=root / "template.json",
        root_path=root,
        root_identity=file_identity_from_path(root),
        identity=identity or FileIdentity(1, 13),
        size=50013,
        sha256=TEST_TEMPLATE_SHA256,
    )


class FakeProcess:
    def __init__(self, waits, *, pid=43210, poll_value=None):
        self.waits = list(waits)
        self.wait_timeouts = []
        self.signals = []
        self.terminated = False
        self.killed = False
        self.pid = pid
        self.poll_value = poll_value

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if not self.waits:
            return self.poll_value
        result = self.waits.pop(0)
        if isinstance(result, BaseException):
            raise result
        self.poll_value = result
        return result

    def poll(self):
        return self.poll_value

    def send_signal(self, value):
        self.signals.append(value)

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class FakeJob:
    def __init__(self, *, active=0, terminate_error=None, remain_active=False):
        self.active = active
        self.terminate_error = terminate_error
        self.remain_active = remain_active
        self.terminated = False
        self.closed = False

    def active_process_count(self):
        return self.active

    def terminate(self, _exit_code=124):
        self.terminated = True
        if self.terminate_error is not None:
            raise self.terminate_error
        if not self.remain_active:
            self.active = 0

    def close(self):
        self.closed = True


def make_control(root: Path, *, worker_pid=None, parent_pid=None) -> WorkerControl:
    run_id = uuid.uuid4().hex
    parent_pid = parent_pid or os.getppid()
    worker_pid = worker_pid or os.getpid()
    binding = RunBinding(
        run_id=run_id,
        task="EventSp",
        stage="SP",
        event="event_20260813_cn",
        deadline_seconds=120,
        parent_pid=parent_pid,
        parent_identity="{0}:12345".format(parent_pid),
        worker_pid=worker_pid,
        config_path=root / ("_codex_event_live_eventsp_" + run_id + ".json"),
        control_path=root / "control.json",
        result_path=root / "result.json",
        cleanup_path=root / "cleanup.json",
        lease_path=root / "lease.json",
    )
    ownership = build_config_ownership(
        binding,
        config_root=root,
        root_identity=file_identity_from_path(root),
        initial_identity=FileIdentity(1, 11),
        control_identity=FileIdentity(1, 12),
    )
    control = WorkerControl(
        binding=binding,
        config_ownership=ownership,
        seed_source=make_seed_source(root),
        serial="emulator-5580",
        verified_game_pid=2703,
        starting_forwards=(),
        handles=WorkerHandles(100, 101, 102, 103, 104, 105),
        materialization_control=make_materialization_control(binding),
        execution_budgets=TEST_BUDGETS,
    )
    return control


def make_owned_control(root: Path):
    config_root = root / "alas" / "config"
    control_root = root / "control"
    config_root.mkdir(parents=True)
    control_root.mkdir()
    run_id = uuid.uuid4().hex
    paths = {
        "config": config_root / ("_codex_event_live_eventsp_" + run_id + ".json"),
        "control": control_root / "worker-control.json",
        "result": control_root / "worker-result.json",
        "cleanup": control_root / "worker-cleanup.json",
        "lease": control_root / "forward-lease.json",
    }
    owned = {
        label: exclusive_create(path, inheritable=False)
        for label, path in paths.items()
    }
    binding = RunBinding(
        run_id=run_id,
        task="EventSp",
        stage="SP",
        event="event_20260813_cn",
        deadline_seconds=120,
        parent_pid=os.getpid(),
        parent_identity="{0}:12345".format(os.getpid()),
        worker_pid=os.getpid() + 1,
        config_path=paths["config"],
        control_path=paths["control"],
        result_path=paths["result"],
        cleanup_path=paths["cleanup"],
        lease_path=paths["lease"],
    )
    ownership = build_config_ownership(
        binding,
        config_root=config_root,
        root_identity=file_identity_from_path(config_root),
        initial_identity=file_identity_from_fd(owned["config"].fd),
        control_identity=file_identity_from_fd(owned["control"].fd),
    )
    control = WorkerControl(
        binding=binding,
        config_ownership=ownership,
        seed_source=make_seed_source(config_root),
        serial="emulator-5580",
        verified_game_pid=2703,
        starting_forwards=(),
        handles=WorkerHandles(100, 101, 102, 103, 104, 105),
        materialization_control=make_materialization_control(binding),
        execution_budgets=TEST_BUDGETS,
    )
    write_owned_file(owned["control"], canonical_json_bytes(control.to_mapping()))
    return control, owned


def close_owned_files(owned):
    for item in owned.values():
        if item.child_handle >= 0:
            item.close_child_handle()
        if item.fd >= 0:
            item.close_parent()


class RunnerSupervisionTests(unittest.TestCase):
    def test_public_error_does_not_copy_exception_text(self):
        descriptor = public_exception_descriptor(RuntimeError("account-private-data"), "probe")
        self.assertEqual(set(descriptor), {"type", "message_digest", "traceback_digest"})
        self.assertEqual(descriptor["type"], "RuntimeError")
        self.assertNotIn("account-private-data", json.dumps(descriptor))

    def test_strict_json_rejects_nonfinite_duplicate_nonutf8_and_oversize(self):
        invalid = (
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":-Infinity}',
            b'{"value":1,"value":2}',
            b'{"value":"\xff"}',
            b"x" * 33,
        )
        for payload in invalid:
            with self.subTest(payload=payload[:32]), self.assertRaises(ValueError):
                strict_json_mapping_bytes(payload, maximum=32, label="test JSON")
        self.assertEqual(
            strict_json_mapping_bytes(b'{"value":1}', maximum=32, label="test JSON"),
            {"value": 1},
        )

    def test_bound_record_is_purpose_scoped_and_run_scoped_without_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            body = {
                "schema": "test/v1",
                "binding": control.binding.to_mapping(),
                "field": {"nested": [1, 2, 3]},
            }
            record = bind_record(control, RECORD_RESULT, body)
            self.assertNotIn("token_digest", control.binding.to_mapping())
            self.assertEqual(record["payload"], body)
            self.assertEqual(
                verify_bound_record(control, RECORD_RESULT, record), body
            )

            wrong_purpose = dict(record)
            wrong_purpose["purpose"] = RECORD_CLEANUP
            with self.assertRaises(ValueError):
                verify_bound_record(control, RECORD_RESULT, wrong_purpose)
            with self.assertRaises(ValueError):
                verify_bound_record(control, RECORD_CLEANUP, record)

            replay_control = make_control(root)
            with self.assertRaises(ValueError):
                verify_bound_record(replay_control, RECORD_RESULT, record)
            for malformed in (None, "", "0" * 31, "0" * 33, "g" * 32):
                candidate = dict(record)
                candidate["run_id"] = malformed
                with self.subTest(run_id=malformed), self.assertRaises(ValueError):
                    verify_bound_record(control, RECORD_RESULT, candidate)

            for purpose in (RECORD_TERMINAL, RECORD_FORWARD_LEASE):
                with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                    verify_bound_record(control, purpose, record)

    def test_worker_terminal_rejects_contradictory_joint_fields(self):
        valid = WorkerTerminal(
            terminal_kind="fatal",
            phase="task_run",
            execution_state="started",
            classification="runner.worker_system_exit",
            passed=False,
            capability_promotion=False,
            exit_code=1,
            exception_type="SystemExit",
            message="exit",
            traceback_digest=None,
            cleanup_status="complete",
            cleanup_digest="0" * 64,
        ).to_mapping()
        contradictions = (
            {
                "terminal_kind": "stop_requested",
                "classification": "runner.worker_fatal",
                "phase": "pre_init",
                "execution_state": "finished",
                "exception_type": "SystemExit",
                "exit_code": 999,
            },
            {"phase": "post_run", "execution_state": "started"},
            {"phase": "result_serialize", "execution_state": "unknown"},
            {"classification": "runner.worker_system_exit", "exit_code": None},
            {
                "classification": "runner.worker_keyboard_interrupt",
                "exception_type": "KeyboardInterrupt",
                "exit_code": 1,
            },
            {"cleanup_status": "missing", "cleanup_digest": "0" * 64},
        )
        for mutation in contradictions:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                WorkerTerminal.from_mapping({**valid, **mutation})

    def test_deadline_is_a_strict_bounded_integer(self):
        self.assertEqual(
            validate_total_deadline(MIN_TOTAL_DEADLINE_SECONDS),
            MIN_TOTAL_DEADLINE_SECONDS,
        )
        self.assertEqual(
            validate_total_deadline(MAX_TOTAL_DEADLINE_SECONDS),
            MAX_TOTAL_DEADLINE_SECONDS,
        )
        for value in (
            None,
            True,
            False,
            "120",
            120.0,
            MIN_TOTAL_DEADLINE_SECONDS - 1,
            MAX_TOTAL_DEADLINE_SECONDS + 1,
            -1,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_total_deadline(value)

    def test_supervision_result_rejects_non_strict_shapes(self):
        valid = {
            "reason": "completed",
            "termination_mode": "completed",
            "returncode": 0,
            "termination_confirmed": True,
            "cooperative_stop_requested": False,
            "forced_terminate": False,
            "forced_kill": False,
            "errors": (),
        }
        for field, value in (
            ("termination_mode", 1),
            ("returncode", True),
            ("termination_confirmed", 1),
            ("cooperative_stop_requested", 0),
            ("forced_terminate", None),
            ("forced_kill", "false"),
            ("errors", ["not-a-tuple"]),
            ("errors", (1,)),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    ProcessSupervisionResult(**{**valid, field: value})

    @unittest.skipUnless(os.name == "nt", "Windows CloseHandle contract")
    def test_job_close_failure_keeps_handle_available_for_retry(self):
        from ctypes import wintypes

        class ScriptedClose:
            def __init__(self):
                self.results = [False, True]
                self.argtypes = None
                self.restype = None

            def __call__(self, _handle):
                return self.results.pop(0)

        close = ScriptedClose()
        job = object.__new__(WindowsWorkerJob)
        job._kernel32 = mock.Mock(CloseHandle=close)
        job._handle = 123
        with self.assertRaises(OSError):
            job.close()
        self.assertEqual(job._handle, 123)
        job.close()
        self.assertIsNone(job._handle)
        self.assertEqual(close.argtypes, (wintypes.HANDLE,))
        self.assertIs(close.restype, wintypes.BOOL)

    def test_forward_inventory_is_exact_and_canonical(self):
        inventory = parse_forward_inventory(
            "emulator-5580 tcp:2078 localabstract:alas.g3.2703\n"
            "emulator-5580 tcp:12339 localabstract:alas.g3.2703\n"
        )
        self.assertEqual({item.port for item in inventory}, {2078, 12339})
        self.assertEqual(inventory, tuple(sorted(inventory)))
        with self.assertRaises(ValueError):
            parse_forward_inventory("emulator-5580 tcp:12339\n")
        with self.assertRaises(ValueError):
            parse_forward_inventory(
                "emulator-5580 tcp:12339 localabstract:alas.g3.2703\n" * 2
            )

    def test_activation_is_one_fixed_write_and_deadline_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            control_path = root / "control.json"
            control_path.write_bytes(canonical_json_bytes(control.to_mapping()))

            pipe = create_activation_pipe()
            real_write = os.write
            try:
                with mock.patch(
                    "alas_headless.runner_supervision.os.write", wraps=real_write
                ) as writer:
                    send_activation(
                        pipe,
                        control,
                        control_path,
                        absolute_deadline=2.0,
                        monotonic=lambda: 1.0,
                    )
                writer.assert_called_once()
                self.assertEqual(len(writer.call_args.args[1]), ACTIVATION_RECORD_BYTES)
                self.assertLessEqual(ACTIVATION_RECORD_BYTES, 512)
            finally:
                pipe.close_parent_read()
                pipe.close_parent_write()

            pipe = create_activation_pipe()
            try:
                with mock.patch(
                    "alas_headless.runner_supervision.os.write",
                    return_value=ACTIVATION_RECORD_BYTES - 1,
                ) as writer:
                    with self.assertRaisesRegex(OSError, "short write"):
                        send_activation(
                            pipe,
                            control,
                            control_path,
                            absolute_deadline=2.0,
                            monotonic=lambda: 1.0,
                        )
                writer.assert_called_once()
            finally:
                pipe.close_parent_read()
                pipe.close_parent_write()

            pipe = create_activation_pipe()
            clock = mock.Mock(side_effect=(1.0, 3.0))
            try:
                with mock.patch("alas_headless.runner_supervision.os.write") as writer:
                    with self.assertRaises(TimeoutError):
                        send_activation(
                            pipe,
                            control,
                            control_path,
                            absolute_deadline=2.0,
                            monotonic=clock,
                        )
                writer.assert_not_called()
            finally:
                pipe.close_parent_read()
                pipe.close_parent_write()

    def test_activation_reader_rejects_partial_and_trailing_records(self):
        for size in (ACTIVATION_RECORD_BYTES - 1, ACTIVATION_RECORD_BYTES + 1):
            with self.subTest(size=size):
                pipe = create_activation_pipe()
                try:
                    self.assertEqual(os.write(pipe.write_fd, b"x" * size), size)
                    pipe.close_parent_write()
                    with self.assertRaisesRegex(RuntimeError, "partial or oversized"):
                        _read_activation_handle(pipe.read_handle)
                    pipe.read_fd = -1
                finally:
                    pipe.close_parent_read()
                    pipe.close_parent_write()

    def test_activation_reader_rejects_malformed_public_run_ids(self):
        for suffix in (b"z" * 32, b"\xff" * 32):
            with self.subTest(suffix=suffix[:1]):
                pipe = create_activation_pipe()
                try:
                    os.write(pipe.write_fd, WORKER_ACTIVATION_SCHEMA.encode("ascii") + suffix)
                    pipe.close_parent_write()
                    with self.assertRaisesRegex(RuntimeError, "run ID is malformed"):
                        _read_activation_handle(pipe.read_handle)
                    pipe.read_fd = -1
                finally:
                    pipe.close_parent_read()
                    pipe.close_parent_write()

    def test_activation_saturated_and_broken_pipe_fail_once_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            control_path = root / "control.json"
            control_path.write_bytes(canonical_json_bytes(control.to_mapping()))
            real_write = os.write

            saturated = create_activation_pipe()
            try:
                self.assertFalse(activation_pipe_write_is_blocking(saturated))
                while True:
                    try:
                        real_write(saturated.write_fd, b"x" * 4096)
                    except OSError as exc:
                        self.assertIn(
                            exc.errno,
                            {errno.EAGAIN, errno.EWOULDBLOCK, errno.ENOSPC},
                        )
                        break
                started = time.monotonic()
                with mock.patch(
                    "alas_headless.runner_supervision.os.write", wraps=real_write
                ) as writer:
                    with self.assertRaises(OSError) as raised:
                        send_activation(
                            saturated,
                            control,
                            control_path,
                            absolute_deadline=time.monotonic() + 5.0,
                        )
                self.assertIn(
                    raised.exception.errno,
                    {errno.EAGAIN, errno.EWOULDBLOCK, errno.ENOSPC},
                )
                self.assertLess(time.monotonic() - started, 1.0)
                writer.assert_called_once()
            finally:
                saturated.close_parent_read()
                saturated.close_parent_write()

            broken = create_activation_pipe()
            broken.close_parent_read()
            try:
                with mock.patch(
                    "alas_headless.runner_supervision.os.write", wraps=real_write
                ) as writer:
                    with self.assertRaises(OSError):
                        send_activation(
                            broken,
                            control,
                            control_path,
                            absolute_deadline=time.monotonic() + 5.0,
                        )
                writer.assert_called_once()
            finally:
                broken.close_parent_read()
                broken.close_parent_write()

    def test_exact_lease_and_delta_never_select_preexisting_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            control = make_control(Path(directory).resolve())
            old = ForwardRecord(
                "emulator-5580", "tcp:2078", "localabstract:alas.g3.2703"
            )
            owned = ForwardRecord(
                "emulator-5580", "tcp:12339", "localabstract:alas.g3.2703"
            )
            lease = ForwardLease(
                binding=control.binding,
                serial="emulator-5580",
                local=owned.local,
                remote=owned.remote,
                verified_game_pid=2703,
                starting_forwards=(old,),
            )
            exact = select_forward_cleanup(
                binding=control.binding,
                serial="emulator-5580",
                verified_game_pid=2703,
                starting=(old,),
                ending=(old, owned),
                lease=lease,
            )
            self.assertEqual(exact.record, owned)
            ambiguous = select_forward_cleanup(
                binding=control.binding,
                serial="emulator-5580",
                verified_game_pid=2703,
                starting=(old,),
                ending=(
                    old,
                    owned,
                    ForwardRecord(
                        "emulator-5580",
                        "tcp:12340",
                        "localabstract:alas.g3.2703",
                    ),
                ),
                lease=None,
            )
            self.assertIsNone(ambiguous.record)
            self.assertEqual(
                ambiguous.blockers, ("runner.cleanup.forward_delta_ambiguous",)
            )

    def test_self_signed_environment_without_live_handle_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            control_path = root / "control.json"
            control_path.write_text(json.dumps(control.to_mapping()), encoding="utf-8")
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(control_path),
                WORKER_ACTIVATION_HANDLE_ENV: "999999999",
                WORKER_CONTROL_HANDLE_ENV: "100",
                WORKER_CONFIG_HANDLE_ENV: "101",
                WORKER_RESULT_HANDLE_ENV: "102",
                WORKER_CLEANUP_HANDLE_ENV: "103",
                WORKER_LEASE_HANDLE_ENV: "104",
                WORKER_SEED_HANDLE_ENV: "105",
            }
            with self.assertRaises((OSError, RuntimeError)):
                worker_control_from_activation(environment)

    @unittest.skipUnless(os.name == "nt", "Windows exact-handle activation contract")
    def test_one_shot_activation_binds_run_identity_and_accepts_json_formatting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            result_file = exclusive_create(root / "result.json", inheritable=True)
            cleanup_file = exclusive_create(root / "cleanup.json", inheritable=True)
            lease_file = exclusive_create(root / "lease.json", inheritable=True)
            run_id = uuid.uuid4().hex
            config_file = exclusive_create(
                root / ("_codex_event_live_eventsp_" + run_id + ".json"),
                inheritable=True,
            )
            control_file = exclusive_create(root / "control.json", inheritable=False)
            seed_file = exclusive_create(root / "template.json", inheritable=False)
            parent_pid = os.getppid()
            binding = RunBinding(
                run_id=run_id,
                task="EventSp",
                stage="SP",
                event="event_20260813_cn",
                deadline_seconds=120,
                parent_pid=parent_pid,
                parent_identity="{0}:54321".format(parent_pid),
                worker_pid=os.getpid(),
                config_path=config_file.path,
                control_path=control_file.path,
                result_path=result_file.path,
                cleanup_path=cleanup_file.path,
                lease_path=lease_file.path,
            )
            child_handles = {
                "control": control_file.create_child_handle("read"),
                "config": config_file.create_child_handle("write"),
                "result": result_file.create_child_handle("write"),
                "cleanup": cleanup_file.create_child_handle("write"),
                "lease": lease_file.create_child_handle("write"),
                "seed": seed_file.create_child_handle("read"),
            }
            handles = WorkerHandles(
                child_handles["control"],
                child_handles["config"],
                child_handles["result"],
                child_handles["cleanup"],
                child_handles["lease"],
                child_handles["seed"],
            )
            ownership = build_config_ownership(
                binding,
                config_root=root,
                root_identity=file_identity_from_path(root),
                initial_identity=file_identity_from_fd(config_file.fd),
                control_identity=file_identity_from_fd(control_file.fd),
            )
            control = WorkerControl(
                binding,
                ownership,
                make_seed_source(root, identity=file_identity_from_fd(seed_file.fd)),
                "emulator-5580",
                2703,
                (),
                handles,
                make_materialization_control(binding),
                TEST_BUDGETS,
            )
            write_owned_file(control_file, json.dumps(control.to_mapping(), indent=2).encode("utf-8"))
            pipe = create_activation_pipe()
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(control_file.path),
                WORKER_ACTIVATION_HANDLE_ENV: str(pipe.read_handle),
                WORKER_CONTROL_HANDLE_ENV: str(handles.control),
                WORKER_CONFIG_HANDLE_ENV: str(handles.config),
                WORKER_RESULT_HANDLE_ENV: str(handles.result),
                WORKER_CLEANUP_HANDLE_ENV: str(handles.cleanup),
                WORKER_LEASE_HANDLE_ENV: str(handles.lease),
                WORKER_SEED_HANDLE_ENV: str(handles.seed),
            }
            send_activation(
                pipe,
                control,
                control_file.path,
                absolute_deadline=time.monotonic() + 5.0,
            )
            actual = worker_control_from_activation(
                environment,
                get_parent_pid=lambda: parent_pid,
                get_process_identity=lambda _pid: binding.parent_identity,
            )
            control_file.child_handle = -1
            self.assertEqual(actual, control)
            self.assertTrue(actual.activation_verified)
            self.assertFalse(control.activation_verified)
            for label, handle in handles.to_mapping().items():
                if label == "control":
                    continue
                if os.name == "nt":
                    self.assertFalse(os.get_handle_inheritable(handle))
                else:
                    self.assertFalse(os.get_inheritable(handle))
            with self.assertRaises((OSError, RuntimeError)):
                worker_control_from_activation(
                    environment,
                    get_parent_pid=lambda: parent_pid,
                    get_process_identity=lambda _pid: binding.parent_identity,
                )
            pipe.read_fd = -1
            for item in (
                control_file,
                config_file,
                result_file,
                cleanup_file,
                lease_file,
                seed_file,
            ):
                item.close_child_handle()
                item.close_parent()

    def test_spoofed_binding_fields_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            control = make_control(Path(directory).resolve())
            baseline = dict(control.binding.to_mapping())
            mutations = {
                "task": "EventB",
                "stage": "A1",
                "event": "",
                "deadline_seconds": 119,
                "parent_pid": 0,
                "parent_identity": "bad",
                "worker_pid": 0,
                "result_path": str(control.binding.config_path),
                "config_path": str(control.binding.config_path.with_name("other.json")),
            }
            for field, value in mutations.items():
                changed = dict(baseline)
                changed[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    RunBinding.from_mapping(changed)

    def test_activation_rejects_real_parent_pid_and_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            control_path = root / "control.json"
            payload = canonical_json_bytes(control.to_mapping())
            control_path.write_bytes(payload)
            activation = control.binding.run_id
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(control_path),
                WORKER_ACTIVATION_HANDLE_ENV: "100",
                WORKER_CONTROL_HANDLE_ENV: "100",
                WORKER_CONFIG_HANDLE_ENV: "101",
                WORKER_RESULT_HANDLE_ENV: "102",
                WORKER_CLEANUP_HANDLE_ENV: "103",
                WORKER_LEASE_HANDLE_ENV: "104",
                WORKER_SEED_HANDLE_ENV: "105",
            }
            with (
                mock.patch(
                    "alas_headless.runner_supervision._read_activation_handle",
                    return_value=activation,
                ),
                mock.patch(
                    "alas_headless.runner_supervision.read_bytes_handle",
                    return_value=(
                        payload,
                        control.config_ownership.control_identity,
                    ),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "parent PID"):
                    worker_control_from_activation(
                        environment,
                        get_parent_pid=lambda: control.binding.parent_pid + 1,
                        get_process_identity=lambda _pid: control.binding.parent_identity,
                    )
                with self.assertRaisesRegex(RuntimeError, "parent process"):
                    worker_control_from_activation(
                        environment,
                        get_parent_pid=lambda: control.binding.parent_pid,
                        get_process_identity=lambda _pid: "1:999",
                    )

    def test_activation_correlates_control_path_and_public_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            original = root / "control.json"
            alternate = root / "alternate-control.json"
            payload = canonical_json_bytes(control.to_mapping())
            original.write_bytes(payload)
            alternate.write_bytes(payload)
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(alternate),
                WORKER_ACTIVATION_HANDLE_ENV: "100",
                WORKER_CONTROL_HANDLE_ENV: "100",
                WORKER_CONFIG_HANDLE_ENV: "101",
                WORKER_RESULT_HANDLE_ENV: "102",
                WORKER_CLEANUP_HANDLE_ENV: "103",
                WORKER_LEASE_HANDLE_ENV: "104",
                WORKER_SEED_HANDLE_ENV: "105",
            }
            with (
                mock.patch(
                    "alas_headless.runner_supervision._read_activation_handle",
                    return_value=control.binding.run_id,
                ),
                mock.patch(
                    "alas_headless.runner_supervision.read_bytes_handle",
                    return_value=(
                        payload,
                        control.config_ownership.control_identity,
                    ),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "control path"):
                    worker_control_from_activation(environment)

            environment[WORKER_CONTROL_ENV] = str(original)
            with (
                mock.patch(
                    "alas_headless.runner_supervision._read_activation_handle",
                    return_value=uuid.uuid4().hex,
                ),
                mock.patch(
                    "alas_headless.runner_supervision.read_bytes_handle",
                    return_value=(
                        payload,
                        control.config_ownership.control_identity,
                    ),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "another run"):
                    worker_control_from_activation(environment)

    def test_control_binding_rejects_wrong_purpose_and_malformed_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            bound = control.to_mapping()
            body = dict(bound["payload"])

            wrong_purpose = bind_record(control, RECORD_RESULT, body)
            with self.assertRaises(ValueError):
                WorkerControl.from_mapping(
                    wrong_purpose
                )

            restored = WorkerControl.from_mapping(bound)
            self.assertEqual(restored.binding, control.binding)
            self.assertFalse(restored.activation_verified)

            partial = bind_record(
                control,
                RECORD_WORKER_CONTROL,
                {"schema": body["schema"]},
            )
            with self.assertRaises(ValueError):
                WorkerControl.from_mapping(
                    partial
                )

            for malformed in (None, "", "0" * 31, "0" * 33, "g" * 32):
                candidate = dict(bound)
                candidate["run_id"] = malformed
                with self.subTest(digest=malformed), self.assertRaises(ValueError):
                    WorkerControl.from_mapping(
                        candidate
                    )

    def test_worker_control_strict_bytes_precede_binding_and_object_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            control_path = control.binding.control_path
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(control_path),
                WORKER_ACTIVATION_HANDLE_ENV: "100",
                WORKER_CONTROL_HANDLE_ENV: "100",
                WORKER_CONFIG_HANDLE_ENV: "101",
                WORKER_RESULT_HANDLE_ENV: "102",
                WORKER_CLEANUP_HANDLE_ENV: "103",
                WORKER_LEASE_HANDLE_ENV: "104",
                WORKER_SEED_HANDLE_ENV: "105",
            }
            valid = canonical_json_bytes(control.to_mapping())
            duplicate = valid.replace(
                b'"run_id":',
                b'"run_id":"0","run_id":',
                1,
            )
            cases = {
                "truncated": valid[:-2],
                "partial": b'{"schema":"alas-headless.runner-bound-record/v1"}\n',
                "oversize": b"{" + b" " * (512 * 1024) + b"}",
                "duplicate": duplicate,
                "nonfinite": b'{"value":NaN}\n',
                "non_utf8": b'{"value":"\xff"}\n',
            }
            for label, payload in cases.items():
                activation = control.binding.run_id
                with (
                    self.subTest(label=label),
                    mock.patch(
                        "alas_headless.runner_supervision._read_activation_handle",
                        return_value=activation,
                    ),
                    mock.patch(
                        "alas_headless.runner_supervision.read_bytes_handle",
                        return_value=(
                            payload,
                            control.config_ownership.control_identity,
                        ),
                    ),
                    self.assertRaises((ValueError, RuntimeError)),
                ):
                    worker_control_from_activation(environment)

    def test_worker_control_requires_one_current_root_identity_at_all_admissions(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = parent / "config"
            root.mkdir()
            control = make_control(root)
            with self.assertRaisesRegex(ValueError, "root identity"):
                WorkerControl(
                    binding=control.binding,
                    config_ownership=control.config_ownership,
                    seed_source=replace(
                        control.seed_source,
                        root_identity=FileIdentity(9, 9),
                    ),
                    serial=control.serial,
                    verified_game_pid=control.verified_game_pid,
                    starting_forwards=control.starting_forwards,
                    handles=control.handles,
                    materialization_control=control.materialization_control,
                    execution_budgets=control.execution_budgets,
                )

            original = parent / "config-original"
            root.rename(original)
            root.mkdir()
            with self.assertRaisesRegex(RuntimeError, "root identity changed"):
                control.to_mapping()
            with self.assertRaisesRegex(RuntimeError, "root identity changed"):
                validate_worker_control_root(control)

    @unittest.skipUnless(os.name == "nt", "Windows inherited-handle contract")
    def test_worker_rejects_bound_control_after_real_root_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            root = parent / "config"
            root.mkdir()
            control = make_control(root)
            control_path = control.binding.control_path
            payload = canonical_json_bytes(control.to_mapping())
            activation = control.binding.run_id
            original = parent / "config-original"
            root.rename(original)
            root.mkdir()
            environment = {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(control_path),
                WORKER_ACTIVATION_HANDLE_ENV: "100",
                WORKER_CONTROL_HANDLE_ENV: "100",
                WORKER_CONFIG_HANDLE_ENV: "101",
                WORKER_RESULT_HANDLE_ENV: "102",
                WORKER_CLEANUP_HANDLE_ENV: "103",
                WORKER_LEASE_HANDLE_ENV: "104",
                WORKER_SEED_HANDLE_ENV: "105",
            }
            inheritability = mock.Mock()
            with (
                mock.patch(
                    "alas_headless.runner_supervision._read_activation_handle",
                    return_value=activation,
                ),
                mock.patch(
                    "alas_headless.runner_supervision.read_bytes_handle",
                    return_value=(
                        payload,
                        control.config_ownership.control_identity,
                    ),
                ),
                mock.patch(
                    "alas_headless.runner_supervision.os.set_handle_inheritable",
                    inheritability,
                ),
                self.assertRaisesRegex(RuntimeError, "root identity changed"),
            ):
                worker_control_from_activation(environment)
            inheritability.assert_not_called()

    def test_exclusive_creation_preserves_preexisting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / (uuid.uuid4().hex + ".json")
            path.write_text("owned-by-somebody-else", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                exclusive_create(path, inheritable=False)
            self.assertEqual(path.read_text(encoding="utf-8"), "owned-by-somebody-else")

    @unittest.skipUnless(os.name == "nt", "Windows exact-handle artifact contract")
    def test_immutable_artifacts_use_locked_master_and_exact_handle_delete(self):
        for label in ("control", "result", "cleanup", "lease"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                _control, owned = make_owned_control(root)
                replacement = owned[label].path.with_name(label + ".replacement")
                try:
                    if label != "control":
                        write_owned_file(owned[label], b"{}\n")
                    replacement.write_bytes(b'{"foreign":true}\n')
                    with self.assertRaises(PermissionError):
                        os.replace(replacement, owned[label].path)
                    owned[label].remove_owned_path()
                    self.assertFalse(owned[label].path.exists())
                    self.assertTrue(replacement.exists())
                finally:
                    close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows hardlink artifact contract")
    def test_immutable_artifacts_retain_hardlink_aliases(self):
        for label in ("control", "result", "cleanup", "lease"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                _control, owned = make_owned_control(root)
                alias = owned[label].path.with_name(label + ".alias")
                try:
                    if label != "control":
                        write_owned_file(owned[label], b"{}\n")
                    os.link(owned[label].path, alias)
                    with self.assertRaisesRegex(RuntimeError, "hard links"):
                        owned[label].remove_owned_path()
                    self.assertTrue(owned[label].path.exists())
                    self.assertTrue(alias.exists())
                finally:
                    close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows disposition race contract")
    def test_immutable_artifact_disposition_hardlink_race_is_cancelled(self):
        from alas_headless import runner_supervision as supervision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _control, owned = make_owned_control(root)
            artifact = owned["result"]
            alias = artifact.path.with_name("result-race.alias")
            write_owned_file(artifact, b"{}\n")
            real_set = supervision._windows_set_disposition

            def link_then_set(kernel32, handle):
                os.link(artifact.path, alias)
                return real_set(kernel32, handle)

            try:
                with mock.patch(
                    "alas_headless.runner_supervision._windows_set_disposition",
                    side_effect=link_then_set,
                ):
                    with self.assertRaisesRegex(RuntimeError, "hardlink race"):
                        artifact.remove_owned_path()
                self.assertTrue(artifact.path.exists())
                self.assertTrue(alias.exists())
                self.assertTrue(artifact.owned)
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows foreign replacement contract")
    def test_immutable_artifact_foreign_post_delete_replacement_survives(self):
        from alas_headless import runner_supervision as supervision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _control, owned = make_owned_control(root)
            artifact = owned["result"]
            try:
                write_owned_file(artifact, b"{}\n")
                real_identity = supervision.file_identity_from_path

                def inject_foreign(path):
                    path = Path(path)
                    if path == artifact.path and not path.exists():
                        path.write_bytes(b'{"foreign":true}\n')
                    return real_identity(path)

                with (
                    mock.patch(
                        "alas_headless.runner_supervision.file_identity_from_path",
                        side_effect=inject_foreign,
                    ),
                    self.assertRaisesRegex(RuntimeError, "foreign replacement"),
                ):
                    artifact.remove_owned_path()
                self.assertFalse(artifact.owned)
                self.assertEqual(
                    json.loads(artifact.path.read_text(encoding="utf-8")),
                    {"foreign": True},
                )
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows exclusive rollback contract")
    def test_exclusive_create_rollback_never_unlinks_racing_alias(self):
        from alas_headless import runner_supervision as supervision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / (uuid.uuid4().hex + ".json")
            alias = root / "rollback.alias"
            real_set = supervision._windows_set_disposition

            def link_then_set(kernel32, handle):
                os.link(path, alias)
                return real_set(kernel32, handle)

            with (
                mock.patch("msvcrt.open_osfhandle", side_effect=OSError("probe")),
                mock.patch(
                    "alas_headless.runner_supervision._windows_set_disposition",
                    side_effect=link_then_set,
                ),
                self.assertRaisesRegex(OSError, "probe"),
            ):
                exclusive_create(path, inheritable=False)
            self.assertTrue(path.exists())
            self.assertTrue(alias.exists())

    @unittest.skipUnless(os.name == "nt", "Windows downgraded child handles")
    def test_child_artifact_handles_are_explicit_downgraded_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _control, owned = make_owned_control(root)
            try:
                self.assertFalse(os.get_handle_inheritable(owned["control"].handle))
                read_handle = owned["control"].create_child_handle("read")
                self.assertTrue(os.get_handle_inheritable(read_handle))
                import msvcrt

                read_fd = msvcrt.open_osfhandle(
                    read_handle, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                )
                owned["control"].child_handle = -1
                with os.fdopen(read_fd, "rb") as stream:
                    stream.seek(0)
                    record = json.loads(stream.read().decode("utf-8"))
                    self.assertEqual(record["schema"], BOUND_RECORD_SCHEMA)
                    self.assertEqual(record["payload"]["schema"], WORKER_CONTROL_SCHEMA)

                write_handle = owned["result"].create_child_handle("write")
                self.assertTrue(os.get_handle_inheritable(write_handle))
                write_bytes_handle(write_handle, b"{}\n")
                owned["result"].child_handle = -1
                self.assertEqual(read_owned_file(owned["result"], 16), b"{}\n")
            finally:
                close_owned_files(owned)

    def test_run_owned_basename_rejects_alias_ads_and_separators(self):
        run_id = uuid.uuid4().hex
        expected = "_codex_event_live_eventsp_" + run_id + ".json"
        self.assertEqual(validate_config_basename(run_id, expected), expected)
        for invalid in (
            expected.upper(),
            expected + ":stream",
            expected + ".",
            expected + " ",
            "subdir/" + expected,
            "subdir\\" + expected,
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_config_basename(run_id, invalid)

    def test_pinned_config_update_preserves_storage_marker_and_discards_top_level(self):
        alas_root = Path(
            os.environ.get(
                "ALAS_PINNED_ROOT",
                str(Path(__file__).resolve().parents[2] / "AzurLaneAutoScript-upstream-readonly"),
            )
        )
        if not (alas_root / "module" / "config" / "config_updater.py").is_file():
            self.skipTest("pinned ALAS tree is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control = make_control(root)
            template_payload = (alas_root / "config" / "template.json").read_bytes()
            self.assertEqual(
                hashlib.sha256(template_payload).hexdigest(), TEST_TEMPLATE_SHA256
            )
            from scripts.python.run_alas_event_task_live_validation import _configure

            seed = _configure(
                json.loads(template_payload.decode("utf-8")),
                serial="emulator-5580",
                task="EventSp",
                event="event_20260813_cn",
                stage="SP",
                use_auto_search=True,
            )
            insert_config_marker(seed, control.binding, control.config_ownership)
            seed["__alas_headless_top_level_marker"] = {"must": "be discarded"}
            input_path = root / "input.json"
            output_path = root / "output.json"
            result_path = root / "result.json"
            fixture_root = root / "pinned-alas"
            shutil.copytree(alas_root / "module", fixture_root / "module")
            shutil.copytree(alas_root / "deploy", fixture_root / "deploy")
            (fixture_root / "config").mkdir()
            (fixture_root / "config" / "template.json").write_bytes(template_payload)
            input_path.write_text(json.dumps(seed), encoding="utf-8")
            code = r"""
import json, sys
from pathlib import Path
alas_root, source, output, result = map(Path, sys.argv[1:])
sys.path.insert(0, str(alas_root))
from module.config.config_updater import ConfigUpdater
from module.config.utils import write_file
old = json.loads(source.read_text(encoding='utf-8'))
updater = ConfigUpdater()
first = updater.config_update(old)
write_file(str(output), first)
second_source = json.loads(output.read_text(encoding='utf-8'))
second_source['EventSp']['Emotion']['Fleet1Value'] = 117
second_source['EventSp']['StopCondition']['RunCount'] = 0
second = updater.config_update(second_source)
write_file(str(output), second)
final = json.loads(output.read_text(encoding='utf-8'))
result.write_text(json.dumps({
    'marker': final['EventSp']['Storage']['Storage'],
    'top_level_present': '__alas_headless_top_level_marker' in final,
    'emotion': final['EventSp']['Emotion']['Fleet1Value'],
    'run_count': final['EventSp']['StopCondition']['RunCount'],
}), encoding='utf-8')
"""
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(fixture_root),
                    str(input_path),
                    str(output_path),
                    str(result_path),
                ],
                cwd=str(fixture_root),
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            proof = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertFalse(proof["top_level_present"])
            self.assertEqual(proof["emotion"], 117)
            self.assertEqual(proof["run_count"], 0)
            final = json.loads(output_path.read_text(encoding="utf-8"))
            validate_config_marker(final, control.binding, control.config_ownership)
            self.assertIn(CONFIG_MARKER_FIELD, proof["marker"])

    @unittest.skipUnless(os.name == "nt", "Windows replace/delete contract")
    def test_replaceable_config_handles_and_exact_handle_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control, owned = make_owned_control(root)
            try:
                payload = {
                    "EventSp": {
                        "Storage": {"Storage": {}},
                        "Emotion": {"Fleet1Value": 119},
                        "StopCondition": {"RunCount": 1},
                    }
                }
                insert_config_marker(payload, control.binding, control.config_ownership)
                write_owned_file(owned["config"], canonical_json_bytes(payload))
                inherited_copy = os.dup(owned["config"].fd)
                owned["config"].close_parent()
                first_tmp = control.binding.config_path.with_suffix(".first.tmp")
                first_tmp.write_bytes(canonical_json_bytes(payload))
                with self.assertRaises(PermissionError):
                    os.replace(first_tmp, control.binding.config_path)
                os.close(inherited_copy)
                first_tmp.write_bytes(canonical_json_bytes(payload))
                os.replace(first_tmp, control.binding.config_path)
                payload["EventSp"]["Emotion"]["Fleet1Value"] = 117
                payload["EventSp"]["StopCondition"]["RunCount"] = 0
                second_tmp = control.binding.config_path.with_suffix(".second.tmp")
                second_tmp.write_bytes(canonical_json_bytes(payload))
                os.replace(second_tmp, control.binding.config_path)
                state = inspect_owned_config(control)
                self.assertTrue(state.marker_verified)
                final = json.loads(
                    control.binding.config_path.read_text(encoding="utf-8")
                )
                self.assertEqual(final["EventSp"]["Emotion"]["Fleet1Value"], 117)
                self.assertEqual(final["EventSp"]["StopCondition"]["RunCount"], 0)
                validate_control_lease(owned["control"], control)
                deleted = delete_owned_config_windows(owned["control"], control, state)
                self.assertTrue(deleted.deleted)
                self.assertFalse(control.binding.config_path.exists())
                owned["config"].owned = False
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows provenance cleanup contract")
    def test_config_cleanup_rejects_bad_provenance_and_identity(self):
        cases = (
            "missing_marker",
            "bad_binding",
            "nan_with_valid_marker",
            "duplicate_json",
            "oversize",
            "hardlink",
            "identity",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                control, owned = make_owned_control(root)
                sibling = control.binding.config_path.with_name("sibling.keep")
                try:
                    payload = {"EventSp": {"Storage": {"Storage": {}}}}
                    insert_config_marker(
                        payload, control.binding, control.config_ownership
                    )
                    write_owned_file(owned["config"], canonical_json_bytes(payload))
                    owned["config"].close_parent()
                    if case == "missing_marker":
                        payload["EventSp"]["Storage"]["Storage"].pop(
                            CONFIG_MARKER_FIELD
                        )
                        control.binding.config_path.write_bytes(
                            canonical_json_bytes(payload)
                        )
                    elif case == "bad_binding":
                        payload["EventSp"]["Storage"]["Storage"][CONFIG_MARKER_FIELD][
                            "run_id"
                        ] = uuid.uuid4().hex
                        control.binding.config_path.write_bytes(
                            canonical_json_bytes(payload)
                        )
                    elif case == "nan_with_valid_marker":
                        payload["EventSp"]["non_finite"] = float("nan")
                        control.binding.config_path.write_text(
                            json.dumps(payload, allow_nan=True), encoding="utf-8"
                        )
                    elif case == "duplicate_json":
                        control.binding.config_path.write_text(
                            '{"EventSp":{},"EventSp":{}}', encoding="utf-8"
                        )
                    elif case == "oversize":
                        control.binding.config_path.write_bytes(
                            b" " * (2 * 1024 * 1024 + 1)
                        )
                    elif case == "hardlink":
                        os.link(control.binding.config_path, sibling)
                    state = inspect_owned_config(control)
                    supplied = state
                    if case == "identity":
                        supplied = replace(
                            state,
                            identity=FileIdentity(
                                state.identity.volume_serial,
                                state.identity.file_id + 1,
                            ),
                        )
                    decision = delete_owned_config_windows(
                        owned["control"], control, supplied
                    )
                    self.assertFalse(decision.deleted)
                    self.assertIsNotNone(decision.blocker)
                    self.assertTrue(control.binding.config_path.exists())
                    self.assertTrue(owned["control"].path.exists())
                    if case == "hardlink":
                        self.assertTrue(sibling.exists())
                finally:
                    close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows provenance cleanup contract")
    def test_config_cleanup_rejects_directory_and_root_replacement(self):
        for case in ("directory", "root_replacement"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                control, owned = make_owned_control(root)
                original_root = control.config_ownership.config_root
                moved_root = original_root.with_name("config-original")
                try:
                    payload = {"EventSp": {"Storage": {"Storage": {}}}}
                    insert_config_marker(
                        payload, control.binding, control.config_ownership
                    )
                    write_owned_file(owned["config"], canonical_json_bytes(payload))
                    owned["config"].close_parent()
                    state = inspect_owned_config(control)
                    if case == "directory":
                        control.binding.config_path.unlink()
                        control.binding.config_path.mkdir()
                        supplied = inspect_owned_config(control)
                    else:
                        original_root.rename(moved_root)
                        original_root.mkdir()
                        control.binding.config_path.write_text(
                            "foreign root object", encoding="utf-8"
                        )
                        supplied = state
                    decision = delete_owned_config_windows(
                        owned["control"], control, supplied
                    )
                    self.assertFalse(decision.deleted)
                    self.assertIsNotNone(decision.blocker)
                    self.assertTrue(control.binding.config_path.exists())
                    self.assertTrue(owned["control"].path.exists())
                finally:
                    close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows provenance cleanup contract")
    def test_config_cleanup_rejects_symlink_without_skipping_root_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control, owned = make_owned_control(root)
            target = root / "symlink-target.keep"
            try:
                payload = {"EventSp": {"Storage": {"Storage": {}}}}
                insert_config_marker(payload, control.binding, control.config_ownership)
                write_owned_file(owned["config"], canonical_json_bytes(payload))
                owned["config"].close_parent()
                control.binding.config_path.unlink()
                target.write_text("foreign target", encoding="utf-8")
                try:
                    os.symlink(target, control.binding.config_path)
                except OSError as exc:
                    self.skipTest(
                        "Windows symlink creation is unavailable: " + str(exc)
                    )
                supplied = inspect_owned_config(control)
                decision = delete_owned_config_windows(
                    owned["control"], control, supplied
                )
                self.assertFalse(decision.deleted)
                self.assertIsNotNone(decision.blocker)
                self.assertTrue(control.binding.config_path.exists())
                self.assertTrue(target.exists())
                self.assertTrue(owned["control"].path.exists())
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows exact-handle cleanup contract")
    def test_foreign_replacement_after_handle_delete_is_preserved(self):
        from alas_headless import runner_supervision as supervision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control, owned = make_owned_control(root)
            sibling = control.binding.config_path.with_name("unrelated.keep")
            try:
                payload = {"EventSp": {"Storage": {"Storage": {}}}}
                insert_config_marker(payload, control.binding, control.config_ownership)
                write_owned_file(owned["config"], canonical_json_bytes(payload))
                owned["config"].close_parent()
                sibling.write_text("keep", encoding="utf-8")
                state = inspect_owned_config(control)
                real_identity = supervision.file_identity_from_path

                def inject_foreign(path):
                    path = Path(path)
                    if path == control.binding.config_path and not path.exists():
                        path.write_text("foreign replacement", encoding="utf-8")
                    return real_identity(path)

                with mock.patch(
                    "alas_headless.runner_supervision.file_identity_from_path",
                    side_effect=inject_foreign,
                ):
                    decision = delete_owned_config_windows(
                        owned["control"], control, state
                    )
                self.assertFalse(decision.deleted)
                self.assertTrue(decision.foreign_replacement)
                self.assertEqual(
                    decision.blocker,
                    "runner.cleanup.config_foreign_replacement_preserved",
                )
                self.assertEqual(
                    control.binding.config_path.read_text(encoding="utf-8"),
                    "foreign replacement",
                )
                self.assertEqual(sibling.read_text(encoding="utf-8"), "keep")
                self.assertTrue(owned["control"].path.exists())
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows reparse cleanup contract")
    def test_reparse_state_is_rejected_before_handle_disposition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control, owned = make_owned_control(root)
            try:
                payload = {"EventSp": {"Storage": {"Storage": {}}}}
                insert_config_marker(payload, control.binding, control.config_ownership)
                write_owned_file(owned["config"], canonical_json_bytes(payload))
                owned["config"].close_parent()
                state = inspect_owned_config(control)
                reparse_state = replace(
                    state,
                    attributes=(state.attributes or 0) | 0x400,
                    is_reparse_point=True,
                    marker_verified=False,
                    marker_error="config_is_reparse_point",
                )
                with mock.patch(
                    "alas_headless.runner_supervision._inspect_windows_config_handle",
                    return_value=reparse_state,
                ):
                    decision = delete_owned_config_windows(
                        owned["control"], control, reparse_state
                    )
                self.assertFalse(decision.deleted)
                self.assertEqual(
                    decision.blocker,
                    "runner.cleanup.config_provenance_invalid",
                )
                self.assertTrue(control.binding.config_path.exists())
                self.assertTrue(owned["control"].path.exists())
            finally:
                close_owned_files(owned)

    @unittest.skipUnless(os.name == "nt", "Windows CloseHandle cleanup contract")
    def test_config_delete_close_failure_is_reported_and_retains_control(self):
        from alas_headless import runner_supervision as supervision

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            control, owned = make_owned_control(root)
            try:
                payload = {"EventSp": {"Storage": {"Storage": {}}}}
                insert_config_marker(payload, control.binding, control.config_ownership)
                write_owned_file(owned["config"], canonical_json_bytes(payload))
                owned["config"].close_parent()
                state = inspect_owned_config(control)
                real_close = supervision._windows_close_handle
                close_calls = 0

                def fail_final_close(kernel32, handle):
                    nonlocal close_calls
                    close_calls += 1
                    real_close(kernel32, handle)
                    if close_calls == 3:
                        raise OSError("scripted config handle close failure")

                with mock.patch(
                    "alas_headless.runner_supervision._windows_close_handle",
                    side_effect=fail_final_close,
                ):
                    decision = delete_owned_config_windows(
                        owned["control"], control, state
                    )
                self.assertEqual(close_calls, 3)
                self.assertFalse(decision.deleted)
                self.assertEqual(
                    decision.blocker,
                    "runner.cleanup.config_handle_close_failed",
                )
                self.assertTrue(owned["control"].path.exists())
            finally:
                close_owned_files(owned)

    def test_wait_return_at_deadline_is_always_deadline(self):
        clock = iter((9.0, 10.0))
        result = supervise_process(
            FakeProcess((0,)),
            FakeJob(active=0),
            absolute_deadline=10.0,
            monotonic=lambda: next(clock),
        )
        self.assertEqual(result.reason, "deadline")
        self.assertEqual(result.termination_mode, "deadline_late_exit")

    def test_deadline_ctrl_break_then_terminates_job(self):
        timeout = subprocess.TimeoutExpired(["worker"], 1)
        process = FakeProcess((timeout, timeout, 124))
        job = FakeJob(active=1)

        def no_console(_process):
            raise OSError("no console")

        from alas_headless.runner_supervision import shutdown_worker

        result = supervise_process(
            process,
            job,
            absolute_deadline=10.0,
            monotonic=lambda: 10.0,
            shutdown=lambda process, job, reason: shutdown_worker(
                process,
                job,
                reason=reason,
                send_cooperative_stop=no_console,
                cleanup_grace_seconds=0,
                force_stop_grace_seconds=0,
            ),
        )
        self.assertEqual(result.reason, "deadline")
        self.assertEqual(result.termination_mode, "deadline_terminated_job")
        self.assertTrue(job.terminated)
        self.assertTrue(result.termination_confirmed)
        self.assertIn("ctrl_break:OSError:sha256:", " ".join(result.errors))
        self.assertNotIn("no console", " ".join(result.errors))

    def test_all_escalation_errors_leave_explicit_unconfirmed_result(self):
        timeout = subprocess.TimeoutExpired(["worker"], 1)
        process = FakeProcess((timeout, timeout, timeout, timeout, timeout))
        process.terminate = lambda: (_ for _ in ()).throw(OSError("terminate failed"))
        process.kill = lambda: (_ for _ in ()).throw(OSError("kill failed"))
        job = FakeJob(
            active=1,
            terminate_error=OSError("job terminate failed"),
            remain_active=True,
        )

        def broken_break(_process):
            raise OSError("break failed")

        from alas_headless.runner_supervision import shutdown_worker

        result = supervise_process(
            process,
            job,
            absolute_deadline=1.0,
            monotonic=lambda: 1.0,
            shutdown=lambda process, job, reason: shutdown_worker(
                process,
                job,
                reason=reason,
                send_cooperative_stop=broken_break,
                cleanup_grace_seconds=0,
                force_stop_grace_seconds=0,
            ),
        )
        self.assertFalse(result.termination_confirmed)
        self.assertEqual(result.termination_mode, "deadline_unconfirmed")
        joined = " ".join(result.errors)
        for message in (
            "ctrl_break:OSError:sha256:",
            "job_terminate:OSError:sha256:",
            "terminate:OSError:sha256:",
            "kill:OSError:sha256:",
        ):
            self.assertIn(message, joined)
        for secret_body in (
            "break failed",
            "job terminate failed",
            "terminate failed",
            "kill failed",
        ):
            self.assertNotIn(secret_body, joined)

    def test_empty_unassigned_job_does_not_masquerade_as_dead_worker(self):
        timeout = subprocess.TimeoutExpired(["worker"], 1)
        process = FakeProcess((timeout, timeout, timeout, 1))
        job = FakeJob(active=0)

        def no_break(_process):
            raise OSError("no process group")

        from alas_headless.runner_supervision import shutdown_worker

        result = supervise_process(
            process,
            job,
            absolute_deadline=1.0,
            monotonic=lambda: 1.0,
            shutdown=lambda process, job, reason: shutdown_worker(
                process,
                job,
                reason=reason,
                send_cooperative_stop=no_break,
                cleanup_grace_seconds=0,
                force_stop_grace_seconds=0,
            ),
        )
        self.assertTrue(process.terminated)
        self.assertTrue(result.termination_confirmed)
        self.assertEqual(result.termination_mode, "deadline_terminated_worker")

    def test_keyboard_interrupt_and_generic_wait_errors_are_distinct(self):
        from alas_headless.runner_supervision import shutdown_worker

        for exception, reason in (
            (KeyboardInterrupt(), "interrupted"),
            (RuntimeError("wait broke"), "supervision_error"),
        ):
            with self.subTest(reason=reason):
                process = FakeProcess((exception, 130))
                result = supervise_process(
                    process,
                    FakeJob(active=0),
                    absolute_deadline=20.0,
                    monotonic=lambda: 0.0,
                    shutdown=lambda process, job, reason: shutdown_worker(
                        process,
                        job,
                        reason=reason,
                        send_cooperative_stop=lambda _process: None,
                        cleanup_grace_seconds=0,
                        force_stop_grace_seconds=0,
                    ),
                )
                self.assertEqual(result.reason, reason)
                self.assertTrue(result.termination_confirmed)

    @unittest.skipUnless(os.name == "nt", "Windows Job/process-group contract")
    def test_windows_job_ctrl_break_unwinds_finally_and_becomes_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "finally.txt"
            ready = Path(directory) / "ready.txt"
            code = (
                "import pathlib,time;"
                "from alas_headless.runner_supervision import install_worker_stop_handler;"
                "restore=install_worker_stop_handler();"
                "pathlib.Path(r'%s').write_text('ready');"
                "\ntry:\n"
                "  while True: time.sleep(0.05)\n"
                "finally:\n"
                "  pathlib.Path(r'%s').write_text('closed'); restore()\n"
            ) % (ready, marker)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(
                Path(__file__).resolve().parents[1] / "python"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", code],
                env=environment,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            job = WindowsWorkerJob()
            try:
                job.assign(process)
                deadline = time.monotonic() + 5.0
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                result = supervise_process(
                    process,
                    job,
                    absolute_deadline=time.monotonic(),
                )
                self.assertEqual(result.reason, "deadline")
                self.assertTrue(result.termination_confirmed)
                self.assertEqual(job.active_process_count(), 0)
                self.assertEqual(marker.read_text(encoding="utf-8"), "closed")
            finally:
                job.close()

    @unittest.skipUnless(os.name == "nt", "Windows kill-on-close Job contract")
    def test_windows_parent_abrupt_exit_kills_contained_worker(self):
        """A parent crash closes its Job and cannot orphan the worker host."""

        import ctypes
        from ctypes import wintypes

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_pid_path = root / "child-pid.txt"
            child_ready_path = root / "child-ready.txt"
            child_code = (
                "import pathlib,time;"
                "pathlib.Path({0!r}).write_text('ready', encoding='utf-8');"
                "time.sleep(60)"
            ).format(str(child_ready_path))
            parent_code = (
                "import os,pathlib,subprocess,sys,time;"
                "from alas_headless.runner_supervision import WindowsWorkerJob;"
                "child=subprocess.Popen([sys.executable,'-c',{0!r}],"
                "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP);"
                "job=WindowsWorkerJob();job.assign(child);"
                "pathlib.Path({1!r}).write_text(str(child.pid),encoding='utf-8');"
                "deadline=time.monotonic()+5;"
                "\nwhile not pathlib.Path({2!r}).exists() and time.monotonic()<deadline:"
                " time.sleep(0.02)\n"
                "os._exit(23)"
            ).format(child_code, str(child_pid_path), str(child_ready_path))
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(
                Path(__file__).resolve().parents[1] / "python"
            )
            parent = subprocess.Popen(
                [sys.executable, "-c", parent_code],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            stdout, stderr = parent.communicate(timeout=10)
            self.assertEqual(parent.returncode, 23, stdout + stderr)
            self.assertTrue(child_pid_path.exists(), stdout + stderr)
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            open_process.restype = wintypes.HANDLE
            wait_for_single = kernel32.WaitForSingleObject
            wait_for_single.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            wait_for_single.restype = wintypes.DWORD
            terminate = kernel32.TerminateProcess
            terminate.argtypes = (wintypes.HANDLE, wintypes.UINT)
            terminate.restype = wintypes.BOOL
            close = kernel32.CloseHandle
            close.argtypes = (wintypes.HANDLE,)
            close.restype = wintypes.BOOL

            # SYNCHRONIZE | PROCESS_TERMINATE.  A missing handle also proves
            # that the exact test-owned PID no longer exists.
            handle = open_process(0x00100001, False, child_pid)
            if handle:
                try:
                    wait_result = wait_for_single(handle, 5000)
                    if wait_result != 0:  # WAIT_OBJECT_0
                        terminate(handle, 125)
                    self.assertEqual(wait_result, 0)
                finally:
                    close(handle)


if __name__ == "__main__":
    unittest.main()
