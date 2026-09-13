"""Research for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    OracleState,
    ResearchDetailState,
    ResearchProjectState,
    ResearchProjectStatus,
    ResearchQueueEntryState,
    ResearchQueueState,
    ResearchResourceCostState,
)
from .errors import SemanticGateClosed


class ResearchOracle:
    """Research operations sharing the oracle frame and input boundary."""

    def research_reset_available(self) -> bool:
        """Recognize the observed exhausted refresh state, without guessing readiness."""
        state = self.read_state()
        if not self.enabled("research/page/back"):
            raise SemanticGateClosed("research reset page is absent or obscured")
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed("research reset frames are incoherent")
        path = "UICamera/Canvas/UIMain/TechnologyUI(Clone)/main/base_page/refresh_btn"
        labels = [t for t in ui.texts if t.path == path + "/Text"
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        icons = [i for i in ui.images if i.path == path and i.active_in_hierarchy
                 and i.active_and_enabled and not i.truncated]
        if len(labels) != 1 or len(icons) != 1 or icons[0].sprite != "refresh":
            raise SemanticGateClosed("research reset state is absent or ambiguous")
        if labels[0].text.strip() == "每日0点后可刷新":
            return False
        raise SemanticGateClosed("research reset ready state and input are not yet reviewed")

    def _research_progress_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        return bool(parts and parts[1:] == ("取消", "确定") and re.fullmatch(
            r"当前研究中的[^<>\r\n]+有新的进展，请去开发船坞确认", parts[0]
        ))

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        """Read the five visible research cards from typed Unity state."""

        return self._retry_transition_read(
            self._research_projects_once,
            attempts=12,
            interval_seconds=0.5,
        )

    def _research_projects_once(self) -> Tuple[ResearchProjectState, ...]:
        """Read one exact, internally coherent five-card snapshot."""

        return self._research_projects_snapshot()[1]

    def _research_projects_snapshot(
        self,
    ) -> Tuple[OracleState, Tuple[ResearchProjectState, ...]]:
        """Return the Button frame together with the cards derived from it."""

        button_state = self.read_state()
        back = self._unique(button_state, "research/page/back")
        if not back.actionable or self._blocking_rules(
            button_state, "research/page/back"
        ):
            raise SemanticGateClosed("research page identity is not proven")
        indexed = []
        pattern = re.compile(
            r"(?:^|/)TechnologyUI\(Clone\)/main/base_page/srcoll_rect/"
            r"content/([1-5])$"
        )
        for button in button_state.buttons:
            match = pattern.search(button.path)
            if (
                match is not None
                and button.name == match.group(1)
                and button.actionable
                and button.point is not None
                and 0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
            ):
                indexed.append((int(match.group(1)), button))
        if len(indexed) != 5 or len({item[0] for item in indexed}) != 5:
            raise SemanticGateClosed("research project Buttons are incomplete")
        indexed.sort(key=lambda item: (item[1].point.x, item[0]))

        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed research Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research snapshots are not coherent")

        def text_at(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research project text is absent or ambiguous: " + path
                )
            return matches[0].text.strip()

        projects = []
        for slot, (unity_index, button) in enumerate(indexed, start=1):
            root = button.path + "/frame/"
            code = text_at(root + "name_bg/Text")
            subtitle = text_at(root + "sub_name")
            marker = re.sub(r"<[^>]*>", "", text_at(root + "marks/Text")).strip()
            status = self._research_status_from_text(marker)
            duration = self.parse_countdown_seconds(text_at(root + "marks/time"))
            version_path = root + "top/label/version"
            versions = tuple(
                image
                for image in ui_state.images
                if image.path == version_path
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if len(versions) != 1:
                raise SemanticGateClosed("research project series is ambiguous")
            version = re.fullmatch(r"version_([1-9][0-9]*)", versions[0].sprite)
            if version is None or not code:
                raise SemanticGateClosed("research project identity is malformed")
            projects.append(
                ResearchProjectState(
                    slot=slot,
                    unity_index=unity_index,
                    code=code,
                    subtitle=subtitle,
                    series=int(version.group(1)),
                    status=status,
                    duration_seconds=duration,
                    button=button,
                )
            )
        return button_state, tuple(projects)

    def click_research_project(
        self, slot: int, *, expected_code: Optional[str] = None
    ) -> ActionReceipt:
        if slot not in range(1, 6):
            raise ValueError("research project slot must be 1 through 5")
        if expected_code is not None and (
            not isinstance(expected_code, str) or not expected_code.strip()
        ):
            raise ValueError("expected research project code must be non-empty")
        state, projects = self._retry_transition_read(
            self._research_projects_snapshot,
            attempts=12,
            interval_seconds=0.5,
        )
        matches = tuple(project for project in projects if project.slot == slot)
        if len(matches) != 1:
            raise SemanticGateClosed("research project slot identity changed")
        expected = matches[0]
        if expected_code is not None and expected.code != expected_code.strip():
            raise SemanticGateClosed("research project code changed before input")
        target = expected.button
        if self._blocking_rules(state, "research/project/{0}".format(slot)):
            raise SemanticGateClosed("research project input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="research/project/{0}".format(slot),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _research_status_from_text(value: str) -> ResearchProjectStatus:
        plain = re.sub(r"<[^>]*>", "", value).strip()
        statuses = {
            "查看详情": ResearchProjectStatus.DETAIL,
            "进行中": ResearchProjectStatus.RUNNING,
            "等待中": ResearchProjectStatus.WAITING,
            # The live CN queue currently labels a queued item as
            # “等待进行”, rather than the older “等待中” wording.
            "等待进行": ResearchProjectStatus.WAITING,
            "研究完成": ResearchProjectStatus.FINISHED,
        }
        try:
            return statuses[plain]
        except KeyError as exc:
            raise SemanticGateClosed(
                "research status is not reviewed: " + plain
            ) from exc

    def research_detail_state(self) -> ResearchDetailState:
        """Read the selected research detail and its exact action state."""

        button_state = self.read_state()
        root_button = self._unique(button_state, "research/detail/root")
        if not root_button.actionable or self._blocking_rules(
            button_state, "research/detail/root"
        ):
            raise SemanticGateClosed("research detail identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research detail snapshots are incomplete")

        root = "TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/"
        panel = "TechnologyUI(Clone)/main/base_page/selecte_panel/"

        def exact_text(suffix: str) -> str:
            path = root + suffix
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research detail text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        code = exact_text("name_bg/Text")
        subtitle = exact_text("sub_name")

        def panel_text(suffix: str) -> str:
            path = panel + suffix
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "research detail text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        action_ids = {
            "start": "research/detail/start",
            "stop": "research/detail/stop",
            "finish": "research/detail/finish",
            "queue": "research/detail/queue",
        }
        actions = {}
        for key, semantic_id in action_ids.items():
            matches = self._matches(button_state, semantic_id)
            if len(matches) > 1:
                raise SemanticGateClosed("research detail action is ambiguous: " + key)
            if key == "queue":
                actions[key] = self._research_queue_add_proven(
                    button_state, ui_state=ui_state
                )
            else:
                actions[key] = bool(matches and matches[0].actionable)

        duration = self.parse_countdown_seconds(panel_text("timer/bg/Text"))
        if not code:
            raise SemanticGateClosed("research detail code is absent")

        # A running or finished project no longer has a start cost panel in
        # the native client.  Its stop/finish action is sufficient to prove
        # the non-startable detail state; inventing a resource for it would
        # make a later confirmation unsafe.  Some idle projects likewise cost
        # no resource.  Their live detail has no cost count or resource icon,
        # and starts directly without a confirmation prompt.
        if actions["stop"] or actions["finish"]:
            resource_id = ""
            owned = 0
            required = 0
            resource_costs: Tuple[ResearchResourceCostState, ...] = ()
            requirement = ""
        else:
            container = panel + "consume_panel/bg/container/"
            costs = []
            for instance in ("item_tpl", "item_tpl(Clone)"):
                resource_count_path = container + instance + "/icon_bg/count"
                resource_path = container + instance + "/icon_bg/icon"
                resource_counts = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(resource_count_path)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
                )
                icons = tuple(
                    item
                    for item in ui_state.images
                    if item.path.endswith(resource_path)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
                )
                if not resource_counts and not icons:
                    continue
                if len(resource_counts) != 1 or len(icons) != 1:
                    raise SemanticGateClosed(
                        "research detail resource identity is ambiguous"
                    )
                resource = re.fullmatch(
                    r"([0-9]+)/([1-9][0-9]*)",
                    re.sub(r"<[^>]*>", "", resource_counts[0].text),
                )
                if resource is None:
                    raise SemanticGateClosed("research detail resource state is malformed")
                if re.fullmatch(r"[A-Za-z0-9_.-]+", icons[0].sprite) is None:
                    raise SemanticGateClosed(
                        "research detail resource identity is ambiguous"
                    )
                item_owned, item_required = map(int, resource.groups())
                # Research Q projects display the numeric inventory sprite on
                # their detail card, while the confirmation prompt names the
                # component by family and tier. Keep the reviewed legacy
                # carrier-aircraft aliases; other component families retain
                # their exact numeric item ids so both observations agree.
                item_resource_id = {
                    "17041": "research_part_t1",
                    "17042": "research_part_t2",
                    "17043": "research_part_t3",
                    "17044": "research_part_t4",
                }.get(icons[0].sprite, icons[0].sprite)
                costs.append(
                    ResearchResourceCostState(
                        resource_id=item_resource_id,
                        owned=item_owned,
                        required=item_required,
                    )
                )
            resource_costs = tuple(costs)
            if not resource_costs:
                resource_id = ""
                owned = 0
                required = 0
                requirement = ""
            else:
                primary = resource_costs[0]
                resource_id = primary.resource_id
                owned = primary.owned
                required = primary.required
                requirement = re.sub(
                    r"<[^>]*>",
                    "",
                    panel_text("consume_panel/bg/task_panel/slider/Text"),
                ).strip()
        return ResearchDetailState(
            code=code,
            subtitle=subtitle,
            duration_seconds=duration,
            resource_id=resource_id,
            resource_owned=owned,
            resource_required=required,
            requirement=requirement,
            can_start=actions["start"] and all(
                cost.owned >= cost.required for cost in resource_costs
            ),
            can_queue=actions["queue"],
            is_running=actions["stop"],
            is_finished=actions["finish"],
            resource_costs=resource_costs,
        )

    def _research_queue_add_proven(
        self, state: OracleState, ui_state: Optional[UIState] = None
    ) -> bool:
        matches = self._matches(state, "research/detail/queue")
        if len(matches) > 1:
            raise SemanticGateClosed("research queue-add target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        if self._blocking_rules(state, "research/detail/queue"):
            return False
        if target.actionable:
            return True
        if (
            target.raycast_top is not None
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False

        # The live 9.7.10 join_btn delegates raycasts to its same-path Image,
        # so the observer cannot assign a top-raycast result to the parent
        # Button.  Admit only this reviewed structure while a concurrently
        # actionable stop button proves that the selected project is running.
        stop = self._matches(state, "research/detail/stop")
        root = self._matches(state, "research/detail/root")
        if (
            len(stop) != 1
            or not stop[0].actionable
            or len(root) != 1
            or not root[0].actionable
        ):
            return False
        if ui_state is None:
            ui_state = self.read_ui_state()
        if (
            ui_state.image_truncated
            or ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("research queue-add snapshots are incomplete")
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == "join_btn"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("research queue-add image is ambiguous")
        return len(images) == 1

    def research_queue_add_available(self) -> bool:
        return self._retry_transition_read(
            self._research_queue_add_available_once,
            attempts=12,
            interval_seconds=0.5,
        )

    def _research_queue_add_available_once(self) -> bool:
        state = self.read_state()
        return self._research_queue_add_proven(state)

    def click_research_queue_add(self) -> ActionReceipt:
        def exact_state() -> OracleState:
            state = self.read_state()
            if not self._research_queue_add_proven(state):
                raise SemanticGateClosed("research queue-add input is not proven")
            return state

        state = self._retry_transition_read(
            exact_state,
            attempts=12,
            interval_seconds=0.5,
        )
        target = self._unique(state, "research/detail/queue")
        assert target.point is not None
        assert target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before research queue-add")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed after research queue-add")
        return ActionReceipt(
            semantic_id="research/detail/queue",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def research_queue_state(self) -> ResearchQueueState:
        """Read all non-empty queue slots and the reviewed claim control."""

        return self._retry_transition_read(self._research_queue_state_once)

    def _research_queue_state_once(self) -> ResearchQueueState:
        """Read one coherent Research queue snapshot without relaxing gates."""

        button_state = self.read_state()
        back = self._unique(button_state, "research/page/back")
        ui_state = self.read_ui_state()
        queue_title = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "TechnologyUI(Clone)/blur_panel/adapt/top/title_queue"
            )
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        if (
            not back.actionable
            or len(queue_title) > 1
            or ui_state.image_truncated
            or ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("research queue identity is not proven")

        def optional_text(path: str) -> Optional[str]:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("research queue text is ambiguous: " + path)
            return matches[0].text.strip() if matches else None

        entries = []
        for slot in range(1, 6):
            root = "TechnologyUI(Clone)/main/queue_page/queue_rect/content/{0}/frame/".format(
                slot
            )
            code = optional_text(root + "name_bg/Text")
            marker = optional_text(root + "marks/Text")
            remain = optional_text(root + "marks/time")
            version_path = root + "top/label/version"
            versions = tuple(
                image
                for image in ui_state.images
                if image.path.endswith(version_path)
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            if code is None and marker is None and remain is None and not versions:
                continue
            if code is None or marker is None or remain is None or len(versions) != 1:
                raise SemanticGateClosed("research queue slot is incomplete")
            version = re.fullmatch(r"version_([1-9][0-9]*)", versions[0].sprite)
            if version is None or not code:
                raise SemanticGateClosed("research queue identity is malformed")
            entries.append(
                ResearchQueueEntryState(
                    slot=slot,
                    code=code,
                    series=int(version.group(1)),
                    status=self._research_status_from_text(marker),
                    remaining_seconds=self.parse_countdown_seconds(remain),
                )
            )
        if not queue_title and not entries:
            raise SemanticGateClosed("research queue has no typed identity anchor")
        claim_matches = self._matches(button_state, "research/queue/claim")
        if len(claim_matches) > 1:
            raise SemanticGateClosed("research queue claim target is ambiguous")
        claimable = bool(claim_matches and claim_matches[0].actionable)
        if claimable and not any(
            entry.status == ResearchProjectStatus.FINISHED for entry in entries
        ):
            raise SemanticGateClosed("research queue claim state is inconsistent")
        return ResearchQueueState(tuple(entries), claimable)

    def _research_start_prompt_costs(
        self, state: OracleState
    ) -> Optional[Tuple[Tuple[str, int], ...]]:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        prefix = re.match(r"开启该科研项目需要消耗\s*:\s*", plain)
        if prefix is None or cancel != "取消" or confirm != "确定":
            return None
        item = r"(物资|心智魔方|(?:通用|主炮|鱼雷|防空炮|舰载机)部件T[1-4])x([1-9][0-9]*)"
        body = plain[prefix.end():]
        # Consume the whole prompt: never accept just the first recognized cost.
        if re.fullmatch(item + r"(?:[\s,，、]+" + item + r")*", body) is None:
            return None
        resource_ids = {
            "物资": "gold",
            "心智魔方": "20001",
            "舰载机部件T1": "research_part_t1",
            "舰载机部件T2": "research_part_t2",
            "舰载机部件T3": "research_part_t3",
            "舰载机部件T4": "research_part_t4",
            "通用部件T1": "17001",
            "通用部件T2": "17002",
            "通用部件T3": "17003",
            "通用部件T4": "17004",
            "主炮部件T1": "17011",
            "主炮部件T2": "17012",
            "主炮部件T3": "17013",
            "主炮部件T4": "17014",
            "鱼雷部件T1": "17021",
            "鱼雷部件T2": "17022",
            "鱼雷部件T3": "17023",
            "鱼雷部件T4": "17024",
            "防空炮部件T1": "17031",
            "防空炮部件T2": "17032",
            "防空炮部件T3": "17033",
            "防空炮部件T4": "17034",
        }
        costs = tuple((resource_ids[name], int(amount)) for name, amount in re.findall(item, body))
        if len({resource_id for resource_id, _ in costs}) != len(costs):
            return None
        return tuple(sorted(costs))

    def _research_start_prompt_cost(self, state: OracleState) -> Optional[Tuple[str, int]]:
        """Legacy single-cost observation must not silently drop companion costs."""
        costs = self._research_start_prompt_costs(state)
        return costs[0] if costs is not None and len(costs) == 1 else None

    def _research_queue_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            plain
            == "确定将该科研项目加入研究队列吗，加入队列的研究项目将顺序完成，不可取消"
            and cancel == "取消"
            and confirm == "确定"
        )

    def research_start_prompt_cost(self) -> Optional[Tuple[str, int]]:
        costs = self.research_start_prompt_costs()
        return costs[0] if costs is not None and len(costs) == 1 else None

    def research_start_prompt_costs(self) -> Optional[Tuple[Tuple[str, int], ...]]:
        state = self.read_state()
        target = self._matches(state, "research/start/confirm")
        if len(target) > 1:
            raise SemanticGateClosed("research start prompt is ambiguous")
        if not target or not target[0].actionable:
            return None
        return self._research_start_prompt_costs(state)
