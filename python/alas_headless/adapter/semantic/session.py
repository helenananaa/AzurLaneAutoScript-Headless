"""Session for the typed ALAS boundary."""

from __future__ import annotations

import os
import re
import time
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple
from ...adapter import (
    ActionLedger,
    AdbRuntimeHandleFactory,
    CapabilityClosureError,
    CapabilityInventory,
    DEFAULT_CAPABILITY_INVENTORY,
    PixelAccessAudit,
    PixelAccessOperation,
    PixelAccessRecord,
    RecoveryPolicy,
    RunPolicy,
    RuntimeHandlePackageGate,
    RuntimeHandlePort,
    SemanticFrame,
    SemanticFrameClock,
    SemanticFrameReader,
    SemanticPixelGuard,
    StaleFrameError,
    TaskCapabilityProfile,
    compatibility_policy_sha256,
    compatibility_profile,
    semantic_runtime_fingerprint_sha256,
    translate_legacy_semantic_environment,
)
from ...alas_combat_observer import AlasCombatObserverManifest
from ...alas_package_process_lease import AlasPackageProcessLease
from ...runtime_trace import RuntimeTraceRecorder
from ...semantic_oracle import (
    ActionReceipt,
    ObserverTransportError,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)
from .adapter import AlasSemanticAdapter
from .legacy import _legacy_action_grants
from .session_combat import SessionCombatPorts
from .session_dispatch import SessionDispatchPorts
from .session_opsi import SessionOpsiPorts
from .session_tasks import SessionTasksPorts


class AlasSemanticSession(SessionTasksPorts, SessionCombatPorts, SessionDispatchPorts, SessionOpsiPorts):
    """Own the runtime handle and refresh the immutable semantic frame."""

    _REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")

    _LOGIN_STARTUP_UPDATE_STALE_RETRY_ATTEMPTS = 2399

    _INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 799

    _LIVE_COMBAT_DRIVER_COMPATIBILITY = frozenset(
        {
            (
                "be80ce591a481c12d60c50d6040d40c035b40a2b",
                "506b76f698b5089aaa29c4e7908b48edb8532a44",
            ),
        }
    )

    def __init__(
        self,
        serial: Optional[str] = None,
        driver_revision: str = "",
        adb: Optional[str] = None,
        package: str = "com.bilibili.azurlane",
        component: str = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        ),
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        mail_mutation_budget: int = 0,
        minigame_play_budget: int = 0,
        meta_assist_budget: int = 0,
        operation_siren_coordinate_checkout_budget: int = 0,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        daily_execute_budget: int = 0,
        exercise_execute_budget: int = 0,
        exercise_refresh_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        awaken_budget: int = 0,
        enhancement_budget: int = 0,
        build_submit_budget: int = 0,
        retirement_budget: int = 0,
        shop_purchase_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
        campaign_camera_positioning_budget: int = 0,
        adb_command_timeout_seconds: int = 10,
        observer_max_age_ms: int = 10000,
        package_process_lease: Optional[AlasPackageProcessLease] = None,
        trace: Optional[RuntimeTraceRecorder] = None,
        runtime_handle: Optional[RuntimeHandlePort] = None,
        run_policy: Optional[RunPolicy] = None,
        policy_grants: Optional[Mapping[str, int]] = None,
        capability_profile: Optional[TaskCapabilityProfile] = None,
        capability_inventory: Optional[CapabilityInventory] = None,
        adb_server_port: int = 5037,
        required_primary_abi: str = "x86_64",
    ) -> None:
        if runtime_handle is None and not serial:
            raise ValueError(
                "semantic ALAS mode requires an ADB serial or runtime handle"
            )
        if runtime_handle is not None:
            if not isinstance(runtime_handle, RuntimeHandlePort):
                raise TypeError("semantic ALAS runtime handle is incomplete")
            if serial is not None or adb is not None:
                raise ValueError(
                    "runtime handle conflicts with ADB serial or executable"
                )
            if adb_command_timeout_seconds != 10:
                raise ValueError("runtime handle conflicts with ADB timeout")
            if adb_server_port != 5037:
                raise ValueError("runtime handle conflicts with ADB server port")
        if not self._REVISION_PATTERN.fullmatch(driver_revision):
            raise ValueError("semantic ALAS mode requires a pinned ANGLE revision")
        if (
            isinstance(adb_command_timeout_seconds, bool)
            or not isinstance(adb_command_timeout_seconds, int)
            or not 1 <= adb_command_timeout_seconds <= 120
        ):
            raise ValueError("semantic ALAS ADB timeout must be in [1, 120]")
        if (
            isinstance(adb_server_port, bool)
            or not isinstance(adb_server_port, int)
            or not 1 <= adb_server_port <= 65535
        ):
            raise ValueError("semantic ALAS ADB server port must be in [1, 65535]")
        if (
            not isinstance(required_primary_abi, str)
            or not required_primary_abi
        ):
            raise ValueError("semantic ALAS required primary ABI is missing")
        if (
            isinstance(observer_max_age_ms, bool)
            or not isinstance(observer_max_age_ms, int)
            or not 1 <= observer_max_age_ms <= 300000
        ):
            raise ValueError("semantic ALAS observer max age must be in [1, 300000]")
        if package_process_lease is not None and not isinstance(
            package_process_lease, AlasPackageProcessLease
        ):
            raise ValueError("semantic ALAS package lease is not verified")
        self.serial = serial
        self.driver_revision = driver_revision
        self.package = package
        self.component = component
        self.required_primary_abi = required_primary_abi
        self.allow_mission_claim_once = bool(allow_mission_claim_once)
        self.allow_mail_mutations = bool(allow_mail_mutations)
        self.mail_mutation_budget = mail_mutation_budget
        self.minigame_play_budget = minigame_play_budget
        self.meta_assist_budget = meta_assist_budget
        self.operation_siren_coordinate_checkout_budget = (
            operation_siren_coordinate_checkout_budget
        )
        self.allow_tactical_rewards = bool(allow_tactical_rewards)
        for label, budget in (
            ("mail mutation", mail_mutation_budget),
            ("minigame play", minigame_play_budget),
            ("META assist", meta_assist_budget),
            (
                "Operation Siren coordinate checkout",
                operation_siren_coordinate_checkout_budget,
            ),
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("daily execute", daily_execute_budget),
            ("exercise execute", exercise_execute_budget),
            ("exercise refresh", exercise_refresh_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("awaken", awaken_budget),
            ("enhancement", enhancement_budget),
            ("build submit", build_submit_budget),
            ("retirement", retirement_budget),
            ("shop purchase", shop_purchase_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
            ("campaign camera positioning", campaign_camera_positioning_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        if campaign_camera_positioning_budget > 2:
            raise ValueError(
                "campaign camera positioning budget must be at most two"
            )
        self.commission_reward_budget = commission_reward_budget
        self.tactical_assign_budget = tactical_assign_budget
        self.commission_start_budget = commission_start_budget
        self.daily_execute_budget = daily_execute_budget
        self.exercise_execute_budget = exercise_execute_budget
        self.exercise_refresh_budget = exercise_refresh_budget
        self.research_reward_budget = research_reward_budget
        self.research_start_budget = research_start_budget
        self.dorm_collect_budget = dorm_collect_budget
        self.dorm_feed_budget = dorm_feed_budget
        self.awaken_budget = awaken_budget
        self.enhancement_budget = enhancement_budget
        self.build_submit_budget = build_submit_budget
        self.retirement_budget = retirement_budget
        self.shop_purchase_budget = shop_purchase_budget
        self.campaign_stage_entry_budget = campaign_stage_entry_budget
        self.campaign_fleet_mutation_budget = campaign_fleet_mutation_budget
        self.campaign_sortie_budget = campaign_sortie_budget
        self.campaign_combat_budget = campaign_combat_budget
        self.campaign_viewport_swipe_budget = campaign_viewport_swipe_budget
        self.campaign_camera_positioning_budget = (
            campaign_camera_positioning_budget
        )
        self.package_process_lease = package_process_lease
        self.observer_max_age_ms = observer_max_age_ms
        self.trace = trace
        if run_policy is not None and not isinstance(run_policy, RunPolicy):
            raise TypeError("semantic run policy is invalid")
        self.run_policy = run_policy
        if policy_grants is not None and not isinstance(policy_grants, Mapping):
            raise TypeError("semantic policy grants are invalid")
        legacy_grants = _legacy_action_grants(
            allow_mission_claim_once=allow_mission_claim_once,
            allow_mail_mutations=allow_mail_mutations,
            mail_mutation_budget=mail_mutation_budget,
            minigame_play_budget=minigame_play_budget,
            meta_assist_budget=meta_assist_budget,
            operation_siren_coordinate_checkout_budget=(
                operation_siren_coordinate_checkout_budget
            ),
            allow_tactical_rewards=allow_tactical_rewards,
            tactical_assign_budget=tactical_assign_budget,
            commission_reward_budget=commission_reward_budget,
            commission_start_budget=commission_start_budget,
            daily_execute_budget=daily_execute_budget,
            exercise_execute_budget=exercise_execute_budget,
            exercise_refresh_budget=exercise_refresh_budget,
            research_reward_budget=research_reward_budget,
            research_start_budget=research_start_budget,
            dorm_collect_budget=dorm_collect_budget,
            dorm_feed_budget=dorm_feed_budget,
            awaken_budget=awaken_budget,
            enhancement_budget=enhancement_budget,
            build_submit_budget=build_submit_budget,
            retirement_budget=retirement_budget,
            shop_purchase_budget=shop_purchase_budget,
            campaign_stage_entry_budget=campaign_stage_entry_budget,
            campaign_fleet_mutation_budget=campaign_fleet_mutation_budget,
            campaign_sortie_budget=campaign_sortie_budget,
            campaign_combat_budget=campaign_combat_budget,
            campaign_viewport_swipe_budget=campaign_viewport_swipe_budget,
            campaign_camera_positioning_budget=campaign_camera_positioning_budget,
        )
        effective_grants = dict(policy_grants or legacy_grants)
        self.policy_grants = MappingProxyType(effective_grants)
        if capability_profile is not None and not isinstance(
            capability_profile, TaskCapabilityProfile
        ):
            raise TypeError("semantic capability profile is invalid")
        if capability_inventory is None:
            capability_inventory = DEFAULT_CAPABILITY_INVENTORY
        elif not isinstance(capability_inventory, CapabilityInventory):
            raise TypeError("semantic capability inventory is invalid")
        recovery_policy = (
            run_policy.recovery_policy
            if run_policy is not None
            else RecoveryPolicy.QUALIFICATION_STOP
        )
        if capability_profile is None:
            capability_profile = (
                TaskCapabilityProfile(profile_id=run_policy.profile_id)
                if run_policy is not None
                else compatibility_profile("legacy-session", effective_grants)
            )
        if (
            run_policy is not None
            and capability_profile.profile_id != run_policy.profile_id
        ):
            raise CapabilityClosureError()
        if (
            run_policy is not None
            and capability_profile.task_config_sha256
            != run_policy.task_config_sha256
        ):
            raise CapabilityClosureError()
        policy_sha256 = (
            run_policy.sha256
            if run_policy is not None
            else compatibility_policy_sha256(
                capability_profile.profile_id,
                effective_grants,
                recovery_policy,
            )
        )
        self.action_ledger = ActionLedger(
            profile=capability_profile,
            inventory=capability_inventory,
            grants=effective_grants,
            recovery_policy=recovery_policy,
            policy_sha256=policy_sha256,
        )
        self.capability_report = self.action_ledger.require_preflight()
        self._pixel_audit = PixelAccessAudit(self._record_pixel_access)
        self.expected_runtime_fingerprint_sha256 = (
            semantic_runtime_fingerprint_sha256(
                package=package,
                component=component,
                driver_revision=driver_revision,
                required_primary_abi=required_primary_abi,
            )
        )
        self._runtime_handle = runtime_handle
        self._package_gate: Optional[Callable[[], None]] = None
        self._runtime_handle_factory: Optional[AdbRuntimeHandleFactory] = None
        self._frame_clock: Optional[SemanticFrameClock] = None
        self._frame_reader: Optional[SemanticFrameReader] = None
        if runtime_handle is None:
            self._runtime_handle_factory = AdbRuntimeHandleFactory(
                serial=serial or "",
                package=package,
                adb=adb or "adb",
                adb_server_port=adb_server_port,
                command_timeout_seconds=float(adb_command_timeout_seconds),
                fingerprint_sha256=self.expected_runtime_fingerprint_sha256,
                driver_revision=driver_revision,
                required_primary_abi=required_primary_abi,
                process_lease=package_process_lease,
                trace=trace,
            )
        self.adapter: Optional[AlasSemanticAdapter] = None
        # META owns a complete task rather than one observer frame.  Keep the
        # ownership lease on the session so rebuilding the Oracle/adapter does
        # not silently turn an own-beacon confirmation into an assist action.
        self._meta_beacon_active = False
        self._combat_manifest: Optional[AlasCombatObserverManifest] = None
        self._combat_last_generation = 0
        self._combat_automation_source: Optional[str] = None
        self._combat_result_transition_until = 0.0
        self._combat_result_observation: Optional[Tuple[str, float]] = None
        self._combat_last_result_receipt: Optional[ActionReceipt] = None
        self._login_update_restart_performed = False
        self._game_manager_restart_pending = False

    def discard_task_state(self) -> None:
        """Release observations and intents while retaining runtime and grants."""
        if self.adapter is not None:
            self.adapter.reset_task_state()
        if self._frame_clock is not None:
            self._frame_clock.release_frame()
        self._meta_beacon_active = False
        self._opsi_sample_use = None
        self._combat_automation_source = None
        self._combat_result_observation = None
        self._combat_last_result_receipt = None
        self._combat_result_transition_until = 0.0
        self._daily_combat_seen_at = float("-inf")
        self._login_update_restart_performed = False
        self._game_manager_restart_pending = False

    def _record_pixel_access(self, record: PixelAccessRecord) -> None:
        if self.trace is not None:
            self.trace.emit(
                "semantic.pixel.unsupported",
                outcome="error",
                fields={
                    "ordinal": record.ordinal,
                    "frame_id": record.frame_id,
                    "generation": record.generation,
                    "operation": record.operation.value,
                    "consumer": record.consumer,
                },
            )

    def pixel_access_records(self) -> tuple[PixelAccessRecord, ...]:
        return self._pixel_audit.records()

    def pixel_guard(self, frame: SemanticFrame) -> SemanticPixelGuard:
        if self._frame_clock is None:
            raise StaleFrameError()
        current = self._frame_clock.borrow(frame.frame_id)
        if current is not frame:
            raise StaleFrameError()
        return SemanticPixelGuard(frame, self._pixel_audit)

    def reject_pixel_access(
        self,
        operation: str,
        consumer: str,
    ) -> None:
        try:
            classified = PixelAccessOperation(operation)
        except (TypeError, ValueError) as exc:
            raise ValueError("pixel access operation is not classified") from exc
        if self._frame_clock is None:
            raise StaleFrameError()
        frame = self._frame_clock.borrow()
        self._pixel_audit.reject(frame, classified, consumer)

    @property
    def runtime_handle(self) -> Optional[RuntimeHandlePort]:
        return self._runtime_handle

    def _prepare_explicit_runtime_handle(self) -> RuntimeHandlePort:
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("explicit runtime handle is unavailable")
        package_gate = RuntimeHandlePackageGate(
            handle=handle,
            expected_fingerprint_sha256=(
                self.expected_runtime_fingerprint_sha256
            ),
            package=self.package,
            driver_revision=self.driver_revision,
            process_lease=self.package_process_lease,
        )
        package_gate()
        self._package_gate = package_gate
        return handle

    def _release_owned_runtime_handle(self) -> None:
        if self._frame_clock is not None:
            self._frame_clock.close()
        self._frame_clock = None
        self._frame_reader = None
        if self._runtime_handle_factory is not None:
            self._runtime_handle_factory.close()
            self._runtime_handle = None
        self._package_gate = None

    @classmethod
    def from_environment(
        cls,
        serial: str,
        *,
        run_policy: Optional[RunPolicy] = None,
        trace: Optional[RuntimeTraceRecorder] = None,
    ) -> "AlasSemanticSession":
        translation = translate_legacy_semantic_environment(
            os.environ,
            explicit_policy=run_policy,
            trace=trace,
        )
        return cls(
            serial=serial,
            **translation.session_arguments,
            trace=trace,
            run_policy=run_policy,
            policy_grants=translation.grants,
        )

    def open(self) -> AlasSemanticAdapter:
        if self.adapter is not None:
            return self.adapter
        try:
            if self._runtime_handle is None:
                factory = self._runtime_handle_factory
                if factory is None:
                    raise SemanticGateClosed(
                        "semantic runtime handle factory is unavailable"
                    )
                prepared = factory()
                self._runtime_handle = prepared.handle
                self._package_gate = prepared.package_gate
            elif self._package_gate is None:
                self._prepare_explicit_runtime_handle()
            handle = self._runtime_handle
            package_gate = self._package_gate
            if handle is None or package_gate is None:
                raise SemanticGateClosed("semantic runtime handle is unavailable")
            package_gate()

            def invalidate_current_frame() -> None:
                frame_clock = self._frame_clock
                if frame_clock is None or frame_clock.current_frame_id is None:
                    return
                frame_id = frame_clock.current_frame_id
                # A semantic target is re-read immediately before input, but
                # that does not authorize input from an expired ALAS frame.
                # Keep the final mutation boundary fail closed as well.
                frame_clock.borrow(frame_id, require_fresh=True)
                frame_clock.invalidate(frame_id)

            def invalidate_then_tap(x: int, y: int) -> None:
                invalidate_current_frame()
                handle.tap(x, y)

            def invalidate_then_swipe(
                x1: int,
                y1: int,
                x2: int,
                y2: int,
                duration_ms: int,
            ) -> None:
                invalidate_current_frame()
                handle.swipe(x1, y1, x2, y2, duration_ms)

            oracle = SemanticOracle(
                handle.observer_request,
                handle.foreground_component,
                invalidate_then_tap,
                OracleFingerprint(
                    package=self.package,
                    component=self.component,
                    driver_revision=self.driver_revision,
                    expected_pid=handle.pid,
                    max_age_ms=self.observer_max_age_ms,
                ),
                swipe=invalidate_then_swipe,
            )
            self._frame_clock = SemanticFrameClock(handle, oracle)
            self._frame_reader = SemanticFrameReader(self._frame_clock, oracle)
            self.adapter = AlasSemanticAdapter(
                oracle,
                package_gate,
                allow_mission_claim_once=self.allow_mission_claim_once,
                allow_mail_mutations=self.allow_mail_mutations,
                mail_mutation_budget=self.mail_mutation_budget,
                minigame_play_budget=self.minigame_play_budget,
                meta_assist_budget=self.meta_assist_budget,
                operation_siren_coordinate_checkout_budget=(
                    self.operation_siren_coordinate_checkout_budget
                ),
                allow_tactical_rewards=self.allow_tactical_rewards,
                tactical_assign_budget=self.tactical_assign_budget,
                commission_reward_budget=self.commission_reward_budget,
                commission_start_budget=self.commission_start_budget,
                daily_execute_budget=self.daily_execute_budget,
                exercise_execute_budget=self.exercise_execute_budget,
                exercise_refresh_budget=self.exercise_refresh_budget,
                research_reward_budget=self.research_reward_budget,
                research_start_budget=self.research_start_budget,
                dorm_collect_budget=self.dorm_collect_budget,
                dorm_feed_budget=self.dorm_feed_budget,
                awaken_budget=self.awaken_budget,
                enhancement_budget=self.enhancement_budget,
                build_submit_budget=self.build_submit_budget,
                retirement_budget=self.retirement_budget,
                shop_purchase_budget=self.shop_purchase_budget,
                campaign_stage_entry_budget=self.campaign_stage_entry_budget,
                campaign_fleet_mutation_budget=(
                    self.campaign_fleet_mutation_budget
                ),
                campaign_sortie_budget=self.campaign_sortie_budget,
                campaign_combat_budget=self.campaign_combat_budget,
                campaign_viewport_swipe_budget=(
                    self.campaign_viewport_swipe_budget
                ),
                campaign_camera_positioning_budget=(
                    self.campaign_camera_positioning_budget
                ),
                frame_observation_oracle=self._frame_reader.oracle,
                frame_identity_provider=self._frame_reader.identity,
                input_frame_refresher=self.refresh_frame,
                tactical_input_frame_refresher=self.refresh_tactical_input_frame,
                action_ledger=self.action_ledger,
            )
            if self._meta_beacon_active:
                self.adapter.begin_meta_beacon()
            if self.trace is not None:
                self.trace.emit(
                    "semantic.session.open",
                    fields={"observer_max_age_ms": self.observer_max_age_ms},
                )
            return self.adapter
        except Exception as exc:
            if self.trace is not None:
                self.trace.emit(
                    "semantic.session.open",
                    outcome="error",
                    fields={"exception_type": type(exc).__name__},
                )
            self._release_owned_runtime_handle()
            raise

    def close(self) -> None:
        self.adapter = None
        self.action_ledger.close()
        self._release_owned_runtime_handle()
        if self.trace is not None:
            self.trace.emit("semantic.session.close")

    def refresh_frame(self, *, include_ui: bool = True) -> SemanticFrame:
        self.open()
        if self._frame_clock is None:
            raise StaleFrameError()
        previous_frame_id = self._frame_clock.current_frame_id
        # A Unity transition can keep changing the full hierarchy while the
        # atomic Button/state endpoint is already healthy.  ALAS screenshots
        # are polling boundaries, so retry only this explicit cross-generation
        # condition and still fail closed for every other semantic error.
        attempt = 0
        while True:
            try:
                frame = self._frame_clock.acquire(include_ui=include_ui)
                break
            except (
                SemanticGateClosed,
                StaleFrameError,
                ObserverTransportError,
            ) as exc:
                message = str(exc)
                # Legacy observers may publish every two seconds. After a
                # committed input, wait for a newer generation instead of
                # retrying the same invalidated frame only for 300 ms.
                input_generation_retry = bool(
                    isinstance(exc, StaleFrameError)
                    and getattr(self._frame_clock, "_invalidated_generation", None) is not None
                    and attempt < 20
                )
                retryable = isinstance(exc, StaleFrameError) or message in (
                    "semantic frame mixes UI and state generations",
                    "observer snapshot is stale",
                    "observer endpoints are not generation-coherent",
                    "game activity is not top-resumed",
                )
                login_snapshot = self.open()._login_flow.snapshot()
                in_login_transition = bool(
                    login_snapshot.active
                    and time.monotonic()
                    <= login_snapshot.passive_transition_until
                )
                stale_login_update_wait = bool(
                    login_snapshot.active
                    and not in_login_transition
                    and isinstance(exc, SemanticGateClosed)
                    and message == "observer snapshot is stale"
                    and self.open().oracle.stale_login_update_in_progress()
                    and attempt < self._LOGIN_STARTUP_UPDATE_STALE_RETRY_ATTEMPTS
                )
                extended_login_retry = bool(
                    in_login_transition
                    and (
                        isinstance(exc, ObserverTransportError)
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 399
                )
                initial_game_startup_retry = bool(
                    previous_frame_id is None
                    and (
                        (
                            isinstance(exc, ObserverTransportError)
                            and message == "observer is unavailable"
                        )
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message == "game activity is not top-resumed"
                        )
                    )
                    and attempt < self._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS
                )
                in_combat_result_transition = bool(
                    time.monotonic() <= self._combat_result_transition_until
                )
                extended_combat_result_retry = bool(
                    in_combat_result_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 79
                )
                campaign_context = getattr(self.adapter, "_campaign_context", None)
                in_campaign_transition = bool(
                    campaign_context is not None
                    and time.monotonic()
                    <= float(campaign_context.passive_transition_until)
                )
                extended_campaign_retry = bool(
                    in_campaign_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 199
                )
                semantic_adapter = self.open()
                in_operation_siren_transition = bool(
                    time.monotonic()
                    <= max(
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_entry_transition_until",
                                0.0,
                            )
                        ),
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_auto_search_transition_until",
                                0.0,
                            )
                        ),
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_page_remount_until",
                                0.0,
                            )
                        ),
                    )
                )
                extended_operation_siren_retry = bool(
                    in_operation_siren_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "typed main-thread UI probe is incomplete",
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 79
                )
                retryable = retryable or bool(
                    in_login_transition and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_combat_result_transition
                    and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_campaign_transition
                    and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_operation_siren_transition
                    and (
                        isinstance(exc, ObserverTransportError)
                        or message == "typed main-thread UI probe is incomplete"
                    )
                )
                retryable = retryable or initial_game_startup_retry
                if not retryable or (
                    attempt >= 2
                    and not input_generation_retry
                    and not initial_game_startup_retry
                    and not extended_login_retry
                    and not stale_login_update_wait
                    and not extended_combat_result_retry
                    and not extended_campaign_retry
                    and not extended_operation_siren_retry
                ):
                    raise
                attempt += 1
                time.sleep(0.15)
        # Keep an exact result-action transition lease until its short deadline.
        # META and other multi-page result stacks can expose one coherent page
        # between two transient hierarchy rebuilds; clearing on that first page
        # made the following rebuild fail as an unrelated stale frame.
        if self.trace is not None:
            self.trace.emit(
                "semantic.frame.refresh",
                fields={
                    "previous_frame_id": previous_frame_id,
                    "frame_id": frame.frame_id,
                    "generation": frame.generation,
                },
            )
        return frame

    _OPERATION_SIREN_COMBAT_OBSERVER_GAP_MESSAGES = (
        "observer snapshot is stale",
        "observer endpoints are not generation-coherent",
        "combat fixture endpoint completeness changed",
        "combat fixture endpoint generations disagree",
    )

    def restart_game_after_update(self) -> bool:
        if self._login_update_restart_performed:
            return False
        adapter = self.open()
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # The exact NetworkDown prompt is mutually exclusive with the
            # reviewed update-restart contract.  Let the original following
            # handle_popup_confirm("UI_ADDITIONAL") branch consume it.
            return False
        try:
            explicit_prompt = adapter.login_update_restart_prompt_available()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise
        try:
            if explicit_prompt:
                # The prompt matcher performs a coherent multi-endpoint read. Get
                # one fresh ALAS frame immediately before its owned confirmation
                # input, just like the normal session click boundary.
                self.refresh_frame()
                adapter = self.open()
                adapter.click_login_update_restart_prompt()
                if self.trace is not None:
                    self.trace.emit("semantic.login.update_restart_prompt")
            elif not self._login_update_restart_required_on_frame(adapter):
                return False
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise
        factory = self._runtime_handle_factory
        if factory is None or self.package_process_lease is not None:
            raise SemanticGateClosed(
                "post-update game restart requires an owned ADB runtime"
            )
        adapter.end_login()
        self.adapter = None
        self._release_owned_runtime_handle()
        factory.restart_game(self.component)
        # This session may rebuild its Oracle before Unity has removed the
        # completion text. Preserve exactly one restart across that rebuild.
        self._login_update_restart_performed = True
        self.begin_login()
        # Unity can expose the newly-created observer socket before its first
        # post-update scene frame is fresh. Scope the longer grace to this one
        # owned cold-restart recovery; normal transitions retain their existing
        # short stale-frame limit.
        self.open()._login_flow.extend_passive_transition(120.0)
        if self.trace is not None:
            self.trace.emit("semantic.login.update_restart")
        return True
