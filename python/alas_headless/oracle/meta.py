"""Meta for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from typing import Dict, Mapping, Optional, Tuple
from .contracts import (
    ActionReceipt,
    MetaAssistState,
    MetaCurrentDetailState,
    MetaDossierDetailState,
    MetaEntranceState,
    Point,
    TextState,
)
from .errors import SemanticGateClosed


class MetaOracle:
    """Meta operations sharing the oracle frame and input boundary."""

    def _meta_skill_full_prompt_state(self):
        state = self.read_state()
        if not any(b.active_in_hierarchy and b.active_and_enabled
                   for b in self._matches(state, 'os/exit/confirm')):
            return None
        pattern = r'[^\n]{1,128}META的当前研习技能已达满级，是否前往切换研习技能？'
        # Classify only this message before attempting its stable sandwich.
        # A foreign course/purchase dialog must remain with its own task port,
        # including while that dialog's text and Button slices are mounting.
        ui = self.read_ui_state()
        contents = [t for t in ui.texts
                    if t.path.endswith('Msgbox(Clone)/window/msg_panel/content')
                    and t.active_in_hierarchy and t.active_and_enabled
                    and not t.truncated and t.bounds is not None]
        if not any(re.fullmatch(pattern, re.sub(r'<[^>]*>', '', t.text).strip())
                   for t in contents):
            return None
        parts = self._msgbox_prompt_parts(state)
        if (parts is None or parts[1:] != ('取消', '确定')
                or re.fullmatch(pattern, parts[0]) is None):
            return None
        return state

    def meta_skill_full_prompt_visible(self) -> bool:
        return self._meta_skill_full_prompt_state() is not None

    def click_meta_skill_full_prompt(self, confirm: bool) -> ActionReceipt:
        state = self._meta_skill_full_prompt_state()
        if state is None:
            raise SemanticGateClosed('META skill-full prompt identity is not proven')
        target_id = 'os/exit/confirm' if confirm else 'os/exit/cancel'
        target = self._unique(state, target_id)
        # The shared Msgbox rule is historically named tactical-continue.
        # This exact text/choice sandwich proves that very modal as our owner;
        # every independent overlay remains a blocker.
        blockers = tuple(rule for rule in self._blocking_rules(state, target_id)
                         if not (rule.blocker_id == 'tactical-continue'
                                 and rule.path_fragment == '/Msgbox(Clone)/'))
        if (not target.actionable or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point) or blockers):
            raise SemanticGateClosed('META skill-full choice is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META skill-full input')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        for _ in range(16):
            self._sleep(.25)
            after = self.read_state()
            if (after.generation > state.generation
                    and not any(b.active_in_hierarchy and '/Msgbox(Clone)/' in b.path
                                for b in after.buttons)):
                return ActionReceipt(
                    semantic_id='meta/skill-full/' + ('confirm' if confirm else 'cancel'),
                    generation=state.generation, point=target.point,
                    bounds=target.bounds, path=target.path)
        raise SemanticGateClosed('META skill-full prompt did not close after input')

    def meta_character_menu_visible(self) -> bool:
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/character/sync')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('META synchronization menu is ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META synchronization menu frames are incoherent')
        images = [i for i in ui.images if i.path == targets[0].path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if len(images) != 1 or images[0].sprite != 'menu_syn_btn':
            raise SemanticGateClosed('META synchronization menu identity is unsupported')
        return not self._blocking_rules(state, 'meta/character/sync')

    def click_meta_character_sync(self) -> ActionReceipt:
        if not self.meta_character_menu_visible():
            raise SemanticGateClosed('META synchronization menu is absent')
        # Generic typed click revalidates unique target, exact top raycast,
        # freshness, blockers and foreground immediately before input.
        return self.click('meta/character/sync')

    def meta_character_tactics_page_visible(self) -> bool:
        root = 'OverlayCamera/Overlay/UIMain/MetaCharacterTacticsUI(Clone)/'
        state = self.read_state()
        skills = [b for b in state.buttons
                  if b.path == root + 'SkillPanel/Skills/Content/SkillTpl(Clone)'
                  and b.active_in_hierarchy and b.active_and_enabled]
        if not skills:
            return False
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META tactics frames are incoherent')
        names = [t for t in ui.texts
                 if t.path == root + 'NamePanel/NameMask/NameText'
                 and t.active_in_hierarchy and t.active_and_enabled
                 and not t.truncated and t.bounds is not None]
        return (len(names) == 1 and names[0].text.strip().endswith('META')
                and len(self._matches(state, 'meta/character/back')) == 1)

    def meta_character_page_visible(self) -> bool:
        if self.meta_character_tactics_page_visible():
            return True
        state = self.read_state()
        root = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/PTPanel/'
        if any(b.path.startswith(root) and b.active_in_hierarchy
               and b.active_and_enabled for b in state.buttons):
            return True
        catalogue = ('UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/'
                     'ScrollPanel/ListPanel/Container/BannerTpl(Clone)')
        if any(b.path == catalogue and b.active_in_hierarchy
               and b.active_and_enabled for b in state.buttons):
            # Back from focused detail can reveal the catalogue before leaving
            # META. Its native page graph must observe this existing owner too.
            backs = self._matches(state, 'meta/character/back')
            if len(backs) > 1:
                raise SemanticGateClosed('META catalogue return target is ambiguous')
            if (backs and backs[0].actionable
                    and not self._blocking_rules(state, 'meta/character/back')):
                return True
        return self.meta_character_sync_page_visible()

    def meta_character_sync_page_visible(self) -> bool:
        root = 'OverlayCamera/Overlay/UIMain/MetaCharacterSynUI(Clone)/'
        paths = (root + 'TaskPanel/BtnGetMore', root + 'TaskPanel/BtnGetAll')
        controls = [b for b in self.read_state().buttons
                    if b.active_in_hierarchy and b.active_and_enabled and b.path in paths]
        if len(controls) > 1:
            raise SemanticGateClosed('META synchronization reward control is ambiguous')
        return bool(controls)

    def meta_character_sync_rewards(self) -> Tuple[int, int, int]:
        """Read complete milestone totals without relying on repeated-row order."""
        state = self.read_state()
        ui = self.read_ui_state()
        return self._meta_character_sync_rewards_in_state(state, ui)

    def _meta_character_sync_rewards_in_state(self, state, ui) -> Tuple[int, int, int]:
        root = 'OverlayCamera/Overlay/UIMain/MetaCharacterSynUI(Clone)/'
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META synchronization reward frames are incoherent')
        paths = (root+'TaskPanel/BtnGetMore', root+'TaskPanel/BtnGetAll')
        controls = [b for b in state.buttons if b.path in paths
                    and b.active_in_hierarchy and b.active_and_enabled]
        images = [i for i in ui.images if i.active_in_hierarchy and i.active_and_enabled]
        identity = [i for i in images if len(controls) == 1 and i.path == controls[0].path]
        if len(controls) != 1 or len(identity) != 1 or identity[0].truncated or identity[0].sprite != 'btn_getall':
            raise SemanticGateClosed('META synchronization reward identity is unsupported')
        texts = [t for t in ui.texts if t.active_in_hierarchy and t.active_and_enabled]
        def numbers(path):
            matches = [t for t in texts if t.path == path]
            if not matches or any(t.truncated or not re.fullmatch(r'[0-9]+', t.text.strip()) for t in matches):
                raise SemanticGateClosed('META synchronization reward numbers are incomplete')
            return [int(t.text.strip()) for t in matches]
        points = numbers(root+'PTPanel/Count/NumText')
        row = root+'TaskPanel/Scroll/Viewport/Content/TaskTpl(Clone)/'
        thresholds = numbers(row+'PT/Count/NumText')
        indices = numbers(row+'Target/IndexText')
        got = [i for i in images if i.path == row+'Info/AwardInfo/Award/Tag/Got']
        masks = [i for i in images if i.path == row+'GotMask']
        if (len(points) != 1 or len(thresholds) != len(set(thresholds))
                or len(indices) != len(thresholds) or len(set(indices)) != len(indices)
                or any(t <= 0 for t in thresholds)
                or len(masks) != len(got) or any(i.truncated for i in masks+got)
                or any(i.sprite != 'tag_got' for i in got)):
            raise SemanticGateClosed('META synchronization reward rows are incomplete or ambiguous')
        eligible = sum(t <= points[0] for t in thresholds)
        if len(got) > eligible or self._blocking_rules(state, 'meta/character/rewards'):
            raise SemanticGateClosed('META synchronization reward state is inconsistent or obscured')
        return points[0], eligible, len(got)

    def click_meta_character_sync_rewards(self) -> ActionReceipt:
        state = self.read_state()
        ui = self.read_ui_state()
        _, eligible, claimed = self._meta_character_sync_rewards_in_state(state, ui)
        if eligible <= claimed:
            raise SemanticGateClosed('META synchronization has no claimable rewards')
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META synchronization claim frames are incoherent')
        root = 'OverlayCamera/Overlay/UIMain/MetaCharacterSynUI(Clone)/TaskPanel/'
        targets = [b for b in state.buttons if b.path in (root+'BtnGetMore', root+'BtnGetAll')
                   and b.active_in_hierarchy and b.active_and_enabled]
        if len(targets) != 1:
            raise SemanticGateClosed('META synchronization claim target is absent or ambiguous')
        target = targets[0]
        images = [i for i in ui.images if i.path == target.path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if (not target.interactable or target.raycast_top is False
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or len(images) != 1 or images[0].sprite != 'btn_getall'
                or images[0].raycast_target is not True or images[0].bounds != target.bounds
                or self._blocking_rules(state, 'meta/character/rewards')):
            raise SemanticGateClosed('META synchronization claim target is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META synchronization claim')
        self._tap(round(target.point.x), round(target.point.y))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after META synchronization claim')
        receipt = ActionReceipt(semantic_id='meta/character/rewards', generation=state.generation,
                                path=target.path, point=target.point, bounds=target.bounds)
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if self.read_state().generation > receipt.generation:
                if self.award_info_page_visible():
                    return receipt
                try:
                    if self.meta_character_sync_rewards()[2] > claimed:
                        return receipt
                except SemanticGateClosed:
                    pass
            self._sleep(0.2)
        raise SemanticGateClosed('META synchronization claim did not reach its reward postcondition')

    def meta_character_pending_sync(self) -> Tuple[int, int]:
        """Read the pre-unlock phase; other reward phases remain unqualified."""
        state = self.read_state()
        root = 'UICamera/Canvas/UIMain/MetaCharacterUI(Clone)/HidePanel/PTPanel/'
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META character progress frames are incoherent')
        for name, sprite in [('ShowWayBtn', 'ptpanel_btn_showway'), ('PreviewBtn', 'ptpanel_btn_preview')]:
            buttons = [b for b in state.buttons if b.path == root + name
                       and b.active_in_hierarchy and b.active_and_enabled]
            images = [i for i in ui.images if i.path == root + name and i.active_in_hierarchy
                      and i.active_and_enabled and not i.truncated]
            if len(buttons) != 1 or len(images) != 1 or images[0].sprite != sprite:
                raise SemanticGateClosed('META character reward phase is not yet adapted')
        texts = [t for t in ui.texts if t.path == root + 'Progress/PT/PTProgressText'
                 and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if len(texts) != 1:
            raise SemanticGateClosed('META character progress is missing or ambiguous')
        match = re.fullmatch(r'([0-9]+)/([1-9][0-9]*)', re.sub(r'<[^>]*>', '', texts[0].text).strip())
        if match is None:
            raise SemanticGateClosed('META character progress is malformed')
        current, required = int(match[1]), int(match[2])
        if current >= required:
            raise SemanticGateClosed('META synchronization-ready reward phase is not yet adapted')
        if self._blocking_rules(state, 'meta/character/progress'):
            raise SemanticGateClosed('META character progress is obscured')
        return current, required

    def click_meta_character_back(self) -> ActionReceipt:
        if not (self.meta_character_page_visible() or self.meta_character_menu_visible()):
            raise SemanticGateClosed('META character page is absent')
        state = self.read_state()
        target = self._unique(state, 'meta/character/back')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is False
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/character/back')):
            raise SemanticGateClosed('META character back is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META character back')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='meta/character/back', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def meta_reward_preview_entry_visible(self) -> bool:
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/reward-preview/open')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('META reward entry is ambiguous')
        target = targets[0]
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META reward entry frames are incoherent')
        images = [i for i in ui.images if i.path == target.path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if len(images) != 1 or images[0].sprite != 'btn_award':
            raise SemanticGateClosed('META reward entry identity is unsupported')
        return not self._blocking_rules(state, 'meta/reward-preview/open')

    def click_meta_reward_preview_entry(self) -> ActionReceipt:
        if not self.meta_reward_preview_entry_visible():
            raise SemanticGateClosed('META reward entry is absent')
        state = self.read_state()
        target = self._unique(state, 'meta/reward-preview/open')
        if (not target.actionable or target.raycast_top is not True
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/reward-preview/open')):
            raise SemanticGateClosed('META reward entry is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META reward entry')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='meta/reward-preview/open', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def meta_dossier_detail_visible(self) -> bool:
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/dossier/list')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('META dossier list identity is ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META dossier frames are incoherent')
        root = targets[0].path.rsplit('/', 1)[0]
        hp = [t for t in ui.texts if t.path == root + '/hp/Text'
              and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if len(hp) != 1:
            raise SemanticGateClosed('META dossier HP identity is incomplete')
        match = re.fullmatch(r'([0-9]+)/([1-9][0-9]*)', re.sub(r'<[^>]*>', '', hp[0].text).strip())
        if match is None or int(match[1]) > int(match[2]):
            raise SemanticGateClosed('META dossier HP is malformed')
        return True

    def click_meta_dossier_list(self) -> ActionReceipt:
        if not self.meta_dossier_detail_visible():
            raise SemanticGateClosed('META dossier page is absent')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/list')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not True
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/list')):
            raise SemanticGateClosed('META dossier list target is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier input')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='meta/dossier/list', generation=state.generation,
            path=target.path, point=target.point, bounds=target.bounds)

    def meta_dossier_detail_state(self, *, allow_auto_prompt=False, allow_auto_result=False) -> MetaDossierDetailState:
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/list')
        root = target.path.rsplit('/', 1)[0] + '/'
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META dossier detail frames are incoherent')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or any(not ((rule.blocker_id == 'meta-dossier-auto-prompt' and allow_auto_prompt)
                            or (rule.blocker_id == 'meta-dossier-auto-result' and allow_auto_result))
                       for rule in self._blocking_rules(state, 'meta/dossier/list'))):
            raise SemanticGateClosed('META dossier detail is absent or obscured')
        def exact(path):
            texts = [t for t in ui.texts if t.path == root+path
                     and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            if len(texts) != 1:
                raise SemanticGateClosed('META dossier detail text is absent or ambiguous: '+path)
            return re.sub(r'<[^>]*>', '', texts[0].text).strip()
        def fraction(path):
            value = re.fullmatch(r'([0-9]+)/([1-9][0-9]*)', exact(path))
            if value is None or int(value[1]) > int(value[2]):
                raise SemanticGateClosed('META dossier detail fraction is malformed: '+path)
            return int(value[1]), int(value[2])
        points, capacity = fraction('progress/value')
        hp, maximum = fraction('hp/Text')
        level = exact('hp/level/Text')
        if re.fullmatch(r'[1-9][0-9]*', level) is None:
            raise SemanticGateClosed('META dossier detail level is malformed')
        images = [i for i in ui.images if i.path == root+'btns/auto_btn'
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if not images and hp == 0:
            reward = self._unique(state, 'meta/dossier/reward')
            reward_images = [i for i in ui.images if i.path == reward.path
                             and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
            if (not reward.active_in_hierarchy or not reward.active_and_enabled
                    or len(reward_images) != 1 or reward_images[0].sprite != 'btn_get'):
                raise SemanticGateClosed('META completed dossier reward identity is incomplete')
            return MetaDossierDetailState(points, capacity, int(level), hp, maximum, None)
        if len(images) != 1 or not images[0].sprite:
            raise SemanticGateClosed('META dossier auto control identity is incomplete')
        return MetaDossierDetailState(points, capacity, int(level), hp, maximum, images[0].sprite)

    def meta_dossier_auto_result(self):
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/dossier/auto/result/confirm')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return None
        if len(targets) != 1:
            raise SemanticGateClosed('META dossier auto result is ambiguous')
        target = targets[0]
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('META dossier auto result frames are incoherent')
        root = target.path.rsplit('/btns/start', 1)[0]
        def text(suffix):
            items = [t for t in ui.texts if t.path == root+'/'+suffix
                     and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            if len(items) != 1:
                raise SemanticGateClosed('META dossier auto result text is incomplete: '+suffix)
            return re.sub(r'\s+', '', items[0].text)
        if (text('top/title') != '自动作战' or text('msg_panel/label') != '自动作战完成'
                or text('btns/start/pic') != '确定'):
            raise SemanticGateClosed('META dossier auto result identity is unsupported')
        values = [text('msg_panel/'+s+'/Text') for s in ('oil', 'battle_cnt', 'damage')]
        if any(re.fullmatch(r'[0-9]+', v) is None for v in values) or int(values[1]) <= 0 or int(values[2]) <= 0:
            raise SemanticGateClosed('META dossier auto result amounts are malformed')
        images = [i for i in ui.images if i.path == target.path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if (len(images) != 1 or images[0].sprite != 'btn_big_red'
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/auto/result/confirm')):
            raise SemanticGateClosed('META dossier auto result confirmation is not actionable')
        if self.meta_dossier_detail_state(allow_auto_result=True).current_hp != 0:
            raise SemanticGateClosed('META dossier auto result has remaining HP')
        return dict(oil=int(values[0]), battle_count=int(values[1]), damage=int(values[2]))

    def click_meta_dossier_auto_result_confirm(self) -> ActionReceipt:
        result = self._retry_transition_read(self.meta_dossier_auto_result)
        if result is None:
            raise SemanticGateClosed('META dossier auto result is absent')
        self.last_meta_dossier_auto_result = result
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/auto/result/confirm')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/auto/result/confirm')):
            raise SemanticGateClosed('META dossier auto result target changed')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier auto result input')
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic()+12.0
        while True:
            after = self.read_state()
            try:
                closed = (after.generation > state.generation and self.meta_dossier_auto_result() is None
                          and self.meta_dossier_detail_state().current_hp == 0)
            except SemanticGateClosed:
                closed = False
            if closed:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier auto result did not close')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/auto/result/confirm', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def meta_dossier_reward_visible(self):
        if not self.meta_dossier_detail_visible():
            return False
        return self.meta_dossier_detail_state().current_hp == 0

    def click_meta_dossier_reward(self) -> ActionReceipt:
        if not self._retry_transition_read(self.meta_dossier_reward_visible):
            raise SemanticGateClosed('META completed dossier reward is absent')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/reward')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/reward')):
            raise SemanticGateClosed('META dossier reward is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier reward input')
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic()+12.0
        while True:
            after = self.read_state()
            if after.generation > state.generation and self.award_info_page_visible():
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier reward did not reach its award postcondition')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/reward', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def meta_dossier_auto_remaining_seconds(self):
        detail = self.meta_dossier_detail_state()
        if detail.auto_sprite != 'auto_02':
            return None
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/auto/start')
        ui = self.read_ui_state()
        texts = [t for t in ui.texts if t.path == target.path+'/Text'
                 and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if not state.generation <= ui.generation <= state.generation+2 or len(texts) != 1:
            raise SemanticGateClosed('META dossier automatic countdown is incomplete')
        match = re.fullmatch(r'([0-9]+):([0-5][0-9]):([0-5][0-9])', texts[0].text.strip())
        if match is None or detail.current_hp <= 0:
            raise SemanticGateClosed('META dossier automatic countdown is malformed')
        return int(match[1])*3600+int(match[2])*60+int(match[3])

    def meta_dossier_auto_prompt(self):
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/dossier/auto/confirm')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return None
        if len(targets) != 1:
            raise SemanticGateClosed('META dossier auto prompt is ambiguous')
        target = targets[0]
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('META dossier auto prompt frames are incoherent')
        root = target.path.rsplit('/btns/start', 1)[0]
        def text(suffix):
            items = [t for t in ui.texts if t.path == root+'/'+suffix
                     and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            if len(items) != 1:
                raise SemanticGateClosed('META dossier auto prompt text is incomplete: '+suffix)
            return items[0].text.strip()
        if text('top/title') != '自动作战' or text('btns/start/pic') != '开始':
            raise SemanticGateClosed('META dossier auto prompt identity is unsupported')
        minutes = re.fullmatch(r'([1-9][0-9]*)MIN', text('msg_panel/time/Text'))
        values = [text('msg_panel/'+s+'/Text') for s in ('oil', 'battle_cnt', 'highest_damage')]
        if minutes is None or any(re.fullmatch(r'[0-9]+', v) is None for v in values):
            raise SemanticGateClosed('META dossier auto prompt costs are malformed')
        if int(values[1]) <= 0 or int(values[2]) <= 0:
            raise SemanticGateClosed('META dossier auto prompt has no proven challenge')
        images = [i for i in ui.images if i.path == target.path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        if (len(images) != 1 or images[0].sprite != 'btn_big_red'
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/auto/confirm')):
            raise SemanticGateClosed('META dossier auto confirmation is not actionable')
        return {'minutes': int(minutes[1]), 'oil': int(values[0]),
                'battle_count': int(values[1]), 'highest_damage': int(values[2])}

    def click_meta_dossier_auto_confirm(self) -> ActionReceipt:
        costs = self._retry_transition_read(self.meta_dossier_auto_prompt)
        if costs is None:
            raise SemanticGateClosed('META dossier auto confirmation is absent')
        detail = self.meta_dossier_detail_state(allow_auto_prompt=True)
        if detail.current_hp <= 0 or detail.auto_sprite != 'auto_01':
            raise SemanticGateClosed('META dossier auto confirmation has no available dossier')
        self.last_meta_dossier_auto_costs = costs
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/auto/confirm')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/auto/confirm')):
            raise SemanticGateClosed('META dossier auto confirmation target changed')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier auto confirmation')
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic()+12.0
        while True:
            after = self.read_state()
            try:
                advanced = (after.generation > state.generation
                            and self.meta_dossier_auto_prompt() is None
                            and self.meta_dossier_auto_remaining_seconds() is not None)
            except SemanticGateClosed:
                # The native server transition briefly mounts Loading. Wait
                # for typed postconditions without dispatching another input.
                advanced = False
            if advanced:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier auto confirmation did not change its phase')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/auto/confirm', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def click_meta_dossier_auto_start(self) -> ActionReceipt:
        summary = self._retry_transition_read(self.meta_dossier_detail_state)
        if summary.auto_sprite == 'auto_03':
            raise SemanticGateClosed('META dossier automatic attack requires one completed challenge')
        if summary.current_hp <= 0 or summary.auto_sprite != 'auto_01':
            raise SemanticGateClosed('META dossier automatic attack is not available')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/auto/start')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/auto/start')):
            raise SemanticGateClosed('META dossier auto target is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier auto input')
        self.last_meta_dossier_auto_transition = []
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic() + 12.0
        while True:
            after = self.read_state()
            ui = self.read_ui_state()
            if after.generation <= ui.generation <= after.generation + 2:
                self.last_meta_dossier_auto_transition.append({
                    'generation': after.generation,
                    'texts': [{'path': t.path, 'text': t.text} for t in ui.texts
                              if t.active_in_hierarchy and t.active_and_enabled
                              and not t.truncated and t.text.strip()
                              and 'ArchivesWorldBossDetailUI(Clone)' not in t.path],
                    'buttons': [b.path for b in after.buttons if b.active_in_hierarchy
                                and b.active_and_enabled and '/WorldBossUI(Clone)/' not in b.path],
                })
                self.last_meta_dossier_auto_transition = self.last_meta_dossier_auto_transition[-32:]
            if (after.generation > state.generation and self.meta_dossier_auto_prompt() is not None):
                # Only acknowledge opening the confirmation layer. Its content
                # and input require a separate reviewed confirmation port.
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier auto start did not reach its confirmation postcondition')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/auto/start', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def click_meta_dossier_start(self) -> ActionReceipt:
        summary = self._retry_transition_read(self.meta_dossier_detail_state)
        if summary.current_hp <= 0:
            raise SemanticGateClosed('META dossier has no remaining HP')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/start')
        ui = self.read_ui_state()
        images = [i for i in ui.images if i.path == target.path and i.active_in_hierarchy
                  and i.active_and_enabled and not i.truncated]
        if (not state.generation <= ui.generation <= state.generation+2
                or len(images) != 1 or images[0].sprite != 'btn_start'
                or not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/start')):
            raise SemanticGateClosed('META dossier start is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier start')
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic()+12.0
        while True:
            after = self.read_state()
            if after.generation > state.generation and self.daily_precombat_visible():
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier start did not reach its fleet preparation postcondition')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/start', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def meta_dossier_assist_visible(self) -> bool:
        state = self.read_state()
        targets = [b for b in self._matches(state, 'meta/dossier/current')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('META dossier assist list is ambiguous')
        root = targets[0].path.rsplit('/', 1)[0]
        return sum(b.path == root + '/list_panel/frame/filter/refresh_btn'
                   and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons) == 1

    def click_meta_dossier_current(self) -> ActionReceipt:
        if not self.meta_dossier_assist_visible():
            raise SemanticGateClosed('META dossier assist page is unavailable')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/current')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not True
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/current')):
            raise SemanticGateClosed('META current list target is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META list input')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='meta/dossier/current', generation=state.generation,
            path=target.path, point=target.point, bounds=target.bounds)

    def meta_entrance_available(self) -> bool:
        """Admit the exact META link card on the reward summary page."""

        state = self.read_state()
        page = self._matches(state, "reward/page/back")
        entrance = self._matches(state, "reward/meta/enter")
        if len(page) != 1 or len(entrance) != 1:
            return False
        target = entrance[0]
        # This Selectable delegates the final raycast to its child Image.  The
        # observer therefore reports no top Button while still proving the
        # unique enabled/interactable card and its exact geometry.
        return bool(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "reward/meta/enter")
        )

    def click_meta_entrance(self) -> ActionReceipt:
        """Open META through the proven delegated reward-summary card."""

        if not self.meta_entrance_available():
            raise SemanticGateClosed("META entrance is not actionable")
        state = self.read_state()
        target = self._unique(state, "reward/meta/enter")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="reward/meta/enter",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_entrance_state(self) -> MetaEntranceState:
        """Read current and dossier META resources from the landing page."""

        button_state = self.read_state()
        back = self._unique(button_state, "meta/page/back")
        current = self._unique(button_state, "meta/current/open")
        dossier = self._unique(button_state, "meta/dossier/open")
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in (back, current, dossier)
        ):
            raise SemanticGateClosed("META landing page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META landing snapshots are not coherent")
        root = "WorldBossUI(Clone)/pages/WorldBossEntranceUI(Clone)/"

        def exact(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "META landing text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        def fraction(value: str, field: str) -> Tuple[int, int]:
            match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", value)
            if match is None:
                raise SemanticGateClosed("META " + field + " is malformed")
            actual, capacity = map(int, match.groups())
            if actual > capacity:
                raise SemanticGateClosed("META " + field + " is inconsistent")
            return actual, capacity

        current_points, current_capacity = fraction(
            exact("current_progress/value"), "current progress"
        )
        dossier_points, dossier_capacity = fraction(
            exact("past_progress/value"), "dossier progress"
        )
        daily_points, daily_capacity = fraction(exact("current/acc"), "daily progress")
        consume_text = exact("current/consume")
        remaining_text = exact("current/time")
        if (
            re.fullmatch(r"[1-9][0-9]*", consume_text) is None
            or re.fullmatch(r"[0-9]+天", remaining_text) is None
        ):
            raise SemanticGateClosed("META schedule summary is malformed")
        return MetaEntranceState(
            current_points=current_points,
            current_capacity=current_capacity,
            dossier_points=dossier_points,
            dossier_capacity=dossier_capacity,
            daily_points=daily_points,
            daily_capacity=daily_capacity,
            consume_points=int(consume_text),
            remaining_days=int(remaining_text[:-1]),
        )

    def meta_page_visible(self) -> bool:
        """Return whether a reviewed WorldBoss page owns UI."""

        for probe in (
            self.meta_entrance_state,
            self.meta_current_empty_points,
            self.meta_dossier_empty_points,
            self.meta_dossier_sync_points,
            self.meta_current_detail_state,
            self.meta_assist_state,
        ):
            try:
                probe()
                return True
            except SemanticGateClosed:
                pass
        return self.meta_dossier_detail_visible()

    def click_meta_home(self) -> ActionReceipt:
        """Return from any reviewed META page through its exact home control."""

        def read_target():
            if not self.meta_page_visible():
                raise SemanticGateClosed("META page identity is absent")
            state = self.read_state()
            target = self._unique(state, "meta/home")
            if not (
                target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.raycast_top is None
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
                and not self._blocking_rules(state, "meta/home")
            ):
                raise SemanticGateClosed("META home control is not actionable")
            return state, target

        # Re-read the complete existing proof while the returned assist list
        # settles. The common transition helper injects no input and still
        # fails after its bounded attempts if any proof remains unavailable.
        state, target = self._retry_transition_read(read_target)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before META home input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed after META home input")
        return ActionReceipt(
            semantic_id="meta/home",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_category_back_control(self):
        """Prove the inner-page return used by ALAS' ASH_QUIT branch."""
        if not self.meta_page_visible():
            raise SemanticGateClosed("META category page identity is absent")
        state = self.read_state()
        target = self._unique(state, 'meta/category/back')
        if not (
            target.active_in_hierarchy and target.active_and_enabled
            and target.interactable and target.raycast_top in (None, True)
            and target.point is not None and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, 'meta/category/back')
        ):
            raise SemanticGateClosed("META category back control is not actionable")
        return state, target

    def click_meta_category_back(self) -> ActionReceipt:
        state, target = self.meta_category_back_control()
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('meta/category/back', state.generation,
                             target.point, target.bounds, target.path)

    def click_meta_card(self, dossier: bool) -> ActionReceipt:
        """Open one exact META category card from a proven landing state."""

        self.meta_entrance_state()
        state = self.read_state()
        semantic_id = "meta/dossier/open" if dossier else "meta/current/open"
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("META category card is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        """Read the exact self-beacon detail page before assist or combat."""

        button_state = self.read_state()
        reward_phase = any(b.active_in_hierarchy and b.active_and_enabled
                           for b in self._matches(button_state, 'meta/current/reward'))
        control_ids = (('meta/current/detail/list', 'meta/current/reward') if reward_phase
                       else ('meta/current/detail/list', 'meta/current/help', 'meta/current/start'))
        controls = tuple(
            self._unique(button_state, semantic_id)
            for semantic_id in control_ids
        )
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in controls
        ):
            raise SemanticGateClosed("META current detail identity is absent")
        if any(
            self._blocking_rules(button_state, semantic_id)
            for semantic_id in control_ids
        ):
            raise SemanticGateClosed("META current detail is obstructed")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META current detail snapshots are not coherent")
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossDetailUI(Clone)/"

        def exact(path: str) -> str:
            matches = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("META current detail text is ambiguous")
            return matches[0]

        progress = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("progress/value"))
        attempts = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("point/Text"))
        hp = re.fullmatch(
            r"([0-9]+)/<color=#[0-9A-Fa-f]{6}>([1-9][0-9]*)</color>",
            exact("hp/Text"),
        )
        level = exact("hp/level/Text")
        if progress is None or attempts is None or hp is None or not level.isdigit():
            raise SemanticGateClosed("META current detail summary is malformed")
        current_points, point_capacity = map(int, progress.groups())
        remaining_attempts, attempt_capacity = map(int, attempts.groups())
        current_hp, max_hp = map(int, hp.groups())
        if reward_phase:
            target = controls[1]
            images = [i for i in ui_state.images if i.path == target.path
                      and i.active_in_hierarchy and i.active_and_enabled]
            if (current_hp != 0 or len(images) != 1 or images[0].truncated
                    or images[0].sprite != 'btn_get'):
                raise SemanticGateClosed('META completed beacon reward identity is unsupported')
        if (
            current_points > point_capacity
            or remaining_attempts > attempt_capacity
            or current_hp > max_hp
        ):
            raise SemanticGateClosed("META current detail summary is inconsistent")
        return MetaCurrentDetailState(
            current_points=current_points,
            point_capacity=point_capacity,
            remaining_attempts=remaining_attempts,
            attempt_capacity=attempt_capacity,
            level=int(level),
            current_hp=current_hp,
            max_hp=max_hp,
        )

    def _click_meta_current_detail_control(self, semantic_id: str) -> ActionReceipt:
        self._retry_transition_read(self.meta_current_detail_state)
        state = self.read_state()
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("META current detail control is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META detail input')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_current_help(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/help")

    def meta_current_reward_visible(self) -> bool:
        if not self._matches(self.read_state(), 'meta/current/reward'):
            return False
        return self.meta_current_detail_state().current_hp == 0

    def click_meta_current_reward(self) -> ActionReceipt:
        if not self.meta_current_reward_visible():
            raise SemanticGateClosed('META completed beacon reward is absent')
        return self._click_meta_current_detail_control('meta/current/reward')

    def click_meta_current_start(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/start")

    def click_meta_current_detail_list(self) -> ActionReceipt:
        return self._click_meta_current_detail_control("meta/current/detail/list")

    def meta_current_empty_points(self, *, require_create: bool = False) -> Tuple[int, int]:
        """Read current-beacon points from the exact empty-beacon page."""

        return self._meta_empty_points('current', require_create=require_create)

    def meta_dossier_empty_points(self, *, require_create: bool = False) -> Tuple[int, int]:
        """Read archive points from the mounted empty dossier page."""

        return self._meta_empty_points('dossier', require_create=require_create)

    def meta_dossier_sync_points(self) -> int:
        state = self.read_state()
        back = self._unique(state, 'meta/dossier/sync/back')
        ui = self.read_ui_state()
        if (not back.active_in_hierarchy or not back.active_and_enabled
                or not back.interactable or back.raycast_top is not None
                or not state.generation <= ui.generation <= state.generation + 2
                or self._blocking_rules(state, 'ui/absence-probe')):
            raise SemanticGateClosed('META dossier sync page is not coherent or unobscured')
        root = 'WorldBossUI(Clone)/pages/ArchivesWorldBossListUI(Clone)/'
        values = [t.text.strip() for t in ui.texts if t.path.endswith(root+'main/award/pt/Text')
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        selected = [t.text.strip() for t in ui.texts
                    if re.search(re.escape(root)+r'main/list/scrollrect/content/[0-9]+/underway/label$', t.path)
                    and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if len(values) != 1 or not values[0].isdecimal() or len(selected) != 1:
            raise SemanticGateClosed('META dossier sync point identity is ambiguous')
        match = re.fullmatch(r'同步值\(([0-9]+)/([1-9][0-9]*)\)', selected[0])
        if match is None or int(match[1]) != int(values[0]) or int(match[1]) > int(match[2]):
            raise SemanticGateClosed('META dossier sync point identity is inconsistent')
        return int(values[0])

    def meta_dossier_sync_page_visible(self) -> bool:
        if not self.observation_target_present('meta/dossier/sync/back'):
            return False
        self._retry_transition_read(self.meta_dossier_sync_points)
        return True

    def meta_dossier_sync_reward_available(self) -> bool:
        """Read the game's explicit eligibility marker, including inactive state."""
        return self._retry_transition_read(self._meta_dossier_sync_reward_available)

    def _meta_dossier_sync_reward_available(self) -> bool:
        if self.meta_dossier_sync_page_visible():
            suffix = 'WorldBossUI(Clone)/pages/ArchivesWorldBossListUI(Clone)/main/award/get_all'
        elif self.meta_dossier_detail_visible():
            self.meta_dossier_detail_state()
            suffix = 'WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/archives_btn/tip'
        else:
            self.meta_dossier_empty_points()
            suffix = 'WorldBossUI(Clone)/pages/ArchivesWorldBossEmptyUI(Clone)/archives_btn/tip'
        state = self.read_state()
        ui = self.read_ui_state()
        markers = [i for i in ui.images if i.path.endswith(suffix)]
        if (not state.generation <= ui.generation <= state.generation + 2
                or self._blocking_rules(state, 'ui/absence-probe')
                or len(markers) != 1 or markers[0].truncated
                or markers[0].active_in_hierarchy != markers[0].active_and_enabled):
            raise SemanticGateClosed('META dossier reward eligibility marker is incomplete or incoherent')
        return markers[0].active_in_hierarchy

    def click_meta_dossier_sync_rewards(self) -> ActionReceipt:
        self.meta_dossier_sync_points()
        if not self.meta_dossier_sync_reward_available():
            raise SemanticGateClosed('META dossier synchronization has no claimable rewards')
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/sync/rewards')
        ui = self.read_ui_state()
        images = [i for i in ui.images if i.path == target.path]
        if (not state.generation <= ui.generation <= state.generation + 2
                or len(images) != 1 or images[0].truncated
                or not images[0].active_in_hierarchy or not images[0].active_and_enabled
                or images[0].bounds != target.bounds
                or not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is False
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/sync/rewards')):
            raise SemanticGateClosed('META dossier synchronization reward target is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier synchronization claim')
        self._tap(round(target.point.x), round(target.point.y))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after META dossier synchronization claim')
        receipt = ActionReceipt(semantic_id='meta/dossier/sync/rewards', generation=state.generation,
                                path=target.path, point=target.point, bounds=target.bounds)
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            try:
                if self.read_state().generation > state.generation:
                    if self.award_info_page_visible():
                        return receipt
                    if not self.meta_dossier_sync_reward_available():
                        return receipt
            except SemanticGateClosed:
                pass  # Read the server transition; never repeat its input.
            self._sleep(.2)
        raise SemanticGateClosed('META dossier synchronization claim did not reach its reward postcondition')

    def click_meta_dossier_sync_open(self) -> ActionReceipt:
        """Open the exact archive progress control; ALAS owns page arrival."""
        self.meta_dossier_empty_points()
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/sync/open')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('META dossier sync entry snapshots are not coherent')
        images = [i for i in ui.images if i.path == target.path
                  and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        values = [t.text.strip() for t in ui.texts if t.path == target.path+'/Text'
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if (len(images) != 1 or images[0].sprite != 'btn' or len(values) != 1
                or re.fullmatch(r'[0-9]+/[1-9][0-9]*', values[0]) is None):
            raise SemanticGateClosed('META dossier sync entry identity is unsupported')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/sync/open')):
            raise SemanticGateClosed('META dossier sync entry is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier sync entry')
        self._tap(round(target.point.x), round(target.point.y))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after META dossier sync entry')
        return ActionReceipt(semantic_id='meta/dossier/sync/open', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def _meta_empty_points(self, category, *, require_create):
        list_id = ('meta/dossier/empty/list' if category == 'dossier' else 'meta/current/list')
        create_id = 'meta/' + category + '/create'

        button_state = self.read_state()
        controls = tuple(
            self._unique(button_state, semantic_id)
            for semantic_id in ((list_id, create_id) if require_create else (list_id,))
        )
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in controls
        ):
            raise SemanticGateClosed("META empty-beacon page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META empty-beacon snapshots are not coherent")
        page = ('ArchivesWorldBossEmptyUI' if category == 'dossier' else 'CurrentWorldBossEmptyUI')
        root = 'WorldBossUI(Clone)/pages/' + page + '(Clone)/'
        suffix = root + 'progress/value'
        if category == 'dossier':
            for target, sprite in zip(controls, ('archives_list_btn', 'useitem')):
                images = [i for i in ui_state.images if i.path == target.path
                          and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
                if len(images) != 1 or images[0].sprite != sprite:
                    raise SemanticGateClosed('META empty dossier control identity is unsupported')
        values = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith(suffix)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(values) != 1:
            raise SemanticGateClosed("META empty-beacon point counter is ambiguous")
        match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", values[0])
        if match is None:
            raise SemanticGateClosed("META empty-beacon point counter is malformed")
        current, capacity = map(int, match.groups())
        if current > capacity:
            raise SemanticGateClosed("META empty-beacon points are inconsistent")
        return current, capacity

    def click_meta_dossier_create(self) -> ActionReceipt:
        self._retry_transition_read(lambda: self.meta_dossier_empty_points(require_create=True))
        state = self.read_state()
        target = self._unique(state, 'meta/dossier/create')
        if (not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'meta/dossier/create')):
            raise SemanticGateClosed('META dossier create control is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META dossier create')
        self._tap(round(target.point.x), round(target.point.y))
        deadline = time.monotonic() + 12.0
        while True:
            after = self.read_state()
            if after.generation > state.generation and self.meta_dossier_detail_visible():
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META dossier create did not reach its detail postcondition')
            self._sleep(.2)
        return ActionReceipt(semantic_id='meta/dossier/create', generation=state.generation,
                             path=target.path, point=target.point, bounds=target.bounds)

    def click_meta_current_create(self) -> ActionReceipt:
        """Create a current beacon from the exact empty-beacon control."""

        self.meta_current_empty_points(require_create=True)
        state = self.read_state()
        target = self._unique(state, "meta/current/create")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/current/create")
        ):
            raise SemanticGateClosed("META beacon create control is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/current/create",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_current_list(self) -> ActionReceipt:
        """Open the exact current-beacon assist list without selecting combat."""

        state = self.read_state()
        target = self._unique(state, "meta/current/list")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/current/list")
        ):
            raise SemanticGateClosed("META assist list is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/current/list",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_assist_state(self) -> MetaAssistState:
        """Read the selected assist beacon and remaining daily attempts."""

        button_state = self.read_state()
        start = self._unique(button_state, "meta/assist/start")
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/"
        candidate_pattern = re.compile(
            r".*/" + re.escape(root) + r"list_panel/mask/bg/container/[1-9][0-9]*$"
        )
        candidates = tuple(
            button
            for button in button_state.buttons
            if candidate_pattern.fullmatch(button.path) is not None
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.point is not None
            and button.bounds is not None
        )
        if not (
            start.active_in_hierarchy
            and start.active_and_enabled
            and start.point is not None
            and start.bounds is not None
            and candidates
        ):
            raise SemanticGateClosed("META assist page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("META assist snapshots are not coherent")
        selected_pattern = re.compile(
            r".*/"
            + re.escape(root)
            + r"list_panel/mask/bg/container/([1-9][0-9]*)/selected(?:/.*)?$"
        )
        selected_indices = {
            int(match.group(1))
            for text in ui_state.texts
            if text.active_in_hierarchy
            and text.active_and_enabled
            and (match := selected_pattern.fullmatch(text.path)) is not None
        }
        if len(selected_indices) != 1:
            raise SemanticGateClosed("META selected assist candidate is ambiguous")

        def exact(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "META assist text is absent or ambiguous: " + path
                )
            return text_value(matches[0])

        def text_value(text: TextState) -> str:
            return re.sub(r"<[^>]*>", "", text.text).strip()

        attempts_match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact("point/Text"))
        hp_match = re.fullmatch(r"HP:([1-9][0-9]*)", exact("main/hp/Text"))
        level = exact("main/hp/level/Text")
        if (
            attempts_match is None
            or hp_match is None
            or re.fullmatch(r"[1-9][0-9]*", level) is None
        ):
            raise SemanticGateClosed("META assist summary is malformed")
        attempts, capacity = map(int, attempts_match.groups())
        selected_candidate_index = next(iter(selected_indices))
        candidate_indices = {int(candidate.name) for candidate in candidates}
        if attempts > capacity:
            raise SemanticGateClosed("META assist attempts are inconsistent")
        if selected_candidate_index not in candidate_indices:
            raise SemanticGateClosed("META selected assist candidate is inconsistent")
        return MetaAssistState(
            remaining_attempts=attempts,
            attempt_capacity=capacity,
            selected_level=int(level),
            selected_hp=int(hp_match.group(1)),
            candidate_count=len(candidates),
            selected_candidate_index=selected_candidate_index,
        )

    def click_meta_assist_next_candidate(
        self,
        *,
        expected_index: int,
        expected_level: int,
    ) -> ActionReceipt:
        """Select the next mounted assist candidate with exact stale-state guards."""

        if (
            isinstance(expected_index, bool)
            or not isinstance(expected_index, int)
            or expected_index < 1
            or isinstance(expected_level, bool)
            or not isinstance(expected_level, int)
            or expected_level < 1
        ):
            raise SemanticGateClosed("META assist candidate expectation is invalid")
        summary = self.meta_assist_state()
        if (
            summary.selected_candidate_index != expected_index
            or summary.selected_level != expected_level
        ):
            raise SemanticGateClosed("META assist candidate changed before selection")

        state = self.read_state()
        root = "WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/"
        candidate_pattern = re.compile(
            r".*/" + re.escape(root) + r"list_panel/mask/bg/container/([1-9][0-9]*)$"
        )
        candidates = []
        for button in state.buttons:
            match = candidate_pattern.fullmatch(button.path)
            if match is None or button.name != match.group(1):
                continue
            candidates.append((int(match.group(1)), button))
        candidates.sort(key=lambda item: item[0])
        indices = tuple(index for index, _button in candidates)
        if len(candidates) < 2 or expected_index not in indices:
            raise SemanticGateClosed("META next assist candidate is absent")
        selected_position = indices.index(expected_index)
        next_index, target = candidates[(selected_position + 1) % len(candidates)]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and 0 <= target.point.x < self.fingerprint.width
            and 0 <= target.point.y < self.fingerprint.height
            and not self._blocking_rules(state, "meta/assist/start")
        ):
            raise SemanticGateClosed("META next assist candidate is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before META candidate input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/assist/candidate/{0}".format(next_index),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_assist_start(self) -> ActionReceipt:
        """Start the currently proven META assist target."""

        summary = self.meta_assist_state()
        if summary.remaining_attempts < 1:
            raise SemanticGateClosed("META assist attempts are exhausted")
        state = self.read_state()
        target = self._unique(state, "meta/assist/start")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "meta/assist/start")
        ):
            raise SemanticGateClosed("META assist start is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/assist/start",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meta_assist_sortie_prompt_visible(self) -> bool:
        state = self.read_state()
        ui_state = self.read_ui_state()
        prompt = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip() == "保存当前编队并出击？"
        )
        return bool(
            len(prompt) == 1
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        )

    def click_meta_precombat_empty_vanguard(self) -> ActionReceipt:
        """Open one proven empty formation slot for task-scoped manual setup."""

        return self._click_meta_precombat_empty_slot('vanguard')

    def click_meta_precombat_empty_main(self, expected_vanguard_sprite: str) -> ActionReceipt:
        return self._click_meta_precombat_empty_slot('main', expected_vanguard_sprite)

    def _click_meta_precombat_empty_slot(self, role, expected_vanguard_sprite=None):
        if not self.daily_precombat_visible():
            raise SemanticGateClosed('META formation preparation is absent')
        state = self.read_state()
        semantic_id = 'meta/precombat/'+role+'/add'
        target = self._unique(state, semantic_id)
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('META formation frames are incoherent')
        root = 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/'
        dossier = [b for b in self._matches(state, 'meta/dossier/list')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if len(dossier) != 1:
            raise SemanticGateClosed('META dossier owner is absent or ambiguous behind preparation')
        for side in ('main', 'vanguard'):
            powers = [t for t in ui.texts if t.path == root+'adapt/middle/gear_score/'+side+'/Text'
                      and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            expected_empty = role == 'vanguard' or side == 'main'
            if (len(powers) != 1 or (expected_empty and powers[0].text.strip() != '0')
                    or (not expected_empty and re.fullmatch(r'[1-9][0-9]*', powers[0].text.strip()) is None)):
                raise SemanticGateClosed('META initial formation slots do not match the requested setup')
        if role == 'main':
            heroes = [i for i in ui.images if i.path.startswith(root+'adapt/middle/HeroContainer/')
                      and i.path.endswith('/'+str(expected_vanguard_sprite)+'_root/mouseChild')
                      and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
            if not expected_vanguard_sprite or len(heroes) != 1:
                raise SemanticGateClosed('META existing vanguard changed before main setup')
        images = [i for i in ui.images if i.path == target.path and i.active_in_hierarchy
                  and i.active_and_enabled and not i.truncated]
        if (len(images) != 1 or images[0].sprite != 'add_icon'
                or not target.active_in_hierarchy or not target.active_and_enabled
                or not target.interactable or target.raycast_top is not None
                or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or self._blocking_rules(state, semantic_id)):
            raise SemanticGateClosed('META empty vanguard slot is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before META formation input')
        receipt = self._click_exact_image(state, images[0], semantic_id)
        self._retry_transition_read(self._enhancement_dock_records)
        return receipt

    def meta_precombat_fleet_ready(self) -> bool:
        """Require non-zero main and vanguard power on the shared META formation."""

        if not self.daily_precombat_visible():
            return False
        ui_state = self.read_ui_state()

        def exact_power(side: str) -> Optional[int]:
            suffix = f"PreCombatUI(Clone)/adapt/middle/gear_score/{side}/Text"
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            return int(matches[0].text.strip()) if len(matches) == 1 else None

        main = exact_power("main")
        vanguard = exact_power("vanguard")
        return bool(main is not None and main > 0 and vanguard is not None and vanguard > 0)

    def click_meta_formation_ship(self, candidate, expected_sprite: str) -> ActionReceipt:
        """Select an immutable formation candidate without unrelated morale fields."""
        from .contracts import EnhancementDockCandidate
        if not isinstance(candidate, EnhancementDockCandidate) or not expected_sprite:
            raise TypeError('META formation candidate is invalid')
        current = self.enhancement_dock_candidates()
        matches = [c for c in current if (c.ship_id, c.ship_name, c.level) ==
                   (candidate.ship_id, candidate.ship_name, candidate.level)]
        if len(matches) != 1:
            raise SemanticGateClosed('META formation ship changed or became ambiguous')
        state, ui = self._enhancement_dock_records()
        target = matches[0].button
        controls = [b for b in state.buttons if b.path == target.path and b.name == target.name
                    and b.actionable and b.bounds == target.bounds]
        portraits = [i for i in ui.images if i.path == target.path+'/content/ship_icon'
                     and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        count_path = 'OverlayCamera/Overlay/UIMain/blur_panel/select_panel/bottom_info/bg_input/count'
        counts = [t for t in ui.texts if t.path == count_path and t.active_in_hierarchy
                  and t.active_and_enabled and not t.truncated]
        names = [t.text.strip() for t in ui.texts if t.path == target.path+'/content/info/name_mask/name'
                 and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        levels = [t.text.strip() for t in ui.texts if t.path == target.path+'/content/dockyard/lv/Text'
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if (len(controls) != 1 or len(portraits) != 1 or portraits[0].sprite != expected_sprite
                or names != [candidate.ship_name] or levels != [str(candidate.level)]
                or len(counts) != 1 or re.sub(r'<[^>]*>', '', counts[0].text).strip() != '0/1'):
            raise SemanticGateClosed('META formation ship or empty selection identity is incomplete')
        receipt = self._gems_equipment_click_button(state, controls[0], 'tactical/dock/ship', require_raycast_top=True)
        deadline = time.monotonic()+8.0
        while True:
            after = self.read_text_state()
            counts = [t for t in after.texts if t.path == count_path and t.active_in_hierarchy
                      and t.active_and_enabled and not t.truncated]
            if (after.generation > state.generation and len(counts) == 1
                    and re.sub(r'<[^>]*>', '', counts[0].text).strip() == '1/1'):
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META formation candidate did not reach one selected ship')
            self._sleep(.1)

    def meta_precombat_ship_visible(self, expected_sprite: str, role: str) -> bool:
        if role not in ('main', 'vanguard'):
            raise ValueError('META formation role is invalid')
        if not self.daily_precombat_visible():
            return False
        state = self.read_state()
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('META mounted formation frames are incoherent')
        root = 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/adapt/middle/'
        powers = [t for t in ui.texts if t.path == root+'gear_score/'+role+'/Text'
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        portraits = [i for i in ui.images if i.active_in_hierarchy and i.active_and_enabled
                     and not i.truncated and i.bounds is not None and (
                         (i.path.startswith(root+'HeroContainer/')
                          and i.path.endswith('/'+expected_sprite+'_root/mouseChild'))
                         or (i.path.startswith(root+'fleet/'+role+'/')
                             and i.path.endswith('/icon_bg/icon') and i.sprite == expected_sprite))]
        return (len(powers) == 1 and re.fullmatch(r'[1-9][0-9]*', powers[0].text.strip()) is not None
                and len(portraits) == 1)

    def confirm_meta_formation_ship(self, ship_id: int, expected_sprite: str, role: str) -> ActionReceipt:
        if role not in ('main', 'vanguard'):
            raise ValueError('META formation role is invalid')
        state, ui = self._enhancement_dock_records()
        prefix = 'UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/'
        root = prefix+str(ship_id)+'/content/'
        selected = [i for i in ui.images if i.path.startswith(prefix)
                    and i.path.endswith('/content/front/selected/text')
                    and i.active_in_hierarchy and i.active_and_enabled and not i.truncated
                    and i.sprite == 'status_select']
        portraits = [i for i in ui.images if i.path == root+'ship_icon'
                     and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        counts = [t for t in ui.texts if t.path == 'OverlayCamera/Overlay/UIMain/blur_panel/select_panel/bottom_info/bg_input/count'
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if (len(selected) != 1 or selected[0].path != root+'front/selected/text'
                or len(portraits) != 1 or portraits[0].sprite != expected_sprite
                or len(counts) != 1 or re.sub(r'<[^>]*>', '', counts[0].text).strip() != '1/1'):
            raise SemanticGateClosed('META selected formation ship is absent or ambiguous')
        receipt = self.click('tactical/dock/confirm')
        deadline = time.monotonic()+12.0
        while True:
            after = self.read_state()
            if after.generation > state.generation and self.meta_precombat_ship_visible(expected_sprite, role):
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed('META formation ship did not mount in the requested role')
            self._sleep(.1)

    def meta_simulation_prompt_visible(self) -> bool:
        """Recognize the optional Lv15 simulation prompt without accepting it."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        prompts = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        return bool(
            len(prompts) == 1
            and re.fullmatch(
                r"是否进入当前信标META的模拟战斗？\n战斗强度：Lv15\n"
                r"\*该战斗不消耗石油，不会获得任何奖励",
                prompts[0],
            )
            is not None
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        )

    def _meta_help_texts(self) -> Tuple[int, Mapping[str, TextState]]:
        ui_state = self.read_ui_state()
        expected = {
            "confirm": (
                "WorldBossHelpUI(Clone)/confirm_btn/Text",
                "确定",
            ),
            "cancel": (
                "WorldBossHelpUI(Clone)/cancel_btn/Text",
                "取消",
            ),
            "world": (
                "WorldBossHelpUI(Clone)/window/sliders/content/world/Text",
                "世界",
            ),
            "guild": (
                "WorldBossHelpUI(Clone)/window/sliders/content/guild/Text",
                "大舰队",
            ),
            "friend": (
                "WorldBossHelpUI(Clone)/window/sliders/content/friend/Text",
                "好友",
            ),
        }
        result: Dict[str, TextState] = {}
        for key, (suffix, value) in expected.items():
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and text.text.strip() == value
            )
            if len(matches) != 1:
                raise SemanticGateClosed("META help popup identity is absent")
            result[key] = matches[0]
        return ui_state.generation, result

    def meta_help_visible(self) -> bool:
        try:
            self._meta_help_texts()
            return True
        except SemanticGateClosed:
            return False

    def click_meta_help_control(self, control: str) -> ActionReceipt:
        generation, controls = self._meta_help_texts()
        if control not in ("confirm", "cancel", "world", "guild", "friend"):
            raise ValueError("unknown META help control")
        target = controls[control]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="meta/help/{0}".format(control),
            generation=generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_simulation_cancel(self) -> ActionReceipt:
        if not self.meta_simulation_prompt_visible():
            raise SemanticGateClosed("META simulation prompt is absent")
        state = self.read_state()
        target = self._unique(state, "os/exit/cancel")
        if not (
            target.actionable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("META simulation cancel is not actionable")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meta/simulation/cancel",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_meta_assist_sortie(self, confirm: bool) -> ActionReceipt:
        if not self.meta_assist_sortie_prompt_visible():
            raise SemanticGateClosed("META assist sortie prompt is absent")
        state = self.read_state()
        semantic_id = "os/exit/confirm" if confirm else "os/exit/cancel"
        target = self._unique(state, semantic_id)
        # This overlay's label Graphic is the top raycast target, so Unity
        # reports the owning Button itself as raycast_top=False.  The exact,
        # unique prompt and both exact choices above prove the modal identity;
        # retain every other Button actionability invariant here.
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top in (True, False)
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("META assist sortie choice is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=(
                "meta/assist/sortie/confirm" if confirm else "meta/assist/sortie/cancel"
            ),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
