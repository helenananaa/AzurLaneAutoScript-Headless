"""Fake oracle rewards for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import Bounds, MissionDisposition, Point, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from types import SimpleNamespace


class FakeRewardsOracle:
    def mail_surface_kind(self):
        if self.mail_surface_kind_value is not None:
            return self.mail_surface_kind_value
        if self.enabled_values.get("mail/manage/back") is True:
            return "manager"
        if self.exists_values.get("mail/page/back") is True or self.enabled_values.get(
            "mail/page/back"
        ) is True:
            return "page"
        return None

    def click_mission_claim_row(self, expected_path):
        self.click_calls.append("task/claim/row/0")
        return ActionReceipt(
            semantic_id="task/claim/row/0",
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path=expected_path,
        )

    def mail_is_empty(self):
        return self.mail_empty

    def mail_confirmation_kind(self):
        return self.mail_confirmation_kind_value

    def research_projects(self):
        if not self.research_projects_visible_value:
            raise SemanticGateClosed("research page identity is not proven")
        return tuple(self.research_project_values)

    def click_research_project(self, slot, *, expected_code=None, expected_series=None):
        if expected_code is not None:
            matches = tuple(
                project
                for project in self.research_project_values
                if project.slot == slot and project.code == expected_code
                and (expected_series is None or project.series == expected_series)
            )
            if len(matches) != 1:
                raise SemanticGateClosed("research project code changed before input")
        self.click_calls.append("research/project/{0}".format(slot))
        return self.click_receipt("research/project/{0}".format(slot))

    def research_detail_state(self):
        return self.research_detail_value

    def research_queue_state(self):
        if not self.research_queue_visible_value:
            raise SemanticGateClosed("research queue identity is not proven")
        return self.research_queue_value

    def research_start_prompt_cost(self):
        return self.research_prompt_cost

    def research_start_prompt_costs(self):
        cost = self.research_start_prompt_cost()
        return (cost,) if cost is not None else None

    def research_queue_add_available(self):
        return self.enabled_values.get("research/detail/queue", True)

    def click_research_queue_add(self):
        return self.click("research/detail/queue")

    def build_selected_pool(self):
        return self.build_pool_value

    def build_costs(self):
        return self.build_cost_value

    def build_submit_state(self):
        return self.build_submit_value

    def build_coins_owned(self):
        return self.build_gold_value

    def build_queue_empty(self):
        return self.build_queue_empty_value

    def build_queue_all_launch_available(self):
        return not self.build_queue_empty_value

    def click_build_queue_all_launch(self):
        return self.click("build/queue/all-launch")

    def build_queue_timers(self):
        if not self.build_queue_visible_value:
            raise SemanticGateClosed("construction queue is not visible")
        return self.build_queue_timer_values

    def build_queue_finish_prompt_cost(self):
        return self.build_queue_finish_prompt_value

    def new_ship_reward_visible(self):
        return self.new_ship_reward_visible_value

    def new_ship_reward_page_visible(self):
        return self.new_ship_reward_page_visible_value

    def battle_pass_page_visible(self):
        return self.battle_pass_page_visible_value

    def battle_pass_reward_available(self):
        return self.battle_pass_reward_available_value

    def battle_pass_claim_all_available(self):
        return self.battle_pass_claim_available_value

    def click_battle_pass_entrance(self):
        self.battle_pass_page_visible_value = True
        return self.click_receipt("reward/battle-pass/enter")

    def click_battle_pass_claim_all(self):
        if not self.battle_pass_claim_available_value:
            raise SemanticGateClosed("Battle Pass claim-all reward is unavailable")
        self.battle_pass_claim_available_value = False
        return self.click_receipt("battle-pass/claim-all")

    def click_battle_pass_home(self):
        self.battle_pass_page_visible_value = False
        return self.click_receipt("battle-pass/home")

    def recommendation_shop_visible(self):
        return self.recommendation_shop_visible_value

    def click_recommendation_shop_home(self):
        if not self.recommendation_shop_visible_value:
            raise SemanticGateClosed("shop shell identity is absent")
        self.recommendation_shop_visible_value = False
        return self.click_receipt("shop/home")

    def free_weekly_supply_pack_available(self):
        return self.free_weekly_supply_pack_available_value

    def shop_oil(self):
        return self.shop_oil_value

    def click_free_weekly_supply_pack(self):
        if not self.free_weekly_supply_pack_available_value:
            raise SemanticGateClosed("free weekly supply pack is unavailable")
        self.free_weekly_supply_pack_available_value = False
        return self.click_receipt("shop/free-weekly-pack")

    def war_archives_data_key_collected(self):
        if not self.war_archives_visible_value:
            raise SemanticGateClosed("war archives page identity is not proven")
        return self.war_archives_collected_value

    def war_archives_data_key_text(self):
        if not self.war_archives_visible_value:
            raise SemanticGateClosed("war archives page identity is not proven")
        return self.war_archives_key_text_value

    def click_war_archives_data_key_collect(self):
        if not self.war_archives_visible_value:
            raise SemanticGateClosed("war archives page identity is not proven")
        if self.war_archives_collected_value:
            raise SemanticGateClosed("war archives data key is already collected")
        self.war_archives_collected_value = True
        return self.click_receipt("archive/key/collect")

    def data_key_limit_prompt_visible(self):
        return self.data_key_limit_prompt_value

    def click_data_key_limit_choice(self, *, confirm):
        if not self.data_key_limit_prompt_value:
            raise SemanticGateClosed("data-key limit prompt is absent")
        self.data_key_limit_prompt_value = False
        if confirm:
            self.war_archives_collected_value = True
        return self.click_receipt(
            "archive/key-limit/confirm" if confirm else "archive/key-limit/cancel"
        )

    def dorm_state(self):
        return self.dorm_state_value

    def dorm_feed_state(self):
        return self.dorm_feed_state_value

    def dorm_empty_food_cancel_available(self):
        return self.dorm_empty_food_cancel_value

    def click_dorm_food(self, item_id):
        before = self.dorm_feed_state_value
        items = []
        for item in before.items:
            items.append(
                SimpleNamespace(
                    item_id=item.item_id,
                    value=item.value,
                    count=item.count - (1 if item.item_id == item_id else 0),
                )
            )
        selected = next(item for item in before.items if item.item_id == item_id)
        self.dorm_feed_state_value = SimpleNamespace(
            food=before.food + selected.value,
            capacity=before.capacity,
            items=tuple(items),
        )
        self.click_calls.append("dorm/feed/item/{0}".format(item_id))
        return self.click_receipt("dorm/feed/item/{0}".format(item_id))

    def tactical_slots(self):
        return tuple(self.tactical_slot_values)

    def tactical_empty_slots_ready(self):
        return self.tactical_empty_slots_ready_value

    def tactical_books(self):
        return tuple(self.tactical_book_values)

    def tactical_book_skill_progress(self):
        return self.tactical_book_skill_progress_value

    def tactical_remaining_seconds(self):
        return tuple(self.tactical_remaining_values)

    def tactical_continue_prompt_text(self):
        return self.tactical_prompt_text

    def commission_scroll_state(self):
        self.commission_scroll_calls.append("state")
        return self.commission_scroll_value

    def commission_scroll_next(self):
        self.commission_scroll_calls.append("next")
        return SimpleNamespace(direction="next")

    def commission_scroll_to_top(self):
        self.commission_scroll_calls.append("top")
        return SimpleNamespace(direction="top")

    def wait_for_mission_state(self, timeout_seconds):
        disposition = (
            self.mission_dispositions.pop(0)
            if self.mission_dispositions
            else self.mission_disposition
        )
        return SimpleNamespace(
            disposition=disposition,
            generation=9,
            claim_all=(object() if disposition == MissionDisposition.CLAIMABLE_ALL else None),
            claim_rows=((object(),) if disposition == MissionDisposition.CLAIMABLE_ROW else ()),
            unfinished_rows=(object(),),
        )

    def mission_page_state(self):
        disposition = (
            self.streaming_mission_dispositions.pop(0)
            if self.streaming_mission_dispositions
            else self.mission_disposition
        )
        self.streaming_generation += 1
        return SimpleNamespace(
            disposition=disposition,
            generation=self.streaming_generation,
            signature=(disposition,),
            claim_all=(
                object()
                if disposition == MissionDisposition.CLAIMABLE_ALL
                else None
            ),
            claim_rows=(
                (
                    SimpleNamespace(
                        path="root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                        "right_panel/content/0/frame/get_btn"
                    ),
                )
                if disposition == MissionDisposition.CLAIMABLE_ROW
                else ()
            ),
            unfinished_rows=(
                (object(),)
                if disposition == MissionDisposition.UNFINISHED
                else ()
            ),
        )

    def mission_weekly_reward_available(self):
        return self.mission_weekly_reward_available_value

    def weekly_mission_progress_claim_available(self):
        return self.weekly_mission_progress_claim_available_value

    def click_weekly_mission_progress_claim(self):
        self.click_calls.append("task/weekly-progress/claim")
        self.weekly_mission_progress_claim_available_value = False
        return self.click_receipt("task/weekly-progress/claim")

    def commission_rows(self):
        return ()

    def commission_is_empty(self):
        return False

    def reward_summary_count(self, section, counter):
        self.last_reward_summary_query = (section, counter)
        if not self.reward_summary_values:
            return 0
        return self.reward_summary_values.pop(0)

    def commission_detail_state(self):
        return self.commission_detail_value

    def commission_start_prompt_cost(self):
        return self.commission_start_prompt_cost_value

    def click_commission_row(self, signature):
        self.click_calls.append("commission/row/{0}".format(signature[0]))
        return ActionReceipt(
            semantic_id="commission/row/{0}".format(signature[0]),
            generation=10,
            point=Point(640, 190),
            bounds=Bounds(100, 100, 1180, 250),
            path="root/commission/row/{0}".format(signature[0]),
        )

    def click_commission_recommend(self, signature):
        self.click_calls.append("commission/detail/recommend")
        return ActionReceipt(
            semantic_id="commission/detail/recommend",
            generation=11,
            point=Point(935, 363),
            bounds=Bounds(855, 316, 1015, 410),
            path="root/commission/detail/recommend",
        )

    def click_commission_start(self, signature):
        self.click_calls.append("commission/detail/start")
        return ActionReceipt(
            semantic_id="commission/detail/start",
            generation=12,
            point=Point(1092, 363),
            bounds=Bounds(1012, 316, 1172, 410),
            path="root/commission/detail/start",
        )

    def commission_start_transition(self, signature):
        self.last_commission_transition_signature = tuple(signature)
        return self.commission_transition_value
