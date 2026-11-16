import json
from pathlib import Path
from datetime import datetime
STORE=Path(__file__).with_name("positions.json");HIST=Path(__file__).with_name("trade_history.json")
def _read(p):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except:return []
def _write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding="utf-8")
def load_positions():return _read(STORE)
def save_position(x):
    xs=load_positions();x=dict(x);x["wkn"]=x["wkn"].upper();x["updated_at"]=datetime.now().isoformat(timespec="seconds")
    xs=[r for r in xs if r.get("wkn")!=x["wkn"]]+[x];_write(STORE,xs)
def delete_position(wkn):_write(STORE,[x for x in load_positions() if x.get("wkn")!=wkn])
def load_history():return _read(HIST)
def close_position(wkn,exit_price):
    xs=load_positions();x=next((r for r in xs if r.get("wkn")==wkn),None)
    if not x:return
    x=dict(x);x["exit_price"]=exit_price;x["closed_at"]=datetime.now().isoformat(timespec="seconds");x["pl_eur"]=(exit_price-x["certificate_entry"])*x["quantity"]
    h=load_history();h.append(x);_write(HIST,h);delete_position(wkn)
