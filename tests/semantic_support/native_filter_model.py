"""Independent native Dock multi-select model for filter semantics only. No device."""
import re
from types import SimpleNamespace as N
from alas_headless.oracle.enhancement import EnhancementOracle

ROOT='OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/'
OPENER='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button'
LABELS={'sort':{'1':'\u7b49\u7ea7','2':'\u7efc\u5408\u6027\u80fd'},'index':{'tpl':'\u5168\u90e8','3':'\u9a71\u9010','4':'\u8f7b\u5de1','5':'\u91cd\u5de1','6':'\u6218\u5217','7':'\u822a\u6bcd','8':'\u7ef4\u4fee','9':'\u6f5c\u8247','10':'\u5176\u4ed6'},'camp':{'tpl':'\u5168\u9635\u8425','1':'\u767d\u9e70'},'rarity':{'tpl':'\u5168\u90e8','3':'\u7cbe\u9510'},'extraindex':{'tpl':'\u65e0\u9650\u5236','3':'\u53ef\u5f3a\u5316','4':'\u53ef\u7a81\u7834'}}
class NativeMultiSelect:
 def __init__(self,selected):self.selected={k:set(v) for k,v in selected.items()};self.opened=False;self.generation=0;self.inputs=[]
 def _retirement_records(self):
  self.generation+=1;images=[N(path=OPENER,sprite='shaixuan_on',active_in_hierarchy=True,active_and_enabled=True,raycast_target=True,truncated=False,bounds=N())];texts=[]
  if self.opened:
   for group,options in LABELS.items():
    for option,label in options.items():
     path=ROOT+'container/indexsort_'+group+'/bg/'+option
     sprite=('btn_index_yellow' if group=='sort' else 'btn_index_blue') if option in self.selected[group] else 'btn_index_grey'
     images.append(N(name=option,path=path,sprite=sprite,active_in_hierarchy=True,active_and_enabled=True,raycast_target=True,truncated=False,bounds=N()))
     texts.append(N(path=path+'/Image',text=label,active_in_hierarchy=True,active_and_enabled=True,truncated=False,bounds=N()))
   path=ROOT+'btns/ok';images.append(N(path=path,sprite='btn_big_blue',active_in_hierarchy=True,active_and_enabled=True,raycast_target=True,truncated=False,bounds=N()));texts.append(N(path=path+'/Image',text='\u786e \u5b9a',active_in_hierarchy=True,active_and_enabled=True,truncated=False,bounds=N()))
  if self.opened:
   for group,option,sprite,truncated in getattr(self,'extra_options',()):
    path=ROOT+'container/indexsort_'+group+'/bg/'+option
    images.append(N(name=option,path=path,sprite=sprite,active_in_hierarchy=True,active_and_enabled=True,raycast_target=True,truncated=truncated,bounds=N()))
  return N(generation=self.generation),N(generation=self.generation,images=images,texts=texts,image_truncated=getattr(self,'unrelated_images_truncated',False),method_mask=15)
 def _enhancement_dock_records(self):return self._retirement_records()
 def _wait_enhancement_filter_option(self,group,option,label):
  state,ui=self._retirement_records();return state,ui,EnhancementOracle._enhancement_filter_option(ui,group,option,label)
 def _blocking_rules(self,*args):return ()
 def _sleep(self,*args):pass
 def _retry_transition_read(self,reader,**kwargs):return reader()
 def _click_exact_image(self,state,image,semantic_id):
  # UI actionability/package/freshness gates are separately tested; this
  # test double models only the independently observed native multi-select.
  self.inputs.append(semantic_id)
  if image.path==OPENER:self.opened=True
  elif image.path==ROOT+'btns/ok':self.opened=False
  else:
   match=re.search(r'indexsort_([^/]+)/bg/([^/]+)$',image.path);assert match
   group,option=match.groups()
   if option=='tpl' or group=='sort':self.selected[group]={option}
   else:self.selected[group].discard('tpl');self.selected[group].symmetric_difference_update({option})
  return N(semantic_id=semantic_id,path=image.path,generation=state.generation)
