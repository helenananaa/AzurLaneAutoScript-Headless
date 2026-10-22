"""Bounded qualification of original HPBalancer decisions, with order restoration."""

import dataclasses
import time


def exercise_scouts(host, adapter, record):
    original = {name: getattr(host.config, name) for name in (
        'HpControl_HpBalanceWeight', 'HpControl_HpBalanceThreshold', 'HpControl_UseHpBalance')}
    oracle = adapter._fresh_input_oracle()
    initial = oracle.campaign_scout_order()
    record.update(before=initial, passed=False,
                  buttons_before=dataclasses.asdict(oracle.read_state()),
                  ui_before=dataclasses.asdict(oracle.read_ui_state()))
    count = len(initial['ships'])
    if count not in (2, 3):
        raise RuntimeError('two or three occupied scout slots are required for this qualification')
    try:
        # Real HP is read unchanged. A valid temporary weight configuration
        # makes the original policy move the last scout to the first slot.
        host.config.override(HpControl_UseHpBalance=True,
            HpControl_HpBalanceWeight=('100,1000,100' if count == 2 else '100,500,1000'),
            HpControl_HpBalanceThreshold=0.2)
        host.hp_get()
        target = tuple(int(i) for i in host._expected_scout_order(host.hp[3:]))
        record['original_policy_hp'] = list(host.hp)
        record['original_policy_order'] = target
        host.hp_balance()
        after = adapter._fresh_input_oracle().campaign_scout_order()
        record['after_policy'] = after
        if after['ships'] != tuple(initial['ships'][i] for i in target[:count]):
            raise RuntimeError('original HPBalancer did not produce its expected order')
        record['passed'] = True
    finally:
        host.config.override(**original)
        current = adapter._fresh_input_oracle().campaign_scout_order()
        if set(current['ships']) != set(initial['ships']):
            record['passed'] = False
            raise RuntimeError('scout membership changed; restoration is not safe')
        restore = [current['ships'].index(ship) for ship in initial['ships']]
        restore.extend(range(count, 3))
        for step in host._gen_exchange_step(restore):
            host._scout_position_change(*step)
        restored = adapter._fresh_input_oracle().campaign_scout_order()
        record['restored'] = restored
        record['swaps'] = list(adapter._campaign_context.scout_swap_history)
        if restored['ships'] != initial['ships']:
            record['passed'] = False
            raise RuntimeError('original scout order was not restored')
        # hp_get caches weighted HP in ALAS. Restoring only the configuration
        # leaves the probe's artificial low HP available to emergency repair.
        try:
            host.hp_get()
            record['restored_policy_hp'] = list(host.hp)
        except Exception:
            record['passed'] = False
            raise


def withdraw_from_precombat(host, adapter):
    receipt = adapter._fresh_input_oracle().click_campaign_precombat_back()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        host.device.screenshot()
        oracle = adapter._frame_or_live_observation_oracle()
        if oracle.read_state().generation > receipt.generation and oracle.campaign_is_in_map():
            host.withdraw(skip_first_screenshot=False)
            raise AssertionError('original withdrawal did not terminate Campaign')
        time.sleep(0.2)
    raise RuntimeError('precombat cancellation did not restore the map')
