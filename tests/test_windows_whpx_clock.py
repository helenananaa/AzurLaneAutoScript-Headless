"""Exercise the Windows launcher without starting an Android emulator."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/windows/whpx-clock.ps1"
LAUNCHER = ROOT / "scripts/windows/start-alas-avd.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not POWERSHELL, reason="Windows PowerShell launcher tests"
)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


# Supply the native API's return values without calling the real hypervisor.
MOCK_API = r"""
Add-Type -TypeDefinition @'
namespace AlasHeadless {
    public static class WhpxClock {
        public static int HResult = 0;
        public static ulong Frequency = 2419202031;
        public static uint Written = 8;
        public static int Calls = 0;
        public static int WHvGetCapability(uint code, out ulong hz, uint size, out uint written) {
            if (code != 0x1004 || size != 8) throw new System.Exception("wrong capability ABI");
            Calls++;
            hz = Frequency;
            written = Written;
            return HResult;
        }
    }
}
'@
"""


def run_ps(script, *, env=None):
    result = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.lstrip("\ufeff"))


@pytest.fixture
def acceleration_probe(tmp_path):
    probe = tmp_path / "emulator probe.ps1"
    probe.write_text(
        "Write-Output $env:TEST_ACCEL_OUTPUT\n"
        "$global:LASTEXITCODE = [int]$env:TEST_ACCEL_EXIT\n",
        encoding="utf-8",
    )
    return probe


def clock_config(probe, *, frequency=2419202031, written=8, hresult=0,
                 accelerator="WHPX(10.0.26200) is installed and usable.", mode="Auto", exit_code=0):
    env = dict(os.environ, TEST_ACCEL_OUTPUT=accelerator, TEST_ACCEL_EXIT=str(exit_code))
    return run_ps(
        "$ErrorActionPreference = 'Stop'; $WarningPreference = 'SilentlyContinue'\n"
        + MOCK_API
        + f"\n[AlasHeadless.WhpxClock]::Frequency = [uint64]{frequency}\n"
        + f"[AlasHeadless.WhpxClock]::Written = {written}\n"
        + f"[AlasHeadless.WhpxClock]::HResult = {hresult}\n"
        + f". {ps_quote(HELPER)}\n"
        + "try {\n"
        + f"$config = Get-EmulatorClockConfiguration -Emulator {ps_quote(probe)} -Mode {mode}\n"
        + "@{config=$config; calls=[AlasHeadless.WhpxClock]::Calls} | ConvertTo-Json -Depth 5\n"
        + "} catch { @{error=$_.Exception.Message; calls=[AlasHeadless.WhpxClock]::Calls} | ConvertTo-Json }",
        env=env,
    )


@pytest.mark.parametrize("frequency,khz", [(2419202031, 2419202), (2899999500, 2900000)])
def test_whpx_uses_current_frequency_and_one_kernel_argument(acceleration_probe, frequency, khz):
    result = clock_config(acceleration_probe, frequency=frequency)
    assert result["calls"] == 1
    assert result["config"]["frequency_hz"] == frequency
    assert result["config"]["tsc_early_khz"] == khz
    assert result["config"]["arguments"] == [
        "-qemu", "-append", f"tsc_early_khz={khz} clocksource=tsc"
    ]


@pytest.mark.parametrize("values", [
    {"frequency": 0}, {"frequency": 1}, {"frequency": 4294967296000},
    {"written": 4}, {"hresult": -2147467259},
])
def test_invalid_frequency_never_produces_a_historical_fallback(acceleration_probe, values):
    result = clock_config(acceleration_probe, **values)
    assert "config" not in result
    assert "WHPX clock query failed" in result["error"]
    assert "-ClockMode Off" in result["error"]


@pytest.mark.parametrize("values,status", [
    ({"accelerator": "AEHD is installed and usable."}, "not-whpx"),
    ({"accelerator": "KVM is installed and usable."}, "not-whpx"),
    ({"exit_code": 1}, "acceleration-check-failed"),
    ({"mode": "Off"}, "disabled"),
])
def test_other_backends_and_explicit_opt_out_do_not_query_whpx(acceleration_probe, values, status):
    result = clock_config(acceleration_probe, hresult=-1, **values)
    assert result["calls"] == 0
    assert result["config"]["status"] == status
    assert result["config"]["arguments"] == []


def test_native_argument_quoting_round_trips_through_start_process(tmp_path):
    output = tmp_path / "received.json"
    arguments = ["", "tsc_early_khz=2419202 clocksource=tsc", "a b", 'a\\"b', "C:\\space dir\\", "普通路径"]
    code = "import json,sys;open(sys.argv[1],'w',encoding='utf-8').write(json.dumps(sys.argv[2:]))"
    tokens = [sys.executable, "-c", code, str(output), *arguments]
    # FilePath is separate; run the remaining tokens through the production quoting function.
    result = run_ps(
        f"$ErrorActionPreference='Stop'; . {ps_quote(HELPER)}\n"
        + "$tokens = @( " + ", ".join(ps_quote(x) for x in tokens[1:]) + " )\n"
        + "$line = ConvertTo-WindowsNativeArguments -Arguments $tokens\n"
        + f"$child = Start-Process -FilePath {ps_quote(tokens[0])} -ArgumentList $line -WindowStyle Hidden -PassThru -Wait\n"
        + "@{exit=$child.ExitCode} | ConvertTo-Json",
    )
    assert result["exit"] == 0
    assert json.loads(output.read_text(encoding="utf-8")) == arguments


@pytest.fixture(scope="module")
def fake_native_tool(tmp_path_factory):
    """A tiny native-command stand-in records argv; it cannot start a VM."""
    directory = tmp_path_factory.mktemp("fake-android-tools")
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        pytest.skip(".NET Framework C# compiler is needed for the fake CLI")
    source = directory / "Tool.cs"
    source.write_text(r'''
using System;
using System.IO;
using System.Web.Script.Serialization;
class Tool {
    static int Main(string[] args) {
        string name = Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]);
        if (name == "adb") {
            if (Environment.GetEnvironmentVariable("TEST_AVD_RUNNING") != "1") return 1;
            if (Array.IndexOf(args, "get-state") >= 0) Console.WriteLine("device");
            else if (Array.IndexOf(args, "cat") >= 0) Console.WriteLine("tsc");
            else Console.WriteLine("test avd\nOK");
            return 0;
        }
        if (Array.IndexOf(args, "-accel-check") >= 0) {
            Console.WriteLine("accel:\n0\nWHPX is installed and usable.\naccel");
            return 0;
        }
        File.WriteAllText(Environment.GetEnvironmentVariable("TEST_LAUNCH_RECEIPT"),
            new JavaScriptSerializer().Serialize(args));
        return 0;
    }
}
''', encoding="utf-8")
    executable = directory / "tool.exe"
    subprocess.run(
        [str(compiler), "/nologo", "/reference:System.Web.Extensions.dll",
         f"/out:{executable}", str(source)],
        check=True, capture_output=True, timeout=30,
    )
    return executable


@pytest.fixture
def fake_avd(tmp_path, fake_native_tool):
    sdk = tmp_path / "sdk with spaces"
    for child in ["emulator", "platform-tools", "cmdline-tools/latest/bin",
                  "system-images/android-32/default/x86_64"]:
        (sdk / child).mkdir(parents=True)
    shutil.copyfile(fake_native_tool, sdk / "emulator/emulator.exe")
    shutil.copyfile(fake_native_tool, sdk / "platform-tools/adb.exe")
    (sdk / "cmdline-tools/latest/bin/avdmanager.bat").write_text("exit /b 99")
    (sdk / "system-images/android-32/default/x86_64/system.img").write_bytes(b"fake image")
    avd_home = tmp_path / "avd home"
    avd = avd_home / "test avd.avd"
    avd.mkdir(parents=True)
    (avd / "config.ini").write_text("image.sysdir.1=system-images\\android-32\\default\\x86_64\\\n")
    return sdk, avd_home, tmp_path / "logs", tmp_path / "launched.json"


def invoke_launcher(fake_avd, *, plan=False, running=False, failure=False):
    sdk, avd_home, logs, receipt = fake_avd
    env = dict(os.environ, TEST_LAUNCH_RECEIPT=str(receipt), TEST_AVD_RUNNING="1" if running else "0")
    return run_ps(
        "$ErrorActionPreference='Stop'; $PSNativeCommandUseErrorActionPreference=$false\n"
        + MOCK_API
        + ("[AlasHeadless.WhpxClock]::HResult = -1\n" if failure else "")
        + "function Get-NetTCPConnection { param($State, $ErrorAction) @() }\n"
        + "try {\n"
        + f"& {ps_quote(LAUNCHER)} -AndroidSdkRoot {ps_quote(sdk)} "
        + f"-AvdHome {ps_quote(avd_home)} -AvdName 'test avd' -ConsolePort 5660 "
        + f"-AdbServerPort 5059 -DnsServer '192.0.2.53' -LogDirectory {ps_quote(logs)} "
        + ("-PlanOnly\n" if plan else "\n")
        + "} catch { @{error=$_.Exception.Message} | ConvertTo-Json }",
        env=env,
    )


def test_launch_plan_has_no_vm_or_log_directory_side_effects(fake_avd):
    result = invoke_launcher(fake_avd, plan=True)
    assert result["outcome"] == "planned"
    assert result["arguments"][-3:] == ["-qemu", "-append", "tsc_early_khz=2419202 clocksource=tsc"]
    assert result["clocksource_verified"] is False
    assert not fake_avd[2].exists()
    assert not fake_avd[3].exists()


def test_launcher_preserves_options_and_passes_kernel_settings_as_one_argument(fake_avd):
    result = invoke_launcher(fake_avd)
    assert result["outcome"] == "started"
    assert result["clocksource_verified"] is False
    receipt = fake_avd[3]
    deadline = time.monotonic() + 3
    while not receipt.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    actual = json.loads(receipt.read_text())
    assert actual == [str(x) for x in result["arguments"]]
    assert actual[:2] == ["-avd", "test avd"]
    assert actual[-3:] == ["-qemu", "-append", "tsc_early_khz=2419202 clocksource=tsc"]
    assert actual[actual.index("-dns-server") + 1] == "192.0.2.53"
    assert "-wipe-data" not in actual and "-no-snapshot" in actual
    assert Path(result["stdout_log"]).is_file()


def test_failed_frequency_query_does_not_start_the_emulator(fake_avd):
    result = invoke_launcher(fake_avd, failure=True)
    assert "WHPX clock query failed" in result["error"]
    assert not fake_avd[3].exists()


def test_already_running_avd_is_observed_without_restarting_or_querying_frequency(fake_avd):
    result = invoke_launcher(fake_avd, running=True, failure=True)
    assert result["outcome"] == "already-running"
    assert result["clocksource"] == "tsc"
    assert result["clock_configuration_applied"] is False
    assert not fake_avd[3].exists()
