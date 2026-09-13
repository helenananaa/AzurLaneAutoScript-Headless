import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "bluetooth_trim", Path(__file__).parents[1] / "scripts/python/qualify_redroid_bluetooth_trim.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_hardware_absent_with_userdata_on_and_unrelated_services_allowed():
    module.verify_candidate({
        "features": "feature:android.hardware.ethernet\nfeature:android.software.webview\n",
        "services": "Found 2 services:\n0 package: [android.content.pm.IPackageManager]\n1 wifi: []",
        "processes": "PID NAME\n1 init\n300 com.android.systemui\n",
        "hal_init_state": "\n", "persisted_switch": "1\n",
    })


@pytest.mark.parametrize("field,value", [
    ("features", "feature:android.hardware.bluetooth\n"),
    ("features", "feature:android.hardware.bluetooth_le\n"),
    ("services", "0 bluetooth_manager: [android.bluetooth.IBluetoothManager]"),
    ("processes", "100 com.android.bluetooth"),
    ("processes", "128 android.hardware.bluetooth@1.1-service.sim"),
    ("hal_init_state", "stopped"),
    ("persisted_switch", "0"),
])
def test_remaining_hardware_or_off_only_trial_cannot_pass(field, value):
    observation = {"features": "feature:android.hardware.ethernet", "services": "Found 0 services:",
                   "processes": "PID NAME\n1 init", "hal_init_state": "", "persisted_switch": "1"}
    observation[field] = value
    with pytest.raises(ValueError):
        module.verify_candidate(observation)
