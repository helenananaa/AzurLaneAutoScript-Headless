import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


def test_live_receipt_preserves_frozen_nested_frame_without_changing_it():
    script = Path(__file__).resolve().parents[1] / 'scripts/python/run_alas_configured_task_live.py'
    spec = importlib.util.spec_from_file_location('live_receipt', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    @dataclass(frozen=True)
    class Frame:
        generation: int
        snapshot: object

    original = Frame(7, MappingProxyType({'buttons': (MappingProxyType({'path': 'exact', 'active': True}),)}))
    recorded = module.encode_receipt_value(original)
    assert json.loads(json.dumps(recorded)) == {'generation': 7, 'snapshot': {'buttons': [{'path': 'exact', 'active': True}]}}
    recorded['snapshot']['buttons'][0]['path'] = 'changed copy'
    assert original.snapshot['buttons'][0]['path'] == 'exact'
