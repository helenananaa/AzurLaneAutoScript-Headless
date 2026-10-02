#include "../../overlays/angle-g3/src/libANGLE/renderer/null/NativeLuaGlobeProbe.h"
#include <cassert>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using namespace rx::alas;
struct Value {
  int type = 0, id = 0; double number = 0; std::string text;
  static Value table(int n) { return {5,n,0,{}}; }
  static Value function(int n) { return {6,n,0,{}}; }
  static Value numeric(double n) { return {3,0,n,{}}; }
  static Value string(const std::string &s) { return {4,0,0,s}; }
};
struct State {
  std::vector<Value> stack;
  std::vector<Value> registry;
  std::map<int,std::map<std::string,Value>> tables;
  std::map<int,std::vector<Value>> functions;
  double version = 501;
  Value at(int i) { return stack.at(i < 0 ? stack.size()+i : i-1); }
};
static State *versionState;
static State &s(void *p) { return *static_cast<State *>(p); }
static NativeLuaReadApi api() {
  return {
    +[](void *p) { return static_cast<int>(s(p).stack.size()); },
    +[](void *p,int n) { s(p).stack.resize(n); },
    +[](void *p,int i) { return s(p).at(i).type; },
    +[](void *p,const char *text) { s(p).stack.push_back(Value::string(text)); },
    +[](void *p,int i) { auto table=s(p).at(i); auto key=s(p).stack.back(); s(p).stack.pop_back();
      auto &entries=s(p).tables[table.id]; auto it=entries.find(key.text);
      s(p).stack.push_back(it == entries.end() ? Value{} : it->second); },
    +[](void *p) { s(p).stack.push_back({}); },
    +[](void *p,int i) {
      auto key=s(p).stack.back();
      if (i == -10000) {
        auto n=key.type == 0 ? size_t{0} : static_cast<size_t>(key.number);
        s(p).stack.pop_back(); if (n == s(p).registry.size()) return 0;
        s(p).stack.push_back(Value::numeric(n+1)); s(p).stack.push_back(s(p).registry[n]); return 1;
      }
      auto table=s(p).at(i); auto &entries=s(p).tables[table.id];
      auto it=key.type == 0 ? entries.begin() : entries.upper_bound(key.text);
      s(p).stack.pop_back(); if (it == entries.end()) return 0;
      s(p).stack.push_back(Value::string(it->first)); s(p).stack.push_back(it->second); return 1;
    },
    +[](void *p,int i) { return s(p).at(i).number; },
    +[](void *p,int i) { return static_cast<int>(s(p).at(i).number != 0); },
    +[](void *p,int i,size_t *len) { auto &stack=s(p).stack; auto &v=stack.at(i<0 ? stack.size()+i : i-1);
      *len=v.text.size(); return v.text.c_str(); },
    +[](void *p,int i,int n)->const char * { auto fn=s(p).at(i); auto &values=s(p).functions[fn.id];
      if (static_cast<size_t>(n)>values.size()) return nullptr;
      s(p).stack.push_back(values[n-1]); return "captured"; },
    +[](void *p,int i)->const void * { auto v=s(p).at(i);
      return reinterpret_cast<const void *>(static_cast<uintptr_t>(v.id*10+v.type)); },
    +[](void *,int) { return 1; },
    +[](void *)->const double * { return &versionState->version; },
  };
}
static State world() {
  State st; st.stack={Value::numeric(42)};
  st.registry={Value::function(1)}; st.functions[1]={Value::table(1),Value::table(2)};
  st.tables[1]={{"atlas",Value::table(10)}, {"inventoryProxy",Value::table(11)}, {"colorDic",Value::table(3)}};
  st.tables[2]={{"entranceTplDic",Value::table(12)}, {"dragTrigger",{7,20,0,{}}}, {"isDragging",{1,0,1,{}}}};
  st.tables[3]={{"00C8C8",Value::numeric(6)}, {"00C7C7",Value::numeric(77)}};
  return st;
}
static NativeLuaGlobeDiagnostic read(State &st, NativeLuaReadApi a=api(), NativeLuaUnityObjectApi objects={}) {
  versionState=&st; NativeLuaGlobeDiagnostic d;
  NativeLuaGlobeReader(a,&st,d,objects).read();
  assert(st.stack.size()==1 && st.stack[0].number==42);
  return d;
}
int main() {
  auto st=world(); auto d=read(st);
  assert(d.status==1 && d.stackBalanced && d.worldCandidates==1 && d.dragCandidates==1 && d.dragging[0]==1);
  assert(d.colorCount==2 && !d.truncated);
  assert(std::string(d.colors[0].hex.data())=="00C7C7" && d.colors[0].entrance==77);
  int identityCalls=0;
  NativeLuaUnityObjectApi objects{&identityCalls,+[](void *opaque,void *lua,int index)->int32_t {
    ++*static_cast<int *>(opaque);
    assert(s(lua).at(index).type==7);
    return -300-s(lua).at(index).id;
  }};
  st.tables[2]["cmPointer"]={7,21,0,{}};
  d=read(st,api(),objects);
  assert(d.dragPointerIds[0]==-321 && d.dragTriggerIds[0]==-320 && identityCalls==2);
  st.tables[2]["cmPointer"]=Value::table(21);
  identityCalls=0; d=read(st,api(),objects);
  assert(d.dragPointerIds[0]==0 && d.dragTriggerIds[0]==-320 && identityCalls==1);
  st.tables[2]["cmPointer"]={7,21,0,{}};
  d=read(st); assert(d.dragPointerIds[0]==0 && d.dragCandidates==1 && d.dragging[0]==1);
  NativeLuaUnityObjectApi unsupported{nullptr,+[](void *,void *,int)->int32_t { return 0; }};
  d=read(st,api(),unsupported); assert(d.dragPointerIds[0]==0 && d.dragTriggerIds[0]==0 && !d.truncated);
  NativeLuaUnityObjectApi unbalanced{nullptr,+[](void *,void *lua,int)->int32_t {
    s(lua).stack.push_back(Value::numeric(9)); return -321;
  }};
  d=read(st,api(),unbalanced); assert(d.dragPointerIds[0]==0 && d.truncated && d.stackBalanced);
  st=world();
  auto missing=api(); missing.rawGet=nullptr; d=read(st,missing); assert(d.status==2 && d.stage==1);
  st.version=503; d=read(st); assert(d.status==2 && d.stage==2); st.version=501;
  st.tables[3]["000000"]=Value::numeric(0); st.tables[3]["FFFFFF"]=Value::numeric(1.5);
  st.tables[3]["invalid"]=Value::numeric(6); d=read(st); assert(d.colorCount==2);
  st.tables[2]["isDragging"]=Value::string("true"); d=read(st); assert(d.dragCandidates==0);
  st.tables[1].erase("inventoryProxy"); d=read(st); assert(d.worldCandidates==0);
  st=world(); st.functions[1].push_back(Value::function(1)); d=read(st); assert(d.colorCount==2);
  st=world();
  st.tables[101]=st.tables[1]; st.tables[102]=st.tables[2];
  st.tables[1]={{"fields",Value::table(101)}};
  st.tables[2]={{"fields",Value::table(102)}};
  d=read(st); assert(d.worldCandidates==1 && d.dragCandidates==1 && d.colorCount==2 && d.stackBalanced);
  st.tables[101]["fields"]=Value::table(1); // Raw storage cycles remain bounded.
  d=read(st); assert(d.worldCandidates==1 && d.colorCount==2 && d.stackBalanced);
  st.registry.assign(4097,{}); d=read(st); assert(d.truncated && d.registryVisited==4096 && d.stackBalanced);
  st=world(); st.tables[3].clear();
  for (int n=1;n<=257;++n) { char key[7]; std::snprintf(key,sizeof(key),"%06X",n); st.tables[3][key]=Value::numeric(n); }
  d=read(st); assert(d.colorCount==256 && d.truncated && d.stackBalanced);
  st=world();
  for (int n=100;n<400;++n) st.registry.insert(st.registry.end()-1,Value::table(n));
  d=read(st); assert(d.worldCandidates==1 && d.dragCandidates==1 && d.colorCount==2 && !d.truncated);
  // Registry closures can retain the same candidate after the general walk
  // cache has evicted it. Count distinct candidate tables, not encounters.
  st=world();
  for (int n=100;n<400;++n) st.registry.push_back(Value::table(n));
  st.registry.push_back(Value::function(1));
  d=read(st); assert(d.worldCandidates==1 && d.dragCandidates==1 && d.colorCount==2 && d.stackBalanced);
  st=world(); st.tables[201]=st.tables[1]; st.tables[202]=st.tables[2];
  st.functions[1].push_back(Value::table(201)); st.functions[1].push_back(Value::table(202));
  d=read(st); assert(d.worldCandidates==2 && d.dragCandidates==2 && d.colorCount==4);
  st=world();
  for (int n=200;n<216;++n) { st.tables[n]=st.tables[2]; st.registry.push_back(Value::table(n)); }
  d=read(st); assert(d.dragCandidates==16 && d.truncated && d.stackBalanced);
  st=world(); st.registry.clear();
  for (int n=0;n<500;++n) {
    const int fn=100+n; st.registry.push_back(Value::function(fn));
    for (int k=0;k<16;++k) st.functions[fn].push_back(Value::table(10000+n*16+k));
  }
  d=read(st); assert(d.inspectionCount==8192 && d.registryVisited<500 && d.truncated && d.stackBalanced);
  st=world(); st.functions[1]={Value::table(100)};
  for (int n=100;n<105;++n) st.tables[n]["world"]=Value::table(n+1);
  d=read(st); assert(d.truncated && d.stackBalanced);
  std::cout << "Lua scalar reader: stack, ABI, raw identity, cycles, late registry and work limits passed\n";
}
