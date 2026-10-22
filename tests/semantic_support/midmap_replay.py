"""Offline observer transport for retained full-dock scenes. Never opens ADB."""
import copy
import json
import contextlib
import time
from types import SimpleNamespace
from pathlib import Path

from alas_headless import AlasSemanticSession
from alas_headless.adapter import semantic_runtime_fingerprint_sha256
from .observer_fixtures import (FakeBackend, make_button, make_text, make_ui,
                                make_buttons, make_snapshot, make_image,
                                set_retirement_settings)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'com.bilibili.azurlane'
COMPONENT = PACKAGE + '/com.manjuu.azurlane.MainActivity'
REVISION = '506b76f698b5089aaa29c4e7908b48edb8532a44'


def retained_payload(path):
    value = json.loads((ROOT / path).read_text(encoding='utf-8'))
    if 'buttons_snapshot' in value['state']:
        return {'state': {'protocol_schema': 'alas-headless.observer/v1',
                          'status': 'ok', 'snapshot': value['state']['snapshot'],
                          'buttons': value['state']['buttons_snapshot']},
                'ui': value['ui']['snapshot']}
    return value


class ReplayRuntime:
    def __init__(self, payload):
        self.pid = 1948
        self.fingerprint_sha256 = semantic_runtime_fingerprint_sha256(
            package=PACKAGE, component=COMPONENT, driver_revision=REVISION,
            required_primary_abi='x86_64')
        self.generation = 100
        self.actions = []
        self.action_paths = []
        self.requests = []
        self.payload = copy.deepcopy(payload)
        self.on_input = None
        self.foreground = COMPONENT
        self.tick()

    def tick(self):
        self.generation += 1
        for part in (self.payload['state']['snapshot'], self.payload['state']['buttons'], self.payload['ui']):
            part.update(pid=self.pid, package=PACKAGE, driver_revision=REVISION,
                        generation=self.generation, age_ms=0)
            for key in ('snapshot_monotonic_ns', 'response_monotonic_ns'):
                part.pop(key, None)

    def observer_request(self, request):
        self.requests.append(request)
        if request == 'GET /v1/state\n':
            self.tick()
            return copy.deepcopy(self.payload['state'])
        if request == 'GET /v1/ui\n':
            return copy.deepcopy(self.payload['ui'])
        raise AssertionError('Unimplemented offline endpoint: ' + request)

    def foreground_component(self):
        return self.foreground

    def tap(self, x, y):
        self.actions.append((x, y))
        if self.on_input is None:
            raise AssertionError('Unexpected input during read-only replay')
        self.on_input(x, y)
        self.tick()

    def swipe(self, *args):
        raise AssertionError('Unexpected swipe during dock replay')

    def session(self):
        session = AlasSemanticSession(runtime_handle=self, driver_revision=REVISION,
                                      retirement_budget=1, campaign_combat_budget=4)
        session.begin_campaign_pre_sortie('10-2')
        session.refresh_frame()
        return session


def fixture_payload(buttons, texts=(), images=()):
    return {'state': {'protocol_schema': 'alas-headless.observer/v1', 'status': 'ok',
                      'snapshot': make_snapshot(), 'buttons': make_buttons(buttons)},
            'ui': make_ui(list(texts), images=list(images))}


class DockChainRuntime(ReplayRuntime):
    """Game-side simulation; missing captures are explicitly contract fixtures."""
    def __init__(self, *, delayed_equipment=False):
        self.phase = 'full'
        self.history = []
        self.delayed_equipment = delayed_equipment
        self.delay_reads = 0
        self.combat_frames = 0
        self.selection = retained_payload('integration/alas/campaign-midmap-continuous-20260913/blocked-r2.json')
        self.full = retained_payload('integration/alas/campaign-midmap-continuous-20260911/blocked-r1.json')
        self.precombat = retained_payload('tests/fixtures/midmap-retirement/precombat.json')
        self.map = retained_payload('tests/fixtures/midmap-retirement/map.json')
        super().__init__(self.full)
        self.on_input = self.advance_input

    def enter(self, phase):
        self.phase = phase
        self.history.append(phase)
        print('OFFLINE OBSERVER:', phase, flush=True)
        root = 'OverlayCamera/Overlay/UIMain/'
        if phase == 'selection' or phase == 'selection-after':
            self.payload = copy.deepcopy(self.selection)
            if phase == 'selection-after':
                for t in self.payload['ui']['texts']:
                    if t['path'].endswith('/capacity/Text'):
                        t['text'] = '851/930'
        elif phase == 'settings':
            b = FakeBackend([])
            set_retirement_settings(b, self.generation, keep_needed=True)
            self.payload = {'state': {'protocol_schema': 'alas-headless.observer/v1',
                            'status': 'ok', 'snapshot': b.snapshot, 'buttons': b.buttons}, 'ui': b.ui}
        elif phase == 'confirm':
            path = root + 'DestoryInfoUI(Clone)/frame/'
            self.payload = fixture_payload([make_button('confirm_button', path+'confirm_button')], [
                make_text('信息',path+'top/title_list/infomation/title'),
                make_text('确 定',path+'confirm_button/pic'),
                make_text('79',root+'blur_panel/select_panel/bottom_info/bg_input/count')])
        elif phase == 'rarity':
            path = root+'DestoryConfirmWindow(Clone)/window/'
            self.payload = fixture_payload([make_button('confirm_btn',path+'confirm_btn')], [
                make_text('是否确认',path+'content/desc/label'),
                make_text('选择角色中有<color=#92fc63>精锐以上</color>的角色：',path+'content/Text')])
        elif phase in ('reward', 'battle-award'):
            path=root+'AwardInfoUI(Clone)/items/'
            self.payload=fixture_payload([make_button('close',path+'close')], [
                make_text('物资',path+'items_scroll/content/item_tpl(Clone)/bg/name_mask/name'),
                make_text('1393',path+'items_scroll/content/item_tpl(Clone)/bg/icon_bg/count')])
            if phase=='battle-award':
                self.payload['ui']['texts'].append(make_text('胜利',
                    'UICamera/Canvas/UIOrigin/NewBattleResultEmptyUI(Clone)/result/title'))
                self.payload['ui']['text_count']=len(self.payload['ui']['texts'])
        elif phase in ('equipment', 'equipment-clear', 'equipment-delay'):
            path=root+'ResolveEquipmentUI(Clone)/main/'
            selected=phase!='equipment-clear'
            self.payload=fixture_payload([
                make_button('cancel_btn',path+'cancel_btn'),make_button('ALL',path+'options/ALL',500,500),
                *([make_button('reduce',path+'frame/view/content/0/frame/bg/selected/reduce',200,200)] if selected else [])], [
                make_text('请选择需要拆解的装备，未选的装备将放入仓库',path+'title/Text'),
                make_text('取 消',path+'cancel_btn/Image'),make_text('全部',path+'options/ALL/Label'),
                make_text('115',path+'frame/view/content/0/frame/bg/icon_bg/count')],
                [make_image(path+'options/ALL/Background/Checkmark','toggle_on')] if selected else [])
        elif phase=='preserve':
            path=root+'Msgbox(Clone)/window/'
            self.payload=fixture_payload([make_button('custom_button_1(Clone)',path+'button_container/custom_button_1(Clone)')], [
                make_text('不进行任何操作，所有装备会放入<color=#5f984d>仓库</color>\n是否退出？',path+'msg_panel/content')])
        elif phase=='precombat':
            self.payload=copy.deepcopy(self.precombat)
        elif phase=='combat':
            self.payload=fixture_payload([make_button('PauseBtn','UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn')])
        elif phase in ('result', 'statistics'):
            path=root+'NewBattleResultEmptyUI(Clone)/'+('NewBattleResultGradePage(Clone)'
                if phase=='result' else 'NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn')
            self.payload=fixture_payload([make_button('confirmBtn',path)])
        elif phase=='map':
            self.payload=copy.deepcopy(self.map)
        else:
            raise AssertionError('Unexpected simulation phase '+phase)
        self.tick()

    def advance_input(self,x,y):
        buttons=self.payload['state']['buttons']['buttons']
        hit=[b for b in buttons if b.get('adb_point') and
             (round(b['adb_point']['x']),round(b['adb_point']['y']))==(x,y)]
        top=[b for b in hit if b.get('raycast_top') is True]
        if top:
            hit=top
        assert len(hit)==1, ('Input must identify one observed button', self.phase, hit)
        path=hit[0]['path']
        self.action_paths.append({'phase':self.phase,'path':path})
        transitions={'full':'selection','settings':'selection','confirm':'rarity','rarity':'reward',
                     'reward':'equipment','equipment-clear':'preserve','preserve':'selection-after',
                     'selection-after':'precombat','precombat':'combat','result':'battle-award',
                     'statistics':'map','battle-award':'statistics'}
        if self.phase=='selection':
            # Bind simulation to the distinct observed input controls, never a
            # predetermined sequence that accepts any tap.
            if hit[0]['path'].endswith('/setting'):
                return self.enter('settings')
            assert hit[0]['path'].endswith('/quick_select'),hit
            return self.enter('confirm')
        if self.phase=='equipment':
            assert (x,y)==(500,500),'Only deselect-all is expected'
            return self.enter('equipment-delay' if self.delayed_equipment else 'equipment-clear')
        if self.phase=='precombat' and path.endswith('/adapt/top/back_btn'):
            return self.enter('map')
        assert self.phase in transitions,'Unexpected input at '+self.phase
        suffixes={'full':'/custom_button_1(Clone)','settings':'/btnBack','confirm':'/confirm_button',
                  'rarity':'/confirm_btn','reward':'/close','equipment-clear':'/cancel_btn',
                  'preserve':'/custom_button_1(Clone)','selection-after':'/back',
                  'precombat':'/adapt/right/start','result':'/NewBattleResultGradePage(Clone)',
                  'statistics':'/confirmBtn','battle-award':'/close'}
        assert path.endswith(suffixes[self.phase]), (self.phase,path)
        self.enter(transitions[self.phase])

    def observer_request(self,request):
        if self.phase=='equipment-delay' and request=='GET /v1/state\n':
            self.delay_reads+=1
            if self.delay_reads==3:
                self.enter('equipment-clear')
        return super().observer_request(request)


class ReplayDevice:
    def __init__(self, runtime, session):
        self.runtime=runtime
        self.semantic_adapter=session
        self.snapshots=0
        self.screenshot()

    @property
    def has_cached_image(self): return True

    def screenshot(self):
        self.snapshots+=1
        if self.snapshots>100:
            raise AssertionError('Original ALAS did not finish within 100 replay frames')
        if self.runtime.phase=='combat':
            self.runtime.combat_frames+=1
            if self.runtime.combat_frames==4:
                self.runtime.enter('result')
        self.runtime.tick()
        self.image=self.semantic_adapter.pixel_guard(self.semantic_adapter.refresh_frame())

    def click(self,button):
        return self.semantic_adapter.click(button)

    def sleep(self,delay):
        time.sleep(0.01)

    def stuck_record_add(self,*args): pass
    def stuck_record_clear(self): pass
    def click_record_clear(self): pass
    def screenshot_interval_set(self,*args): pass
