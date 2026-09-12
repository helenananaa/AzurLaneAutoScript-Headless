"""Campaign HP resource ports; original ALAS owns all decisions and loops."""

import time

from ...semantic_oracle import SemanticGateClosed


class CampaignHealthAdapterPorts:
    def change_campaign_scout_position(self, source_slot, destination_slot):
        context = self._require_campaign_context()
        if context.combat_admission is None:
            raise SemanticGateClosed('campaign scout drag has no original combat admission')
        if context.scout_drag_pending is not None:
            raise SemanticGateClosed('campaign scout drag outcome is still unresolved')
        oracle = self._fresh_input_oracle()
        # A failed transport can have dispatched the drag. Keep this pending
        # until a new task/recovery rather than retrying an uncertain exchange.
        context.scout_drag_pending = {'source_slot': source_slot, 'destination_slot': destination_slot}
        before_inputs = getattr(self.oracle, 'input_dispatch_count', 0)
        try:
            receipt = oracle.drag_campaign_scout(source_slot, destination_slot)
        except Exception:
            if getattr(self.oracle, 'input_dispatch_count', 0) == before_inputs:
                context.scout_drag_pending = None
            raise
        context.scout_drag_pending = receipt
        expected = list(receipt['before'])
        expected.insert(destination_slot, expected.pop(source_slot))
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            current = self._fresh_input_oracle().campaign_scout_order()
            if current['generation'] > receipt['generation'] and current['ships'] == tuple(expected):
                result = dict(receipt, after=current['ships'], post_generation=current['generation'])
                context.scout_swap_history.append(result)
                context.scout_drag_pending = None
                return result
            if set(current['ships']) != set(receipt['before']):
                raise SemanticGateClosed('campaign scout membership changed during exchange')
            time.sleep(0.2)
        raise SemanticGateClosed('campaign scout exchange did not reach the original ALAS insertion')

    def campaign_repair_appear(self, name):
        context = self._require_campaign_context()
        if name == 'EMERGENCY_REPAIR_CONFIRM':
            if context.repair_open_receipt is None or context.repair_use_receipt is not None:
                return False
            panel = self.oracle.campaign_emergency_repair_panel()
            return panel is not None and panel['count'] > 0
        if context.repair_open_receipt is not None:
            return False
        state = self.oracle.campaign_emergency_repair_state()
        if state is None or state['count'] == 0:
            return False
        if state['button'].raycast_top is not True:
            # Precombat's entry animation can expose stock before the icon
            # becomes the top hit. Refresh without input, then still reject
            # persistent occlusion or unknown hit evidence.
            for _ in range(3):
                time.sleep(0.2)
                state = self._fresh_input_oracle().campaign_emergency_repair_state()
                if state is None or state['count'] == 0:
                    return False
                if state['button'].raycast_top is True:
                    break
            else:
                raise SemanticGateClosed('campaign repair button top target is not proven')
        return state['button'].interactable

    def click_campaign_repair(self, name):
        context = self._require_campaign_context()
        oracle = self._fresh_input_oracle()
        if name == 'EMERGENCY_REPAIR_AVAILABLE':
            if context.repair_open_receipt is not None:
                raise SemanticGateClosed('campaign repair details already opened')
            state = oracle.campaign_emergency_repair_state()
            if state is None or state['count'] < 1:
                raise SemanticGateClosed('campaign repair inventory is unavailable')
            admission = context.combat_admission
            if admission is None:
                raise SemanticGateClosed('campaign repair has no original combat admission')
            context.repair_count_before = state['count']
            context.repair_hp_before = oracle.campaign_hp_control_snapshot(
                admission.fleet_index, precombat=True,
                **self._campaign_vitals_kwargs(admission.fleet_index))[0]
            receipt = oracle.click_campaign_emergency_repair('open')
            context.repair_open_receipt = receipt
        else:
            if context.repair_open_receipt is None or context.repair_use_receipt is not None:
                raise SemanticGateClosed('campaign repair use is unowned or already submitted')
            panel = oracle.campaign_emergency_repair_panel()
            if (panel is None or panel['count'] != context.repair_count_before
                    or panel['generation'] <= context.repair_open_receipt.generation):
                raise SemanticGateClosed('campaign repair inventory changed before use')
            receipt = oracle.click_campaign_emergency_repair('use')
            context.repair_use_receipt = receipt
            context.repair_post_deadline = time.monotonic() + 15.0
        return receipt

    def wait_campaign_repair_ready(self):
        """Replace only ALAS's pixel fleet-power stabilization port."""
        self._require_campaign_context()
        deadline = time.monotonic() + 8.0
        previous = None
        while time.monotonic() < deadline:
            oracle = self._fresh_input_oracle()
            state = oracle.campaign_emergency_repair_state()
            if state is None:
                raise SemanticGateClosed('campaign repair preparation disappeared')
            identity = state['count'], state['powers']
            if state['count'] == 0:
                return
            if (all(state['powers']) and previous is not None
                    and identity == previous[0] and state['generation'] > previous[1]):
                return
            previous = identity, state['generation']
            time.sleep(0.2)
        raise SemanticGateClosed('campaign repair preparation did not stabilize')

    def campaign_repair_postcondition(self):
        context = self._campaign_context
        if context is None or context.repair_use_receipt is None:
            return None
        oracle = self._frame_or_live_observation_oracle()
        if oracle.campaign_emergency_repair_panel() is None:
            state = oracle.campaign_emergency_repair_state()
            if state is None:
                raise SemanticGateClosed('campaign repair lost its precombat page')
            if state['generation'] > context.repair_use_receipt.generation:
                if state['count'] == context.repair_count_before - 1:
                    hp, _ = oracle.campaign_hp_control_snapshot(context.combat_admission.fleet_index, precombat=True,
                        **self._campaign_vitals_kwargs(context.combat_admission.fleet_index))
                    before = context.repair_hp_before
                    if (any(after < prior - 0.0001 for after, prior in zip(hp, before))
                            or not any(after > prior + 0.0001 for after, prior in zip(hp, before))):
                        # Inventory can update before the HP animation. Keep
                        # the original preparation loop waiting without input.
                        if time.monotonic() < context.repair_post_deadline:
                            return 'pending'
                        raise SemanticGateClosed('campaign repair HP improvement is not proven')
                    context.repair_history.append(dict(open=context.repair_open_receipt,
                        use=context.repair_use_receipt, count_before=context.repair_count_before,
                        count_after=state['count'], hp_before=before, hp_after=hp,
                        post_generation=state['generation']))
                    context.repair_open_receipt = context.repair_use_receipt = None
                    return 'complete'
                if state['count'] != context.repair_count_before:
                    raise SemanticGateClosed('campaign repair inventory postcondition changed')
        if time.monotonic() >= context.repair_post_deadline:
            raise SemanticGateClosed('campaign repair result did not advance')
        return 'pending'
