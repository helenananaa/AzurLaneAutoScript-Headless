import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "python" / "collect_alas_auto_combat_workload.py"
SPEC = importlib.util.spec_from_file_location("collect_auto_combat", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AutoCombatWorkloadCollectorTests(unittest.TestCase):
    def test_guest_proc_sample_is_converted_to_monotonic_counters(self):
        output = "\n".join(
            (
                "PID:2703",
                "2703 (com.bilibili.azurlane) S 1 2 3 4 5 6 7 8 9 10 100 25 "
                "0 0 0 0 144 0 716569 38155137024 205069",
                "VmHWM: 940416 kB",
                "VmRSS: 820276 kB",
                "Threads: 144",
            )
        )
        pid, sample, details = MODULE.parse_guest_process_sample(
            output, clock_ticks=100, page_size=4096
        )
        self.assertEqual(pid, 2703)
        self.assertEqual(sample.scope, "game")
        self.assertEqual(sample.cpu_time_ns, 1_250_000_000)
        self.assertEqual(sample.rss_bytes, 820276 * 1024)
        self.assertEqual(details["Threads"], 144)

    def test_meminfo_parser_keeps_only_aggregate_process_totals(self):
        actual = MODULE.parse_meminfo_totals(
            "TOTAL PSS: 1763595 TOTAL RSS: 841068 TOTAL SWAP PSS: 951771"
        )
        self.assertEqual(actual["pss_bytes"], 1763595 * 1024)
        self.assertEqual(actual["rss_bytes"], 841068 * 1024)
        self.assertEqual(actual["swap_pss_bytes"], 951771 * 1024)

    def test_emulator_serial_port_is_explicit(self):
        self.assertEqual(MODULE._emulator_port("emulator-5580"), 5580)
        self.assertIsNone(MODULE._emulator_port("127.0.0.1:5555"))

    def test_trace_hooks_cover_specialized_campaign_action_and_restore_it(self):
        class Trace:
            def __init__(self):
                self.records = []

            def emit(self, event, **values):
                self.records.append((event, values))

        original = MODULE.SemanticOracle.click_campaign_stage

        def fake_click(_oracle, stage_code):
            return SimpleNamespace(
                semantic_id="campaign/stage/" + stage_code,
                generation=123,
            )

        MODULE.SemanticOracle.click_campaign_stage = fake_click
        trace = Trace()
        restore = None
        try:
            restore = MODULE._install_trace_hooks(trace)
            receipt = MODULE.SemanticOracle.click_campaign_stage(object(), "12-4")
            self.assertEqual(receipt.semantic_id, "campaign/stage/12-4")
            event, values = trace.records[-1]
            self.assertEqual(event, "alas.action")
            self.assertEqual(
                values["fields"]["method"],
                "SemanticOracle.click_campaign_stage",
            )
            self.assertEqual(values["fields"]["receipt_generation"], 123)
        finally:
            if restore is not None:
                restore()
            self.assertIs(MODULE.SemanticOracle.click_campaign_stage, fake_click)
            MODULE.SemanticOracle.click_campaign_stage = original

    def test_trace_hooks_mark_official_auto_phase_boundaries(self):
        class Trace:
            def __init__(self):
                self.records = []

            def emit(self, event, **values):
                self.records.append((event, values))

        original_start = MODULE.AlasSemanticSession.confirm_campaign_auto_search_started
        original_complete = (
            MODULE.AlasSemanticSession.wait_campaign_auto_search_completion
        )
        MODULE.AlasSemanticSession.confirm_campaign_auto_search_started = (
            lambda _session: SimpleNamespace(
                stage_code="12-4",
                sortie_generation=10,
                map_generation=20,
                map_root_path="CombatUIStandard(Clone)",
            )
        )
        MODULE.AlasSemanticSession.wait_campaign_auto_search_completion = (
            lambda _session, stage_code: SimpleNamespace(
                stage_code=stage_code,
                result_generation=30,
                result_path="LevelStageTotalRewardPanel(Clone)",
                waited_seconds=400.0,
            )
        )
        trace = Trace()
        restore = None
        try:
            restore = MODULE._install_trace_hooks(trace)
            MODULE.AlasSemanticSession.confirm_campaign_auto_search_started(object())
            MODULE.AlasSemanticSession.wait_campaign_auto_search_completion(
                object(), "12-4"
            )
            phases = [
                values["fields"]["phase"]
                for event, values in trace.records
                if event == "alas.phase"
            ]
            self.assertEqual(
                phases,
                ["official-auto-start", "official-auto-complete"],
            )
        finally:
            if restore is not None:
                restore()
            MODULE.AlasSemanticSession.confirm_campaign_auto_search_started = (
                original_start
            )
            MODULE.AlasSemanticSession.wait_campaign_auto_search_completion = (
                original_complete
            )


if __name__ == "__main__":
    unittest.main()
