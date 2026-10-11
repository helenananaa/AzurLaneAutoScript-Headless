#include "../../overlays/angle-g3/src/libANGLE/renderer/null/NativeLuaShipyardProbe.h"
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
  Value at(int i) { if(i == -10002) return Value::table(0); return stack.at(i < 0 ? stack.size()+i : i-1); }
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
      auto it=key.type == 0 ? entries.begin() : entries.upper_bound(key.type == 3 ? std::to_string(static_cast<int>(key.number)) : key.text);
      s(p).stack.pop_back(); if (it == entries.end()) return 0;
      s(p).stack.push_back(it->first.find_first_not_of("0123456789") == std::string::npos ? Value::numeric(std::stoi(it->first)) : Value::string(it->first)); s(p).stack.push_back(it->second); return 1;
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

static State sample() {
  State st; st.stack={Value::numeric(42)};
  auto t=Value::table; auto n=Value::numeric;
  st.tables[0]={{"pg",t(1)},{"ShipRarity",t(22)}};
  st.tables[1]={{"m02",t(2)},{"base",t(16)}};
  st.tables[2]={{"view",t(3)},{"model",t(9)}};
  st.tables[3]={{"mediatorMap",t(4)}};
  st.tables[4]={{"ShipBluePrintMediator",t(5)}};
  st.tables[5]={{"viewComponent",t(6)}};
  st.tables[6]={{"contextData",t(7)},{"filterBlueprintVOs",t(23)}};
  st.tables[7]={{"shipBluePrintVO",t(8)}};
  st.tables[8]={{"id",n(29901)},{"shipId",n(123)},{"level",n(17)},{"fateLevel",n(-1)},{"exp",n(12)}};
  st.tables[9]={{"proxyMap",t(10)}};
  st.tables[10]={{"TechnologyProxy",t(11)},{"PlayerProxy",t(14)}};
  st.tables[11]={{"bluePrintData",t(12)},{"pursuingTimes",n(3)},{"pursuingTimesUR",n(7)}};
  st.tables[12]={{"29901",t(13)}}; st.tables[13]=st.tables[8];
  st.tables[14]={{"data",t(15)}};st.tables[15]={{"gold",n(12000)}};
  st.tables[16]={{"ship_data_blueprint",t(17)},{"ship_data_statistics",t(19)}};
  st.tables[17]={{"29901",t(18)}};st.tables[18]={{"blueprint_version",n(12)},{"is_pursuing",n(1)}};
  st.tables[19]={{"299011",t(20)}};st.tables[20]={{"rarity",n(5)}};
  st.tables[22]={{"SSR",n(6)}};st.tables[23]={{"1",t(8)}};
  return st;
}
static NativeLuaShipyardState read(State &st) {
  versionState=&st;NativeLuaShipyardState out;NativeLuaShipyardReader(api(),&st,out).read();
  assert(st.stack.size()==1 && st.stack[0].number==42);return out;
}
int main() {
  auto st=sample();auto d=read(st);
  assert(d.status==1 && d.stackBalanced && d.series==12 && d.shipIndex==1 && d.rarity==1 && d.purchased==3 && d.coins==12000);
  assert(!d.gemsKnown); // Older snapshots still serve navigation and purchases.
  st.tables[15]["chargeGem"]=Value::numeric(5);st.tables[15]["awardGem"]=Value::numeric(12);
  d=read(st);assert(d.status==1 && d.gemsKnown && d.paidGems==5 && d.freeGems==12);
  st.tables[15]["chargeGem"]=Value::numeric(-1);d=read(st);assert(d.status==1 && !d.gemsKnown);
  st.tables[20]["rarity"]=Value::numeric(6);d=read(st);assert(d.status==1 && d.rarity==2 && d.purchased==7);
  st.tables[13]["exp"]=Value::numeric(13);assert(read(st).status==2);
  st=sample();st.tables[23]["2"]=Value::table(8);assert(read(st).status==2);
  st=sample();st.tables[23]["2"]=Value::table(24);st.tables[24]={{"id",Value::numeric(-1)}};
  assert(read(st).status==1);
  st=sample();st.tables[18]["blueprint_version"]=Value::numeric(99);assert(read(st).series==99);
  st.tables[18]["is_pursuing"]=Value::numeric(0);d=read(st);assert(d.status==1 && !d.pursuing);
  st=sample();st.tables[11].erase("pursuingTimes");assert(read(st).status==2);
  st=sample();st.tables[15]["gold"]=Value::numeric(-1);assert(read(st).status==2);
  st=sample();st.tables[17].clear();assert(read(st).status==2);
  st=sample();st.tables[4].clear();assert(read(st).status==2);
  std::cout << "native Lua shipyard reader passed\n";
}
