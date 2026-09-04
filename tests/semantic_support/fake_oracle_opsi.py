"""Fake oracle opsi for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import SemanticGateClosed


class FakeOpsiOracle:
    def meta_page_visible(self):
        return self.meta_page_visible_value

    def meta_current_detail_state(self):
        raise SemanticGateClosed("META current detail identity is absent")

    def meta_assist_state(self):
        return self.meta_assist_state_value

    def click_meta_assist_next_candidate(self, *, expected_index, expected_level):
        if (
            expected_index != self.meta_assist_state_value.selected_candidate_index
            or expected_level != self.meta_assist_state_value.selected_level
        ):
            raise SemanticGateClosed("META assist candidate changed before selection")
        self.click_calls.append("meta/assist/candidate/3")
        return self.click_receipt("meta/assist/candidate/3")

    def click_meta_home(self):
        self.click_calls.append("meta/home")
        return self.click_receipt("meta/home")

    def meta_precombat_fleet_ready(self):
        return self.meta_precombat_fleet_ready_value

    def operation_siren_battle_result_visible(self):
        return False

    def operation_siren_battle_result_grade(self):
        raise SemanticGateClosed("operation siren battle result is absent")

    def operation_siren_exit_prompt_visible(self):
        return False

    def click_operation_siren_exit(self, confirm):
        if not self.operation_siren_exit_prompt_visible():
            raise SemanticGateClosed("operation siren exit prompt is absent")
        return self.click("os/exit/confirm" if confirm else "os/exit/cancel")

    def operation_siren_abyssal_entry_prompt_visible(self):
        return False

    def operation_siren_state(self):
        raise SemanticGateClosed("Operation Siren page identity is not proven")

    def operation_siren_map_overlay_present(self):
        return False

    def operation_siren_local_map_visible(self):
        return self.operation_siren_local_map_visible_value

    def operation_siren_page_visible(self):
        return self.operation_siren_page_visible_value

    def operation_siren_current_fleet(self):
        return 1

    def operation_siren_globe_state(self):
        raise SemanticGateClosed("Operation Siren globe identity is not proven")

    def operation_siren_mission_list_visible(self):
        return False

    def click_operation_siren_order(self, order_kind):
        return self.click("os/order/" + order_kind)

    def operation_siren_order_confirmation_visible(self, order_kind):
        return self.operation_siren_order_confirmation_visible_value

    def click_operation_siren_order_confirmation(self, order_kind, *, confirm):
        return self.click(
            "os/order/" + ("confirm" if confirm else "cancel")
        )

    def meta_assist_sortie_prompt_visible(self):
        return False

    def meta_simulation_prompt_visible(self):
        return False

    def meta_help_visible(self):
        return False
