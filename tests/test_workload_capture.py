import json
import tempfile
import unittest
from pathlib import Path

from alas_headless.workload_capture import (
    LIVE_WORKLOAD_BASELINE_SCHEMA,
    LIVE_WORKLOAD_CAPTURE_SCHEMA,
    LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA,
    build_resource_receipt,
    emulator_port,
    parse_guest_process_sample,
    parse_meminfo_totals,
    sha256_file,
    summarize_workload_records,
    verify_workload_capture,
    write_json,
)


class WorkloadCaptureTests(unittest.TestCase):
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
        pid, sample, details = parse_guest_process_sample(
            output, clock_ticks=100, page_size=4096
        )
        self.assertEqual(pid, 2703)
        self.assertEqual(sample.scope, "game")
        self.assertEqual(sample.cpu_time_ns, 1_250_000_000)
        self.assertEqual(sample.rss_bytes, 820276 * 1024)
        self.assertEqual(details["Threads"], 144)

    def test_meminfo_parser_keeps_only_aggregate_process_totals(self):
        actual = parse_meminfo_totals(
            "TOTAL PSS: 1763595 TOTAL RSS: 841068 TOTAL SWAP PSS: 951771"
        )
        self.assertEqual(actual["pss_bytes"], 1763595 * 1024)
        self.assertEqual(actual["rss_bytes"], 841068 * 1024)
        self.assertEqual(actual["swap_pss_bytes"], 951771 * 1024)

    def test_emulator_serial_port_is_explicit(self):
        self.assertEqual(emulator_port("emulator-5580"), 5580)
        self.assertIsNone(emulator_port("127.0.0.1:5555"))

    def test_runtime_summary_uses_counter_deltas_and_observer_distribution(self):
        records = (
            {
                "event": "runtime.process.sample",
                "monotonic_ns": 1_000_000_000,
                "fields": {
                    "scope": "host-runtime",
                    "cpu_time_ns": 10_000_000_000,
                    "rss_bytes": 1000,
                    "read_bytes": 10,
                    "write_bytes": 20,
                },
            },
            {
                "event": "runtime.process.sample",
                "monotonic_ns": 2_000_000_000,
                "fields": {
                    "scope": "host-runtime",
                    "cpu_time_ns": 11_000_000_000,
                    "rss_bytes": 2000,
                    "read_bytes": 40,
                    "write_bytes": 50,
                },
            },
            {
                "event": "runtime.process.sample",
                "monotonic_ns": 1_000_000_000,
                "fields": {
                    "scope": "game",
                    "cpu_time_ns": 5_000_000_000,
                    "rss_bytes": 3000,
                },
            },
            {
                "event": "runtime.process.sample",
                "monotonic_ns": 2_000_000_000,
                "fields": {
                    "scope": "game",
                    "cpu_time_ns": 5_500_000_000,
                    "rss_bytes": 4000,
                },
            },
            {
                "event": "runtime.game.process.identity",
                "monotonic_ns": 2_000_000_000,
                "fields": {"pid": 1, "threads": 100},
            },
            {
                "event": "observer.request",
                "monotonic_ns": 1_100_000_000,
                "duration_ns": 10_000_000,
                "outcome": "ok",
                "fields": {"endpoint": "/v1/state", "response_bytes": 100},
            },
            {
                "event": "observer.request",
                "monotonic_ns": 1_200_000_000,
                "duration_ns": 30_000_000,
                "outcome": "ok",
                "fields": {"endpoint": "/v1/ui", "response_bytes": 300},
            },
        )
        actual = summarize_workload_records(records, duration_ns=2_000_000_000)
        self.assertEqual(actual["host_runtime"]["average_cpu_cores"], 1.0)
        self.assertEqual(actual["host_runtime"]["read_bytes_delta"], 30)
        self.assertEqual(actual["game"]["average_cpu_cores"], 0.5)
        self.assertEqual(actual["game"]["threads_p50"], 100)
        self.assertEqual(actual["observer"]["requests"], 2)
        self.assertEqual(actual["observer"]["requests_per_second"], 1.0)
        self.assertEqual(actual["observer"]["duration_ms_p95"], 30)
        self.assertEqual(actual["observer"]["response_bytes_max"], 300)

    def test_resource_receipt_does_not_manufacture_unobserved_counters(self):
        result = {
            "passed": True,
            "run_id": "run-1",
            "workload": {"id": "idle-soak"},
            "device": {"serial": "emulator-5580"},
            "safety": {"in_game_resource_mutation_expected": False},
        }
        receipt = build_resource_receipt(
            result,
            evidence_basis="passive typed observation",
            observed_mutation_dispatches=None,
        )
        self.assertEqual(receipt["schema"], LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA)
        self.assertEqual(receipt["expected_in_game_resource_delta"], 0)
        self.assertFalse(receipt["resource_counters_directly_observed"])
        self.assertIsNone(receipt["observed_mutation_dispatches"])
        self.assertTrue(receipt["zero_resource_contract_passed"])

    def test_capture_verifier_accepts_correlated_files_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            trace_path = output / "runtime-trace.jsonl"
            trace_path.write_text(
                json.dumps(
                    {
                        "event": "workload.phase",
                        "monotonic_ns": 1,
                        "fields": {"phase": "start"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = {
                "schema": LIVE_WORKLOAD_CAPTURE_SCHEMA,
                "run_id": "run-verifier",
                "passed": True,
                "workload": {"id": "idle-soak"},
                "trace": {"after_close": {"recorded": 1}},
            }
            receipt = {
                "schema": LIVE_WORKLOAD_RESOURCE_RECEIPT_SCHEMA,
                "run_id": "run-verifier",
                "expected_in_game_resource_delta": 0,
                "zero_resource_contract_passed": True,
            }
            result_path = output / "result.json"
            receipt_path = output / "resource-receipt.json"
            write_json(result_path, result)
            write_json(receipt_path, receipt)
            write_json(
                output / "baseline-summary.json",
                {
                    "schema": LIVE_WORKLOAD_BASELINE_SCHEMA,
                    "run_id": "run-verifier",
                    "capture_passed": True,
                    "source": {
                        "result_sha256": sha256_file(result_path),
                        "runtime_trace_sha256": sha256_file(trace_path),
                        "resource_receipt_sha256": sha256_file(receipt_path),
                    },
                    "integrity": {
                        "trace_records": 1,
                        "trace_dropped": 0,
                        "trace_invalid": 0,
                        "trace_writer_error": None,
                        "screenshots_captured": False,
                        "observer_sidecar_used": False,
                        "raw_input_fallback_used": False,
                    },
                },
            )

            self.assertTrue(verify_workload_capture(output)["passed"])
            with trace_path.open("a", encoding="utf-8") as handle:
                handle.write('{"event":"tampered"}\n')
            verification = verify_workload_capture(output)
            self.assertFalse(verification["passed"])
            self.assertIn("runtime_trace_sha256 mismatch", verification["errors"])


if __name__ == "__main__":
    unittest.main()
