import importlib.util
from dataclasses import make_dataclass
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


def test_task_copy_uses_native_run_count_contract_and_keeps_recovery():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('configured_task_copy',
        root / 'scripts/python/run_alas_configured_task_live.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    seed = {
        'Main2': {'Scheduler': {'Enable': True}, 'StopCondition': {'RunCount': 0}},
        'Hard': {'Scheduler': {'Enable': True}},
        'Alas': {'Error': {'HandleError': True, 'SaveError': True, 'OnePushConfig': 'provider'}},
    }
    config, override = runner.prepare_config(seed, 'Main2', 1)
    assert config['Alas']['Error'] == {'HandleError': True, 'SaveError': False, 'OnePushConfig': ''}
    assert override == {'original': 0, 'qualification': 1}
    assert config['Main2']['StopCondition']['RunCount'] == 1
    assert seed['Main2']['StopCondition']['RunCount'] == 0
    assert seed['Alas']['Error']['SaveError'] is True
    with pytest.raises(ValueError, match='Hard uses its native daily quota'):
        runner.prepare_config(seed, 'Hard', 1)
    assert runner.prepare_config(seed, 'Hard', None)[1] is None
    seed['Alas']['Error']['HandleError'] = False
    assert runner.prepare_config(seed, 'Hard', None)[0]['Alas']['Error']['HandleError'] is False


def test_action_budget_parameters_use_runtime_grant_registry():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('configured_budget_runner',
        root / 'scripts/python/run_alas_configured_task_live.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from alas_headless.adapter.legacy_environment import LEGACY_BOOLEAN_GRANTS, LEGACY_BUDGET_GRANTS

    values = runner.parse_action_budgets([f'{key}=1' for key in
        (*LEGACY_BUDGET_GRANTS, *LEGACY_BOOLEAN_GRANTS)])
    assert set(values) == set(LEGACY_BUDGET_GRANTS) | set(LEGACY_BOOLEAN_GRANTS)
    assert runner.parse_action_budgets(['ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET=8']) == {
        'ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET': '8'}
    for item in ('ALAS_SEMANTIC_COMMISSION_CLAIM_BUDGET=8',
                 'ALAS_SEMANTIC_ADB=1',
                 'ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET=-1',
                 'ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE=2'):
        with pytest.raises(ValueError):
            runner.parse_action_budgets([item])


@pytest.mark.parametrize('failure', ['close', 'initialize', 'action-observation', 'native-task-end'])
@pytest.mark.parametrize('run_limit', [None, 1])
@pytest.mark.parametrize('expected_surface', ['main', 'campaign', 'globe', 'opsi', 'fushun-prepare'])
def test_real_runner_keeps_receipt_and_removes_temp_config(monkeypatch,tmp_path,failure,run_limit,expected_surface):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('configured_task_runner',
        root/'scripts/python/run_alas_configured_task_live.py')
    runner = importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    runtime=tmp_path/'runtime';(runtime/'config').mkdir(parents=True)
    (runtime/'config'/'seed.json').write_text(json.dumps({
        'Main':{'Scheduler':{'Enable':True,'NextRun':'later'}, 'StopCondition':{'RunCount':0}},
        'Alas':{'Emulator':{'Serial':'test-device'},'Error':{}}}),encoding='utf-8')
    output=tmp_path/'receipt.json'
    state=SimpleNamespace(snapshot={'pid':7},generation=12)
    reads=0
    def read_state(*, check_foreground=True):
        nonlocal reads
        reads+=1
        if failure=='action-observation' and reads>1:
            raise RuntimeError('observer disconnected')
        return state
    def click(target):
        raise ValueError('original action rejected')
    oracle=SimpleNamespace(read_state=read_state,main_page_visible=lambda:True,
        new_year_challenge_ticket_count=lambda:(0,40),
        campaign_page_is_normal=lambda:True,operation_siren_globe_visible=lambda:failure!='native-end-unknown-surface',
        click=click,exists=lambda _:False,
        click_operation_siren_globe_port=lambda *a:None,
        click_operation_siren_globe_map=lambda *a:None,
        operation_siren_globe_unpin=lambda *a:None,operation_siren_globe_swipe=lambda *a:None)
    def close():
        if failure=='close':raise RuntimeError('forward removal failed')
    session=SimpleNamespace(open=lambda:SimpleNamespace(oracle=oracle),close=close, appear=lambda _: False,
        operation_siren_map_visible=lambda:False,
        last_task_outcome={'outcome':'raised' if failure=='native-task-end' else 'returned'})
    DockReceipt = make_dataclass('DockReceipt', [('retired_count', int)])
    session.enhancement_receipts = lambda: ()
    session.retirement_receipt = lambda: DockReceipt(9)
    def run(command):
        if failure=='close':
            oracle.read_state(check_foreground=False)
        if failure=='action-observation':oracle.click('main/battle')
        if failure=='runtime-restart':
            fresh_oracle = SimpleNamespace(**vars(oracle))
            fresh_oracle.read_state = lambda: SimpleNamespace(snapshot={'pid':8},generation=25)
            session.open = lambda: SimpleNamespace(oracle=fresh_oracle)
            oracle.read_state = lambda: (_ for _ in ()).throw(RuntimeError('old process identity'))
        return True
    app=SimpleNamespace(config=SimpleNamespace(bind=lambda task:None),
        device=SimpleNamespace(semantic_adapter=session),main=lambda:None,run=run)
    def initialize(name):
        temporary_config=json.loads((runtime/'config'/(name+'.json')).read_text(encoding='utf-8'))
        assert temporary_config['Main']['StopCondition']['RunCount']==(run_limit or 0)
        if failure=='initialize':raise RuntimeError('configuration construction failed')
        return app
    alas=ModuleType('alas');alas.AzurLaneAutoScript=initialize
    config=ModuleType('module.config.config');config.name_to_function=lambda task:task
    monkeypatch.setitem(sys.modules,'alas',alas)
    monkeypatch.setitem(sys.modules,'module.config.config',config)
    monkeypatch.chdir(root)
    argv=['runner','--alas-root',str(runtime),
        '--seed-config','seed','--task','Main','--driver-revision','test','--output',str(output),
        '--expected-surface',expected_surface]
    if run_limit is not None: argv += ['--run-limit',str(run_limit)]
    monkeypatch.setattr(sys,'argv',argv)
    code=runner.main();result=json.loads(output.read_text(encoding='utf-8'))
    if failure != 'initialize':
        assert result['enhancement_receipts'] == []
        assert result['retirement_receipt'] == {'retired_count': 9}
    assert result['temporary_config_removed'] and not list((runtime/'config').glob('_codex*'))
    assert json.loads((runtime/'config'/'seed.json').read_text(encoding='utf-8'))['Main']['StopCondition']['RunCount']==0
    if run_limit is not None:
        assert result['run_limit_override']=={'original':0,'qualification':run_limit}
    if failure=='close':
        assert code==0 and result['passed']
        assert result['cleanup_errors'][0]['operation']=='session.close'
    elif failure=='runtime-restart':
        assert code==0 and result['passed'] and result['runtime_oracle_changed']
        assert result['before']['pid']==7 and result['after']['pid']==8
    elif failure=='native-end-unknown-surface':
        assert code==1 and not result['passed'] and result['return'] is True
        assert not result['after']['os_map_visible'] and not result['after']['os_globe_visible']
    elif failure=='native-task-end':
        assert code==0 and result['passed'] and result['task_outcome']['outcome']=='raised'
    else:
        assert code==1 and not result['passed']
        if failure=='action-observation':
            assert result['error']['type']=='ValueError'
            assert result['failed_target']=='main/battle'
            assert result['failed_observation_error']['message']=='observer disconnected'
        else:assert result['error']['message']=='configuration construction failed'


def test_native_end_on_unknown_page_is_not_accepted_as_opsi(monkeypatch,tmp_path):
    test_real_runner_keeps_receipt_and_removes_temp_config(monkeypatch,tmp_path,
        'native-end-unknown-surface',None,'opsi')


def test_real_runner_rebinds_to_restarted_process_for_final_observation(monkeypatch,tmp_path):
    test_real_runner_keeps_receipt_and_removes_temp_config(monkeypatch,tmp_path,
        'runtime-restart',None,'main')
