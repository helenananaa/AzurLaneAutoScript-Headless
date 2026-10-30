"""Callbacks and input ownership for the unchanged native confirm loop."""

from dataclasses import dataclass, replace
import re
from .errors import SemanticGateClosed
from .old_retirement_contracts import OldRetirementExecutionReceipt
from .retirement_cv import RetirementCvDeselectionReceipt


@dataclass(frozen=True)
class OldRetirementDialogTarget:
    semantic_id: str
    path_suffix: str
    identity_text_suffix: str
    identity_text: str


def _old_retirement_warning_target(oracle, ui, *, selected_count,
                                   allowed_rarities, expected_levels):
    header = oracle._active_retirement_texts(
        ui, "DestoryConfirmWindow(Clone)/window/content/Text")
    if len(header) != 1:
        raise SemanticGateClosed("old retirement warning identity changed")
    # Rich-text colour is presentation, not a different game warning.
    label = re.sub(r"</?color(?:=[^>]+)?>", "", header[0].text).strip()
    if label == "选择角色中有精锐以上的角色：":
        if not set(allowed_rarities).intersection(("SR", "SSR")):
            raise SemanticGateClosed(
                "rarity warning conflicts with native old-retire selection")
        semantic_id = "retirement/rarity-warning/confirm"
    elif label == "选择角色中有等级不为1的角色：":
        if (expected_levels is None or len(expected_levels) != selected_count
                or not all(type(level) is int and level > 0
                           for level in expected_levels)):
            raise SemanticGateClosed("level warning has no owned submitted selection")
        expected = tuple(sorted(level for level in expected_levels if level > 1))
        displayed = oracle._active_retirement_texts(
            ui, "DestoryConfirmWindow(Clone)/window/content/ships_single/"
                "IconTpl/icon_bg/lv/Text")
        if (not expected or any(re.fullmatch(r"[1-9][0-9]*", t.text.strip()) is None
                                for t in displayed)
                or tuple(sorted(int(t.text.strip()) for t in displayed)) != expected):
            raise SemanticGateClosed("level warning differs from owned selected levels")
        semantic_id = "retirement/level-warning/confirm"
    else:
        raise SemanticGateClosed("old retirement warning identity changed")
    return OldRetirementDialogTarget(
        semantic_id,
        "DestoryConfirmWindow(Clone)/window/confirm_btn",
        "DestoryConfirmWindow(Clone)/window/content/desc/label",
        "是否确认",
    )


def probe_old_retirement_alias(oracle, name, *, selected_count, allowed_rarities,
                               expected_levels=None, _records=None):
    """Replace native template predicates with typed modal/owner identity."""
    state, ui = oracle._retirement_records() if _records is None else _records

    def buttons(suffix):
        return oracle._active_retirement_buttons(state, suffix)

    def actionable(suffix):
        matches = buttons(suffix)
        if len(matches) > 1:
            raise SemanticGateClosed("old retirement dialog target is ambiguous")
        return len(matches) == 1 and matches[0].actionable

    panel = "ResolveEquipmentUI(Clone)/"
    destroy = bool(buttons(panel + "destroy_confirm/actions/destroy_button"))
    kind = oracle._retirement_screen_kind()
    if name == "IN_RETIREMENT_CHECK":
        # The retained Dock can still exist below every confirmation. It is
        # not the native return destination until those modal owners leave.
        return (
            kind == "selection"
            and not destroy
            and not oracle._blocking_rules(state, "retirement/page/back")
        )
    if name == "SHIP_CONFIRM":
        if kind != "selection" or destroy:
            return False
        selection = oracle.retirement_selection_state()
        if not selection.selected_count:
            return False
        if selection.selected_count != selected_count:
            raise SemanticGateClosed(
                "old retirement selected count changed before confirm"
            )
        return actionable("/blur_panel/select_panel/confirm_button")
    if name == "SHIP_CONFIRM_2":
        if kind != "preconfirm" or destroy:
            return False
        preconfirm = oracle._retirement_preconfirm()
        if preconfirm is None or preconfirm[0] != selected_count:
            raise SemanticGateClosed("old retirement preconfirmation count changed")
        return actionable("DestoryInfoUI(Clone)/frame/confirm_button")
    if name == "SR_SSR_CONFIRM":
        if kind != "rarity-warning":
            return False
        target = _old_retirement_warning_target(
            oracle, ui, selected_count=selected_count,
            allowed_rarities=allowed_rarities, expected_levels=expected_levels)
        return actionable(target.path_suffix)
    if name == "GET_ITEMS_1":
        if kind != "award":
            return False
        oracle._retirement_reward_state()
        return actionable("AwardInfoUI(Clone)/items/close")
    if name == "EQUIP_CONFIRM":
        if kind != "equipment" or destroy:
            return False
        equipment = oracle._retirement_equipment_state((state, ui))
        if not equipment.all_checked:
            return actionable(panel + "main/options/ALL")
        return actionable(panel + "main/ok_btn")
    if name == "EQUIP_CONFIRM_2":
        if not destroy:
            return False
        for suffix, label in [
            ("got/title", "将获得以下材料:"),
            ("actions/destroy_button/Image", "确 定"),
            ("actions/cancel_button/Image", "取 消"),
        ]:
            values = oracle._active_retirement_texts(
                ui, panel + "destroy_confirm/" + suffix
            )
            if len(values) != 1 or values[0].text.replace(" ", "") != label.replace(
                " ", ""
            ):
                raise SemanticGateClosed(
                    "old retirement equipment confirmation is incomplete"
                )
        return actionable(panel + "destroy_confirm/actions/destroy_button")
    raise ValueError("unsupported old retirement native alias: " + name)


def prepare_old_retirement_alias_target(
    oracle, name, *, selected_count, allowed_rarities, expected_levels=None
):
    """Expose only a reviewed unique actionable target for a native request."""
    probe_name = "GET_ITEMS_1" if name == "GET_ITEMS_1_RETIREMENT_SAVE" else name
    records = oracle._retirement_records()
    if not probe_old_retirement_alias(
        oracle,
        probe_name,
        selected_count=selected_count,
        allowed_rarities=allowed_rarities,
        expected_levels=expected_levels,
        _records=records,
    ):
        raise SemanticGateClosed(
            "old retirement native control is not currently actionable"
        )
    if name == "SR_SSR_CONFIRM":
        return _old_retirement_warning_target(
            oracle, records[1], selected_count=selected_count,
            allowed_rarities=allowed_rarities, expected_levels=expected_levels)
    targets = {
        "SHIP_CONFIRM": OldRetirementDialogTarget(
            "retirement/preconfirm/open",
            "/blur_panel/select_panel/confirm_button",
            "/blur_panel/select_panel/confirm_button/confirm",
            "确 定",
        ),
        "SHIP_CONFIRM_2": OldRetirementDialogTarget(
            "retirement/ships/confirm",
            "DestoryInfoUI(Clone)/frame/confirm_button",
            "DestoryInfoUI(Clone)/frame/confirm_button/pic",
            "确 定",
        ),
        "EQUIP_CONFIRM": OldRetirementDialogTarget(
            "retirement/equipment/confirm-selection",
            "ResolveEquipmentUI(Clone)/main/ok_btn",
            "ResolveEquipmentUI(Clone)/main/ok_btn/Image",
            "确 定",
        ),
        "EQUIP_CONFIRM_2": OldRetirementDialogTarget(
            "retirement/equipment/disassemble/confirm",
            "ResolveEquipmentUI(Clone)/destroy_confirm/actions/destroy_button",
            "ResolveEquipmentUI(Clone)/destroy_confirm/got/title",
            "将获得以下材料:",
        ),
    }
    if name == "GET_ITEMS_1_RETIREMENT_SAVE":
        reward = oracle._retirement_reward_state()
        return OldRetirementDialogTarget(
            "retirement/reward/close",
            "AwardInfoUI(Clone)/items/close",
            "AwardInfoUI(Clone)/items/items_scroll/content/item_tpl(Clone)/bg/name_mask/name",
            reward.rewards[0][0],
        )
    if name == "EQUIP_CONFIRM" and not oracle._retirement_equipment_state().all_checked:
        return OldRetirementDialogTarget(
            "retirement/equipment/select-all",
            "ResolveEquipmentUI(Clone)/main/options/ALL",
            "ResolveEquipmentUI(Clone)/main/options/ALL/Label",
            "全部",
        )
    if name not in targets:
        raise ValueError("native alias has no input port: " + name)
    return targets[name]


class NativeOldRetirementDialogBoundary:
    def __init__(
        self,
        observe_oracle,
        fresh_oracle,
        *,
        before,
        owner_pid,
        selected_cards,
        selection_receipts,
        allowed_rarities,
        dispatch_retirement,
        require_common_cv=False,
    ):
        self.observe_oracle, self.fresh_oracle = observe_oracle, fresh_oracle
        self.before, self.owner_pid = before, owner_pid
        self.cards, self.selections = tuple(selected_cards), tuple(selection_receipts)
        self.allowed = frozenset(allowed_rarities)
        self.dispatch_retirement = dispatch_retirement
        self.requested = set()
        self.actions = []
        self.ship_rewards, self.equipment_rewards = (), ()
        self.equipment_quantities = None
        self.equipment_selection = None
        self.uncertain_requests = []
        self.refused_requests = []
        self.cv_policy_completed = not require_common_cv
        self.common_cv_preservation = []
        self.protected_source_candidates = []
        if (
            before.selected_count != 0
            or not self.cards
            or len(self.cards) != len(self.selections)
        ):
            raise SemanticGateClosed("old retirement has no owned selection batch")
        previous_generation = -1
        identities = set()
        for index, (card, receipt) in enumerate(zip(self.cards, self.selections)):
            if (
                receipt.pid != owner_pid
                or receipt.instance_id != card.instance_id
                or receipt.template_id != card.template_id
                or card.rarity not in self.allowed
                or receipt.count_before != index
                or receipt.count_after != index + 1
                or receipt.capacity_used != before.capacity_used
                or receipt.observed_generation <= receipt.action.generation
                or receipt.action.generation < previous_generation
                or card.instance_id in identities
            ):
                raise SemanticGateClosed(
                    "old retirement selection ownership is inconsistent"
                )
            previous_generation = receipt.observed_generation
            identities.add(card.instance_id)
        self.count = len(self.cards)

    def record_common_cv_preservation(self, receipt):
        """Keep source IDs intact: modal identity does not identify a Dock UUID."""
        if (not isinstance(receipt, RetirementCvDeselectionReceipt)
                or self.common_cv_preservation
                or any(value.endswith('/ships/confirm') for value in self.requested)
                or receipt.pid != self.owner_pid
                or receipt.selected_before != self.count
                or receipt.selected_after != self.count - 1
                or (receipt.capacity_used, receipt.capacity_total)
                != (self.before.capacity_used, self.before.capacity_total)
                or receipt.observed_generation <= receipt.action.generation):
            raise SemanticGateClosed('old retirement common-CV protection does not match owned batch')
        candidates = tuple(card.instance_id for card in self.cards
                           if (card.template_id, card.name, card.level)
                           == (receipt.template_id, receipt.name, receipt.level))
        if not candidates:
            raise SemanticGateClosed('protected modal card has no owned source candidate')
        self.common_cv_preservation.append(receipt)
        self.protected_source_candidates.append(candidates)
        self.actions.append(receipt.action)
        self.count = receipt.selected_after

    def _submitted_warning_levels(self):
        if not any(a.semantic_id.endswith('/ships/confirm') for a in self.actions):
            return None
        levels = [card.level for card in self.cards]
        for proof in self.common_cv_preservation:
            if proof.level not in levels:
                raise SemanticGateClosed('protected carrier level is not in owned batch')
            levels.remove(proof.level)
        if len(levels) != self.count:
            raise SemanticGateClosed('remaining owned levels do not match selected count')
        return tuple(levels)

    def _plan(self, oracle, alias):
        target = prepare_old_retirement_alias_target(
            oracle, alias, selected_count=self.count, allowed_rarities=self.allowed,
            expected_levels=(self._submitted_warning_levels()
                             if alias == 'SR_SSR_CONFIRM' else None),
        )
        if alias == "GET_ITEMS_1_RETIREMENT_SAVE":
            equipment = any(
                a.semantic_id.endswith("/equipment/disassemble/confirm")
                for a in self.actions
            )
            semantic_id = (
                "retirement/equipment/reward/close"
                if equipment
                else "retirement/reward/close"
            )
            target = replace(target, semantic_id=semantic_id)
        return target

    def appear(self, alias):
        oracle = self.observe_oracle()
        if not probe_old_retirement_alias(
            oracle, alias, selected_count=self.count, allowed_rarities=self.allowed,
            expected_levels=(self._submitted_warning_levels()
                             if alias == 'SR_SSR_CONFIRM' else None),
        ):
            return False
        if alias == "IN_RETIREMENT_CHECK":
            return True
        action_alias = (
            "GET_ITEMS_1_RETIREMENT_SAVE" if alias == "GET_ITEMS_1" else alias
        )
        # A still-visible accepted control is a passive wait, not permission
        # to repeat an unresolved ship/equipment submission or toggle ALL back.
        return self._plan(oracle, action_alias).semantic_id not in self.requested

    def click(self, alias):
        if alias == 'SHIP_CONFIRM_2':
            if self.count == 0:
                raise SemanticGateClosed('common-CV preservation left no ships to submit; no ship submission')
            if not self.cv_policy_completed:
                raise SemanticGateClosed('original common-CV preservation search has not completed')
        oracle = self.fresh_oracle()
        plan = self._plan(oracle, alias)
        if plan.semantic_id in self.requested:
            raise SemanticGateClosed(
                "old retirement phase already requested; input outcome must be inspected"
            )
        state, ui = oracle._retirement_records()
        if state.snapshot["pid"] != self.owner_pid:
            raise SemanticGateClosed(
                "old retirement runtime changed before confirmation"
            )
        final_ship = any(a.semantic_id.endswith("/ships/confirm") for a in self.actions)
        if (
            alias in ("EQUIP_CONFIRM", "EQUIP_CONFIRM_2", "GET_ITEMS_1_RETIREMENT_SAVE")
            and not final_ship
        ):
            raise SemanticGateClosed(
                "retirement reward/equipment has no owned ship submission"
            )
        if alias == "EQUIP_CONFIRM":
            equipment = oracle._retirement_equipment_state((state, ui))
            if self.equipment_quantities is None:
                self.equipment_quantities = equipment.item_quantities
            if equipment.item_quantities != self.equipment_quantities:
                raise SemanticGateClosed("old retirement equipment quantity changed")

        def validate(current, current_ui):
            if current.snapshot["pid"] != self.owner_pid:
                raise SemanticGateClosed("old retirement runtime changed at input")
            current_plan = self._plan(oracle, alias)
            if current_plan != plan:
                raise SemanticGateClosed("old retirement confirmation owner changed")
            if alias == "SHIP_CONFIRM":
                selection = oracle.retirement_selection_state()
                if (
                    selection.capacity_used,
                    selection.capacity_total,
                    selection.selected_count,
                ) != (
                    self.before.capacity_used,
                    self.before.capacity_total,
                    self.count,
                ):
                    raise SemanticGateClosed(
                        "old retirement batch changed before preconfirmation"
                    )
            if alias == "EQUIP_CONFIRM" and plan.semantic_id.endswith(
                "/confirm-selection"
            ):
                equipment = oracle._retirement_equipment_state((current, current_ui))
                if (
                    equipment.item_quantities != self.equipment_quantities
                    or not equipment.all_checked
                    or set(equipment.selected_slots)
                    != {slot for slot, _ in self.equipment_quantities}
                ):
                    raise SemanticGateClosed(
                        "old retirement equipment selection changed before input"
                    )
            if alias == "EQUIP_CONFIRM_2":
                if (
                    self.equipment_selection is None
                    or current.generation <= self.equipment_selection.generation
                ):
                    raise SemanticGateClosed(
                        "old retirement destruction has no fresh owned equipment selection"
                    )

        reward = None
        if alias == "GET_ITEMS_1_RETIREMENT_SAVE":
            reward = oracle._retirement_reward_state().rewards
        self.requested.add(plan.semantic_id)
        dispatched_before = oracle.input_dispatch_count

        def submit():
            return oracle._click_retirement_button(
                plan.semantic_id,
                plan.path_suffix,
                identity_text_suffix=plan.identity_text_suffix,
                identity_text=plan.identity_text,
                validate_records=validate,
            )

        try:
            receipt = (
                self.dispatch_retirement(submit)
                if alias == "SHIP_CONFIRM_2"
                else submit()
            )
        except BaseException as exc:
            # A requested phase may fail before or after actual dispatch. Do
            # not assert it was accepted, and do not replay it automatically.
            record = dict(
                semantic_id=plan.semantic_id,
                error=repr(exc),
                input_dispatched=oracle.input_dispatch_count > dispatched_before,
            )
            if not record["input_dispatched"]:
                self.requested.discard(plan.semantic_id)
                self.refused_requests.append(record)
            else:
                self.uncertain_requests.append(record)
            raise
        self.actions.append(receipt)
        if alias == "EQUIP_CONFIRM" and plan.semantic_id.endswith("/confirm-selection"):
            self.equipment_selection = receipt
        if reward is not None:
            if plan.semantic_id == "retirement/equipment/reward/close":
                self.equipment_rewards += reward
            else:
                self.ship_rewards += reward
        return receipt

    def finish_after_native_return(self):
        """Verify the native return's physical result; never click from here."""
        oracle = self.fresh_oracle()
        state = oracle.read_state()
        after = oracle.retirement_selection_state()
        if (
            state.snapshot["pid"] != self.owner_pid
            or after.selected_count != 0
            or after.capacity_total != self.before.capacity_total
            or self.before.capacity_used - after.capacity_used != self.count
            or not self.ship_rewards
            or self.uncertain_requests
        ):
            raise SemanticGateClosed(
                "old retirement native return lacks an exact completed transaction"
            )
        if not probe_old_retirement_alias(
            oracle,
            "IN_RETIREMENT_CHECK",
            selected_count=self.count,
            allowed_rarities=self.allowed,
        ) or after.generation <= max(a.generation for a in self.actions):
            raise SemanticGateClosed(
                "old retirement return is not a fresh unobscured destination"
            )
        destroyed = any(
            a.semantic_id.endswith("/equipment/disassemble/confirm")
            for a in self.actions
        )
        if self.equipment_quantities and (not destroyed or not self.equipment_rewards):
            raise SemanticGateClosed("old retirement equipment outcome is incomplete")
        submission = next(
            a for a in self.actions if a.semantic_id.endswith("/ships/confirm")
        )
        return OldRetirementExecutionReceipt(
            retired_count=self.count,
            policy_sha256=submission.policy_sha256,
            capability_id=submission.capability_id,
            capacity_before=self.before.capacity_used,
            capacity_after=after.capacity_used,
            capacity_total=after.capacity_total,
            returned_generation=after.generation,
            native_rarities=tuple(sorted(self.allowed)),
            selected_templates=tuple(c.template_id for c in self.cards),
            selected_ui_instances=tuple(c.instance_id for c in self.cards),
            ship_rewards=self.ship_rewards,
            equipment_policy="disassemble",
            equipment_preserved=False,
            equipment_disassembled=destroyed,
            equipment_quantities=self.equipment_quantities or (),
            equipment_rewards=self.equipment_rewards,
            actions=tuple(self.actions),
            selection_receipts=self.selections,
            common_cv_preservation=tuple(self.common_cv_preservation),
            protected_source_candidates=tuple(self.protected_source_candidates),
        )
