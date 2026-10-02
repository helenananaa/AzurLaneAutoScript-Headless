from unittest.mock import Mock
import pytest
from alas_headless.oracle.transport import AdbObserverBridge


def test_adb_tap_holds_one_reviewed_point_without_movement():
    bridge = AdbObserverBridge.__new__(AdbObserverBridge)
    bridge._run = Mock()
    bridge.tap(1142, 641)
    bridge._run.assert_called_once_with(('shell','input','swipe','1142','641','1142','641','100'))

def test_exact_native_projection_is_not_rounded_during_adb_dispatch():
    bridge = AdbObserverBridge.__new__(AdbObserverBridge)
    bridge._run = Mock()
    bridge.tap(821.541199, 274.222137)
    bridge._run.assert_called_once_with(('shell', 'input', 'swipe',
        '821.541199', '274.222137', '821.541199', '274.222137', '100'))

@pytest.mark.parametrize('point', [(float('nan'),1), (1,float('inf')), (True,1), ('821.5',1)])
def test_malformed_typed_point_never_reaches_adb(point):
    bridge = AdbObserverBridge.__new__(AdbObserverBridge); bridge._run = Mock()
    with pytest.raises(ValueError): bridge.tap(*point)
    bridge._run.assert_not_called()
