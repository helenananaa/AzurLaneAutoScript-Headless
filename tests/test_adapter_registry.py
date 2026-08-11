import unittest

from alas_headless.adapter import (
    AdapterContractError,
    CapabilityClosureError,
    FlowScope,
    ObservationRegistry,
    ObserveRequest,
    ObserveResult,
    SemanticFrameIdentity,
    UnknownObservationError,
)


SHA = "a" * 64


def scope(*, capabilities=("mission.observe-page",), identifier="scope-1"):
    return FlowScope(
        scope_id=identifier,
        kind="mission",
        operation="reward",
        parent_scope_id=None,
        task_config_sha256=SHA,
        allowed_capabilities=frozenset(capabilities),
        deadline_monotonic_ns=1_000_000,
    )


def frame(identifier="frame-1"):
    return SemanticFrameIdentity(identifier, 1234, 20, 7, SHA, "b" * 64)


def request(resource, *, identifier="scope-1", primitive="appear"):
    return ObserveRequest(identifier, primitive, resource, {}, "frame-1")


def handler(value):
    def resolve(observation):
        return ObserveResult(observation, frame(), value)

    return resolve


class AdapterRegistryTests(unittest.TestCase):
    def test_exact_registration_dispatches_only_in_exact_context(self):
        registry = ObservationRegistry()
        registry.register_exact(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource="MISSION_CHECK",
            capability="mission.observe-page",
            handler=handler(True),
        )
        result = registry.dispatch(scope(), request("MISSION_CHECK"))
        self.assertTrue(result.value)
        with self.assertRaises(UnknownObservationError):
            registry.dispatch(scope(), request("MISSION_EMPTY"))
        with self.assertRaises(UnknownObservationError):
            registry.dispatch(scope(), request("MISSION_CHECK", primitive="ocr"))

    def test_duplicate_exact_or_pattern_registration_is_rejected(self):
        registry = ObservationRegistry()
        arguments = {
            "flow_kind": "mission",
            "operation": "reward",
            "primitive": "appear",
            "resource": "MISSION_CHECK",
            "capability": "mission.observe-page",
            "handler": handler(True),
        }
        registry.register_exact(**arguments)
        with self.assertRaises(AdapterContractError):
            registry.register_exact(**arguments)

        pattern = {
            "flow_kind": "mission",
            "operation": "reward",
            "primitive": "appear",
            "resource_pattern": r"^REWARD_SIDE_NAVBAR_[0-9]+$",
            "capability": "mission.observe-page",
            "handler": handler(True),
        }
        registry.register_pattern(**pattern)
        with self.assertRaises(AdapterContractError):
            registry.register_pattern(**pattern)
        changed_capability = dict(pattern)
        changed_capability["capability"] = "mission.observe-navbar"
        with self.assertRaises(AdapterContractError):
            registry.register_pattern(**changed_capability)

    def test_patterns_support_dynamic_resources_and_reject_ambiguity(self):
        registry = ObservationRegistry()
        registry.register_pattern(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource_pattern=r"^REWARD_SIDE_NAVBAR_[0-9]+$",
            capability="mission.observe-page",
            handler=handler("first"),
        )
        self.assertEqual(
            registry.dispatch(scope(), request("REWARD_SIDE_NAVBAR_3")).value,
            "first",
        )
        registry.register_pattern(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource_pattern=r"^REWARD_SIDE_NAVBAR_[1-5]$",
            capability="mission.observe-page",
            handler=handler("second"),
        )
        with self.assertRaises(AdapterContractError):
            registry.dispatch(scope(), request("REWARD_SIDE_NAVBAR_3"))

    def test_exact_registration_precedes_matching_dynamic_pattern(self):
        registry = ObservationRegistry()
        registry.register_pattern(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource_pattern=r"^MISSION_[A-Z_]+$",
            capability="mission.observe-page",
            handler=handler("pattern"),
        )
        registry.register_exact(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource="MISSION_CHECK",
            capability="mission.observe-page",
            handler=handler("exact"),
        )
        self.assertEqual(
            registry.dispatch(scope(), request("MISSION_CHECK")).value,
            "exact",
        )

    def test_dispatch_requires_scope_identity_capability_and_bound_result(self):
        registry = ObservationRegistry()
        registry.register_exact(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource="MISSION_CHECK",
            capability="mission.observe-page",
            handler=handler(True),
        )
        with self.assertRaises(AdapterContractError):
            registry.dispatch(scope(), request("MISSION_CHECK", identifier="scope-2"))
        with self.assertRaises(CapabilityClosureError):
            registry.dispatch(scope(capabilities=()), request("MISSION_CHECK"))

        broken = ObservationRegistry()
        broken.register_exact(
            flow_kind="mission",
            operation="reward",
            primitive="appear",
            resource="MISSION_CHECK",
            capability="mission.observe-page",
            handler=lambda observation: True,
        )
        with self.assertRaises(AdapterContractError):
            broken.dispatch(scope(), request("MISSION_CHECK"))

    def test_inventory_is_deterministic_and_has_no_catch_all(self):
        def build(reverse):
            registry = ObservationRegistry()
            resources = ("MISSION_CHECK", "MISSION_EMPTY")
            if reverse:
                resources = tuple(reversed(resources))
            for resource in resources:
                registry.register_exact(
                    flow_kind="mission",
                    operation="reward",
                    primitive="appear",
                    resource=resource,
                    capability="mission.observe-page",
                    handler=handler(True),
                )
            return registry

        first = build(False)
        second = build(True)
        self.assertEqual(first.inventory(), second.inventory())
        self.assertEqual(first.required_capabilities(), ("mission.observe-page",))
        with self.assertRaises(ValueError):
            first.register_pattern(
                flow_kind="mission",
                operation="reward",
                primitive="appear",
                resource_pattern=r"^.*$",
                capability="mission.observe-page",
                handler=handler(True),
            )


if __name__ == "__main__":
    unittest.main()
