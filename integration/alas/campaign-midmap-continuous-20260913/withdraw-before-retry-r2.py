from pathlib import Path
import os,sys,json,shutil,dataclasses
root=Path.cwd(); up=root/'artifacts/campaign-road-debug-20260913'
out=root/'integration/alas/campaign-midmap-continuous-20260913/withdraw-before-retry-r2.json'
name='semantic_midmap_cleanup_20260913'; cfg=up/'config'/f'{name}.json'
shutil.copyfile(up/'config/semantic_e2e.json',cfg)
sys.path[:0]=[str(root/'python'),str(up)]
os.environ.update(ALAS_SEMANTIC_MODE='1',ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44',ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET='0',ALAS_SEMANTIC_RETIREMENT_BUDGET='0')
os.chdir(up)
from module.campaign.run import CampaignRun
from module.exception import CampaignEnd
h=CampaignRun(name,task='Main'); h.config.override(Emulator_Serial='emulator-5554')
h.load_campaign('campaign_10_2',folder='campaign_main')
c=h.campaign;s=c.device.semantic_adapter;r={'passed':False}
try:
 s.begin_campaign_pre_sortie('10-2'); c.device.screenshot();o=s.open()._fresh_input_oracle()
 r['before_map']=o.campaign_is_in_map();r['before_state']=dataclasses.asdict(o.read_state());r['before_ui']=dataclasses.asdict(o.read_ui_state())
 assert r['before_map'],'Expected inherited map, no entry allowed'
 try:c.withdraw(skip_first_screenshot=False)
 except CampaignEnd as e:r['campaign_end']=str(e)
 c.device.screenshot();o=s.open()._fresh_input_oracle();r['chapter']=o.campaign_page_is_normal();r['oil_after']=o.campaign_oil();r['passed']=r['chapter']
except BaseException as e:r['error']=type(e).__name__+': '+str(e)
finally:
 s.close();cfg.unlink();out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in r.items() if k not in ('before_state','before_ui')},ensure_ascii=False))
