"""Read-only typed map-ammo/combat observations; never sends input."""
import argparse
import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from alas_headless import AdbObserverBridge, SemanticOracle, OracleFingerprint


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=90)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    records = []
    with AdbObserverBridge(args.serial, 'com.bilibili.azurlane') as bridge:
        snapshot = bridge.request('GET /v1/state\n')['snapshot']
        oracle = SemanticOracle(bridge.request, bridge.foreground_component, bridge.tap,
            OracleFingerprint(package=bridge.package,
                component=bridge.package+'/com.manjuu.azurlane.MainActivity',
                driver_revision=snapshot['driver_revision'], expected_pid=bridge.pid))
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            try:
                state = oracle.read_state(); ui = oracle.read_ui_state()
                if not state.generation <= ui.generation <= state.generation + 2 or ui.image_truncated:
                    continue
                markers = [i for i in ui.images if i.sprite == 'qianting_icon'
                           and i.active_in_hierarchy and i.active_and_enabled]
                roots = [i.path.rsplit('/', 1)[0] for i in markers]
                ammo = [t for t in ui.texts if any(t.path.startswith(root+'/ammo/') for root in roots)]
                controls = [b for b in state.buttons if '/CombatUIStandard(Clone)/' in b.path
                            and (b.name == 'PauseBtn' or '/Weapon_button_container/' in b.path)]
                records.append(dict(generation=state.generation, ui_generation=ui.generation,
                    runtime_messages=[dataclasses.asdict(t) for t in ui.texts
                        if t.path.endswith('/Msgbox(Clone)/window/msg_panel/content')],
                    submarine_markers=[dataclasses.asdict(i) for i in markers],
                    ammo=[dataclasses.asdict(t) for t in ammo],
                    controls=[dataclasses.asdict(b) for b in controls]))
            except Exception as exc:
                records.append(dict(error=type(exc).__name__+': '+str(exc)))
            time.sleep(0.8)
        document = dict(schema='alas-headless.submarine-ammo-observation/v1',
            serial=args.serial, observed_at=datetime.now(timezone.utc).isoformat(),
            fingerprint=dataclasses.asdict(oracle.fingerprint), input_count=0, records=records)
        args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(records=len(records), ammo=[r['ammo'] for r in records if r.get('ammo')]), ensure_ascii=True))


if __name__ == '__main__':
    main()
