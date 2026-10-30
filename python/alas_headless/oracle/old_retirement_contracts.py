"""Owned card and receipt values for the original ALAS old-retire flow."""

from dataclasses import dataclass
from typing import Optional, Tuple
from .contracts import ActionReceipt, ButtonState


@dataclass(frozen=True)
class OldRetirementCard:
    template_id: int
    instance_id: int
    name: str
    level: int
    rarity: Optional[str]
    button: ButtonState


@dataclass(frozen=True)
class OldRetirementSelectionReceipt:
    action: ActionReceipt
    pid: int
    template_id: int
    instance_id: int
    count_before: int
    count_after: int
    capacity_used: int
    observed_generation: int


@dataclass(frozen=True)
class OldRetirementExecutionReceipt:
    retired_count: int
    capacity_before: int
    capacity_after: int
    capacity_total: int
    returned_generation: int
    native_rarities: Tuple[str, ...]
    selected_templates: Tuple[int, ...]
    selected_ui_instances: Tuple[int, ...]
    ship_rewards: Tuple[Tuple[str, int], ...]
    equipment_policy: str
    equipment_preserved: bool
    equipment_disassembled: bool
    equipment_quantities: Tuple[Tuple[int, int], ...]
    equipment_rewards: Tuple[Tuple[str, int], ...]
    actions: Tuple[ActionReceipt, ...]
    selection_receipts: Tuple[OldRetirementSelectionReceipt, ...]
    policy_sha256: str
    capability_id: str
    mode: str = "old_retire"
    common_cv_preservation: Tuple["RetirementCvDeselectionReceipt", ...] = ()
    protected_source_candidates: Tuple[Tuple[int, ...], ...] = ()

    def __post_init__(self):
        if (
            self.retired_count <= 0
            or self.capacity_before - self.capacity_after != self.retired_count
        ):
            raise ValueError("old retirement receipt capacity delta is inconsistent")
        if self.capacity_after < 0 or self.capacity_total <= 0:
            raise ValueError("old retirement receipt capacity is invalid")
        if self.equipment_policy != "disassemble" or self.equipment_preserved:
            raise ValueError("old retirement receipt conflicts with equipment policy")
        if (
            len(self.selected_ui_instances) != self.retired_count + len(self.common_cv_preservation)
            or len(set(self.selected_ui_instances)) != len(self.selected_ui_instances)
            or len(self.selected_templates) != len(self.selected_ui_instances)
        ):
            raise ValueError("old retirement receipt card identities are inconsistent")
        if len(self.protected_source_candidates) != len(self.common_cv_preservation):
            raise ValueError('old retirement protected source evidence is inconsistent')
        for proof, candidates in zip(self.common_cv_preservation, self.protected_source_candidates):
            if (not candidates or len(set(candidates)) != len(candidates)
                    or not set(candidates).issubset(self.selected_ui_instances)
                    or proof.selected_before - proof.selected_after != 1
                    or proof.selected_after != self.retired_count
                    or (proof.capacity_used, proof.capacity_total) != (self.capacity_before, self.capacity_total)):
                raise ValueError('old retirement protection and physical count disagree')
