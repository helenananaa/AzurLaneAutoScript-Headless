import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless.kvm_local_dev import LocalKvm
from alas_headless.runtime_command import RuntimeCommandResult, RuntimeOwnedProcess
from alas_headless.runtime_backends import RuntimeBackendNotReady, RuntimeIdentityMismatch


@pytest.fixture
def manager(tmp_path):
    value = {'schema':'alas-headless.runtime-config/v1','backend':'kvm',
             'package':'com.bilibili.azurlane',
             'component':'com.bilibili.azurlane/com.manjuu.azurlane.MainActivity',
             'host_class':'linux-x86_64-kvm','adb_server_port':5043,
             'launch_game':False,'manage_angle_routing':False}
    release = tmp_path/'runtime/releases/sample'
    for key, suffix in [('emulator','emulator/emulator'),('emulator_check','emulator/emulator-check'),
                        ('adb','sdk/platform-tools/adb'),('sdk_root','sdk')]:
        value[key] = str(release/suffix)
    value.update(runtime_release_root=str(release),avd_home=str(tmp_path/'runtime/avd'),
                 avd_name='sample',console_port=5660,serial='127.0.0.1:5661')
    path = tmp_path/'runtime.json'
    path.write_text(json.dumps(value))
    return LocalKvm(path,tmp_path/'domain.json',tmp_path/'profile.json')


def owned(manager, pid='123'):
    return {'MainPID':pid,'ActiveState':'active' if pid!='0' else 'inactive','Result':'success',
            'ExecMainStatus':'0','Environment':shlex.quote(f'ALAS_KVM_CONFIG={manager.path}')}


@pytest.mark.parametrize('uuid',['7febc493-864e-4e35-a01c-3090515de95e','wrong-root-filesystem'])
def test_local_vhd_mount_is_required_before_control_files(manager,monkeypatch,uuid):
    monkeypatch.setattr(manager,'command',lambda *a,**kw:SimpleNamespace(stdout=uuid))
    if uuid=='wrong-root-filesystem':
        with pytest.raises(RuntimeError,match='not mounted'):
            manager.require_runtime_mount()
    else:
        manager.require_runtime_mount()
    assert not manager.control.exists()


class Executor:
    def __init__(self, name='sample', sync_code=0, exit_code=0):
        self.calls=[]
        self.name,self.sync_code,self.exit_code=name,sync_code,exit_code
        self.stopped=[]

    def run(self, spec):
        self.calls.append(spec)
        text=self.name+'\r\nOK\r\n' if spec.label=='kvm-console-identity' else ''
        code=self.sync_code if spec.label=='kvm-userdata-sync' else 0
        return RuntimeCommandResult(spec.label,code,text,'',1)

    def stop_owned(self, process, timeout_seconds):
        self.stopped.append(process)
        return self.exit_code


def test_console_stop_uses_verified_emulator_alias_and_syncs_first(manager):
    executor=Executor()
    manager.backend.executor=executor
    manager.backend.request_emulator_stop()
    assert [c.label for c in executor.calls]==['kvm-console-identity','adb-connect','kvm-userdata-sync','emulator-stop']
    assert executor.calls[0].argv[-5:]==('-s','emulator-5660','emu','avd','name')
    assert executor.calls[-1].argv[-4:]==('-s','emulator-5660','emu','kill')
    assert executor.calls[2].argv[-2:]==('shell','sync')


@pytest.mark.parametrize('name,sync_code,error', [('other-avd',0,RuntimeIdentityMismatch),('sample',1,RuntimeBackendNotReady)])
def test_wrong_console_or_failed_sync_never_dispatches_kill(manager,name,sync_code,error):
    executor=Executor(name,sync_code)
    manager.backend.executor=executor
    with pytest.raises(error):
        manager.backend.request_emulator_stop()
    assert not any(c.label=='emulator-stop' for c in executor.calls)


def test_forced_exit_is_not_reported_as_graceful(manager):
    executor=Executor(exit_code=-9)
    manager.backend.executor=executor
    manager.backend._owned_processes['run']=RuntimeOwnedProcess('run',42,'test')
    with pytest.raises(RuntimeBackendNotReady,match='abnormal-exit'):
        manager.backend.stop({'instance_id':'run'})
    assert executor.stopped[0].pid==42


def test_native_login_status_does_not_consume_stale_unity_state(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    monkeypatch.setattr(manager,'adb',lambda *args,**kwargs:SimpleNamespace(stdout='device' if args[0]=='get-state' else ('1' if args[0]=='shell' else 'List of devices attached\n'),stderr='',returncode=0))
    class Bridge:
        def __init__(self,*args,**kwargs): pass
        def foreground_component(self): return manager.config.package+'/com.gsc.phone_login.PhoneLoginActivity'
        def open(self): pytest.fail('native login must not query Unity')
        def close(self): pass
    monkeypatch.setattr('alas_headless.kvm_local_dev.AdbObserverBridge',Bridge)
    assert manager.status()['state']=='login-required'


def test_repeated_start_is_idempotent_and_foreign_service_is_rejected(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    monkeypatch.setattr(manager,'status',lambda:{'state':'login-required'})
    monkeypatch.setattr(manager,'command',lambda *a,**kw:pytest.fail('must not relaunch'))
    assert manager.start()=={'state':'login-required'}
    monkeypatch.setattr(manager,'service',lambda:{**owned(manager),'Environment':'ALAS_KVM_CONFIG=/other.json'})
    with pytest.raises(RuntimeError,match='different runtime'):
        manager.stop()


def test_stop_preserves_adb_server_when_other_devices_use_it(manager,monkeypatch):
    states=iter([owned(manager),owned(manager,'0')])
    monkeypatch.setattr(manager,'service',lambda:next(states))
    monkeypatch.setattr(manager.backend,'request_emulator_stop',lambda:None)
    calls=[]
    def adb(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0,stdout='List of devices attached\nother-device\tdevice\n')
    monkeypatch.setattr(manager,'adb',adb)
    assert manager.stop()['exit_code']==0
    assert not any(c[0]=='kill-server' for c in calls)


@pytest.mark.parametrize('damage',[None,'stale','wrong-pid','truncated'])
def test_status_rejects_bad_frames_but_tolerates_additive_metadata(manager,monkeypatch,damage):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    monkeypatch.setattr(manager,'adb',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='device' if a[0]=='get-state' else '1',stderr=''))
    shared={'protocol_schema':'alas-headless.observer/v1','status':'ok',
            'package':manager.config.package,'pid':55,'generation':12,'age_ms':20}
    value={**shared,'snapshot':{**shared,'flags':15,'main_thread':True,'ui_stage':100,'ui_method_mask':15},
           'buttons':{**shared,'truncated':False,'error_count':0},'future_metadata':{'compatible':True}}
    if damage=='stale': value['snapshot']['age_ms']=4000
    if damage=='wrong-pid': value['buttons']['pid']=56
    if damage=='truncated': value['buttons']['truncated']=True
    class Bridge:
        pid=55
        def __init__(self,*a,**kw): pass
        def foreground_component(self): return manager.config.component
        def open(self): pass
        def request(self,*a): return value
        def close(self): pass
    monkeypatch.setattr('alas_headless.kvm_local_dev.AdbObserverBridge',Bridge)
    assert manager.status()['state']==('semantic-ready' if damage is None else 'observer-not-ready')


def test_failed_start_is_reported_without_contacting_adb(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:{**owned(manager,'0'),'ActiveState':'failed','Result':'exit-code','ExecMainStatus':'1'})
    monkeypatch.setattr(manager,'adb',lambda *a,**kw:pytest.fail('failed service needs no ADB query'))
    state=manager.status()
    assert state['state']=='failed' and not state['running']
    assert state['journal_unit']==manager.unit


def test_missing_transport_is_not_misreported_as_android_starting(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    calls=[]
    def adb(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1 if args[0]=='get-state' else 0,
                               stdout='List of devices attached\n' if args[0]=='devices' else '',
                               stderr='device not found' if args[0]=='get-state' else '')
    monkeypatch.setattr(manager,'adb',adb)
    state=manager.status()
    assert state['state']=='adb-disconnected' and state['recovery']=='Reconnect'
    assert [c[0] for c in calls]==['devices','get-state']


def test_reconnect_keeps_vm_and_never_launches_game(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    calls=[]
    monkeypatch.setattr(manager.backend,'wait_adb',lambda instance,timeout:calls.append((instance,timeout)))
    monkeypatch.setattr(manager.backend,'restart_game',lambda *a:pytest.fail('connection repair must not restart game'))
    monkeypatch.setattr(manager,'status',lambda:{'running':True,'state':'login-required'})
    result=manager.reconnect()
    assert result['recovery']=='adb-reconnected' and result['game_restart_requested'] is False
    assert len(calls)==1


def test_repeated_start_repairs_only_missing_connection(manager,monkeypatch):
    monkeypatch.setattr(manager,'service',lambda:owned(manager))
    monkeypatch.setattr(manager,'status',lambda:{'state':'adb-disconnected'})
    monkeypatch.setattr(manager,'reconnect',lambda:{'state':'login-required','game_restart_requested':False})
    assert manager.start()['game_restart_requested'] is False


def test_backend_readiness_stops_waiting_when_service_exits(manager,monkeypatch):
    manager.backend.executor=Executor()
    monkeypatch.setattr(manager,'service',lambda:{**owned(manager,'0'),'Result':'exit-code','ExecMainStatus':'1'})
    monkeypatch.setattr('alas_headless.kvm_local_dev.time.sleep',lambda *a:pytest.fail('must not sleep after service failure'))
    with pytest.raises(RuntimeError,match='not running'):
        manager.backend.wait_adb({'instance_id':manager.unit},180)


@pytest.mark.parametrize('failed',[True,False])
def test_failed_readiness_cleanup_never_touches_running_vm(manager,monkeypatch,failed):
    state={**owned(manager,'0'),'ActiveState':'failed'} if failed else owned(manager)
    monkeypatch.setattr(manager,'service',lambda:state)
    calls=[]
    monkeypatch.setattr(manager,'adb',lambda *a,**kw:calls.append(a[0]))
    monkeypatch.setattr(manager,'close_unused_adb_server',lambda:calls.append('cleanup'))
    manager.cleanup_failed_service_adb()
    assert calls==(['disconnect','cleanup'] if failed else [])


@pytest.mark.parametrize('service_only', [False, True])
def test_status_cli_service_only_skips_guest_but_preserves_failure(manager, monkeypatch, capsys, service_only):
    from alas_headless import kvm_local_dev
    monkeypatch.setattr(kvm_local_dev, 'LocalKvm', lambda *args: manager)
    monkeypatch.setattr(kvm_local_dev.os, 'getuid', lambda: 1000, raising=False)
    monkeypatch.setattr(manager, 'service', lambda: owned(manager))
    calls = []
    def adb(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout='', stderr='offline')
    monkeypatch.setattr(manager, 'adb', adb)
    argv = ['status', '--config', str(manager.path)]
    if service_only:
        argv.append('--service-only')
    assert kvm_local_dev.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == ('starting' if service_only else 'adb-disconnected')
    assert bool(calls) is not service_only
    monkeypatch.setattr(manager, 'service', lambda: {
        **owned(manager, '0'), 'ActiveState': 'failed', 'Result': 'exit-code', 'ExecMainStatus': '1'})
    assert kvm_local_dev.main(argv) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'failed'


def test_android_only_ready_still_waits_for_backend_readiness(manager, monkeypatch):
    monkeypatch.setattr(manager, 'service', lambda: owned(manager))
    calls = []
    monkeypatch.setattr(manager.backend, 'wait_adb', lambda *a: calls.append('adb'))
    def android(*args):
        calls.append('android-network')
        return {'timings_seconds': {'android_framework_seconds': 2, 'android_network_seconds': 3}}
    monkeypatch.setattr(manager.backend, 'wait_android_ready', android)
    monkeypatch.setattr(manager.backend, 'restart_game', lambda *a: pytest.fail('Android-only must not launch'))
    monkeypatch.setattr(manager, 'status', lambda: {'state': 'android-ready'})
    result = manager.ready(launch_game=False)
    assert calls == ['adb', 'android-network']
    assert result['timings_seconds']['android_network_seconds'] == 3
    def not_ready(*args):
        raise RuntimeBackendNotReady('kvm-network-provisioning-ready-timeout')
    monkeypatch.setattr(manager.backend, 'wait_android_ready', not_ready)
    with pytest.raises(RuntimeBackendNotReady, match='network-provisioning'):
        manager.ready(launch_game=False)
