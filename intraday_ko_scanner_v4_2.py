import time as tm
from datetime import datetime,time
from zoneinfo import ZoneInfo
import math
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import ta,yfinance as yf
from market_universe import MARKET_GROUPS,BASISWERT_IDS,build_universe,asset_options,map_underlying
from product_resolver import resolve_wkn
from position_manager import load_positions,save_position,delete_position,close_position,load_history
from ko_trade_profile import sidebar_profile,render as render_ko,trailing_stop_pct

st.set_page_config(page_title="KO Market Radar V4.2",page_icon="📡",layout="wide")
st.markdown("""<style>.block-container{max-width:1500px;padding-top:2rem;padding-bottom:3rem}[data-testid=stMetric]{background:#fff;border:1px solid #e5e7eb;padding:12px;border-radius:14px;box-shadow:0 4px 14px #0f172a0c}div[data-testid=stDataFrame],[data-testid=stExpander]{border:1px solid #e5e7eb;border-radius:14px;overflow:hidden}.hint{padding:14px;border-radius:14px;background:#f8fafc;border:1px solid #e2e8f0}.search{padding:14px;border-radius:14px;background:#eef6ff;border:1px solid #cfe4ff}</style>""",unsafe_allow_html=True)
st.title("📡 KO Market Radar V4.2")
st.caption("60m Regime · 15m Bias · 5m Setup · 3m Trigger · KO Entry Analyzer")

MIN15,MIN5,MIN3=210,60,80

def ser(f,c):
    x=f[c];x=x.iloc[:,0] if isinstance(x,pd.DataFrame) else x
    return pd.to_numeric(x,errors="coerce")
@st.cache_data(ttl=300,show_spinner=False)
def dl(ticker,interval,period):
    d=yf.download(ticker,interval=interval,period=period,auto_adjust=True,prepost=False,progress=False,threads=False)
    if d.empty:return d
    out=pd.DataFrame(index=d.index)
    for c in ["Open","High","Low","Close","Volume"]:out[c]=ser(d,c)
    return out.dropna(subset=["Open","High","Low","Close"])
@st.cache_data(ttl=180,show_spinner=False)
def dl3(ticker):
    d=dl(ticker,"1m","7d")
    if d.empty:return d
    return d.resample("3min",origin="start_day",label="right",closed="right").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
def is_open(t):
    if t.endswith(".DE") or t in {"^GDAXI","^STOXX50E"}:
        n=datetime.now(ZoneInfo("Europe/Berlin"));return n.weekday()<5 and time(9)<=n.time()<time(17,30)
    if t.startswith("^") or t.isalpha():
        n=datetime.now(ZoneInfo("America/New_York"));return n.weekday()<5 and time(9,30)<=n.time()<time(16)
    return True
def ind(df):
    d=df.copy();c,h,l,v=d.Close,d.High,d.Low,d.Volume.fillna(0)
    for n in [9,20,50,200]:d[f"EMA{n}"]=ta.trend.EMAIndicator(c,n).ema_indicator()
    d["RSI"]=ta.momentum.RSIIndicator(c,14).rsi();d["ATR"]=ta.volatility.AverageTrueRange(h,l,c,14).average_true_range();d["ADX"]=ta.trend.ADXIndicator(h,l,c,14).adx();d["MACD"]=ta.trend.MACD(c).macd_diff()
    typ=(h+l+c)/3;dates=pd.Series(d.index.date,index=d.index);cv=v.groupby(dates).cumsum();d["VWAP"]=((typ*v).groupby(dates).cumsum()/cv.replace(0,np.nan)).fillna(d.EMA20)
    return d.dropna()
def regime60(raw15):
    h=raw15.resample("60min",origin="start_day",label="right",closed="right").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    h=ind(h.iloc[:-1]);
    if len(h)<3:return "NEUTRAL"
    r,p=h.iloc[-1],h.iloc[-2];L=sum([r.Close>r.EMA20,r.EMA20>r.EMA50,r.EMA20>p.EMA20,r.MACD>=0]);S=sum([r.Close<r.EMA20,r.EMA20<r.EMA50,r.EMA20<p.EMA20,r.MACD<=0])
    return "LONG" if L>=3 and L>S else "SHORT" if S>=3 and S>L else "NEUTRAL"
def bias15(d):
    r=d.iloc[-1];L=[r.Close>r.EMA20,r.EMA20>r.EMA50,r.EMA50>r.EMA200,r.ADX>=18,r.MACD>0];S=[r.Close<r.EMA20,r.EMA20<r.EMA50,r.EMA50<r.EMA200,r.ADX>=18,r.MACD<0]
    lc,sc=sum(L),sum(S);return ("LONG" if lc>=4 and lc>sc else "SHORT" if sc>=4 and sc>lc else None),lc,sc
def setup(d,side):
    r=d.iloc[-1];x=[r.Close>r.VWAP,r.EMA9>r.EMA20,r.RSI>50,r.MACD>0] if side=="LONG" else [r.Close<r.VWAP,r.EMA9<r.EMA20,r.RSI<50,r.MACD<0];return sum(x)
def trig(d,side):
    r,p=d.iloc[-1],d.iloc[-2];x=[r.Close>r.EMA9,r.EMA9>r.EMA20,r.RSI>52,r.Close>p.High] if side=="LONG" else [r.Close<r.EMA9,r.EMA9<r.EMA20,r.RSI<48,r.Close<p.Low];return sum(x)
def grade(signal,score,adx,dist,rsi_hot):
    issues=[]
    if adx<20:issues.append(f"ADX nur {adx:.1f}")
    if dist>.75:issues.append(f"Entry {dist:.2f} ATR von EMA20")
    if rsi_hot:issues.append("RSI bereits heiß")
    if "PRE" in signal:issues.append("Entry-Trigger noch nicht vollständig")
    if "WATCH" in signal:issues.append("Setup noch unvollständig")
    if not any(x in signal for x in ["EARLY","CONFIRMED","PRE"]):return "-","; ".join(issues) or "Kein handelbares Setup"
    g="A+" if score>=90 else "A" if score>=85 else "B" if score>=75 else "C" if score>=70 else "-"
    if issues and g in {"A+","A"}:g="B"
    if len(issues)>=2 and g=="B":g="C"
    return g,"; ".join(issues) or "A-Setup erfüllt"
def scan_one(m,spread_ok,event):
    raw15,raw5=dl(m["ticker"],"15m","30d"),dl(m["ticker"],"5m","5d")
    d15,d5=ind(raw15.iloc[:-1]),ind(raw5.iloc[:-1])
    if len(d15)<MIN15 or len(d5)<MIN5:raise ValueError(f"zu wenig Daten 15m={len(d15)} 5m={len(d5)}")
    reg=regime60(raw15);bias,lc,sc=bias15(d15);side=bias or ("LONG" if lc>=sc else "SHORT");s5=setup(d5,side);aligned=reg in {side,"NEUTRAL"}
    raw3=dl3(m["ticker"]) if bias and s5>=2 and aligned else pd.DataFrame();d3=ind(raw3.iloc[:-1]) if not raw3.empty else pd.DataFrame();has3=len(d3)>=MIN3;t3=trig(d3,side) if has3 else 0
    r=d5.iloc[-1];price=float(r.Close);atr=float(r.ATR);dist=abs(price-r.EMA20)/atr;hot=(side=="LONG" and r.RSI>68) or (side=="SHORT" and r.RSI<32);over=(side=="LONG" and r.RSI>72) or (side=="SHORT" and r.RSI<28)
    score=min(100,(lc if side=="LONG" else sc)*8+s5*7+t3*7);entry="🟢 OPTIMAL" if dist<=.75 else "🟡 AKZEPTABEL" if dist<=1 else "🔴 SPÄT"
    if not spread_ok or event:signal="⛔ NO TRADE"
    elif bias and reg not in {bias,"NEUTRAL"}:signal="⚠️ CONTEXT CONFLICT"
    elif over and s5>=3:signal="⛔ HOT ENTRY"
    elif dist>1 and s5>=3:signal="⛔ LATE ENTRY"
    elif bias and has3 and s5>=3 and t3>=3 and score>=80:signal=("🟢🟢 CONFIRMED " if score>=85 else "🟢 EARLY ")+side
    elif bias and s5>=3:signal="🟠 PRE-"+side
    elif bias:signal="🟡 WATCH "+side
    else:signal="⚪ WAIT"
    risk=1.2*atr;stop=price-risk if side=="LONG" else price+risk;tp1=price+1.8*risk if side=="LONG" else price-1.8*risk;tp2=price+2.8*risk if side=="LONG" else price-2.8*risk
    g,hint=grade(signal,score,float(r.ADX),dist,hot);isin=BASISWERT_IDS.get(m["ticker"],"");scq=f"{m['name']} {side} Knockout"
    row={"Asset":m["name"],"Ticker":m["ticker"],"Signal":signal,"Grade":g,"Score":score,"60m Regime":reg,"15m Bias":bias or "NEUTRAL","5m Setup":f"{s5}/4","3m Trigger":f"{t3}/4" if has3 else "FALLBACK","Entry Status":entry,"Setup-Hinweis":hint,"SC Suche":scq,"Basiswert ISIN":isin,"RSI":float(r.RSI),"ADX":float(r.ADX),"ATR %":atr/price*100,"Entry":price,"Stop":stop,"TP1":tp1,"TP2":tp2,"CRV":1.8,"Timestamp":d5.index[-1]}
    return row,d15,d5,d3 if has3 else d5

def candle(df,emas,bars,levels=None):
    d=df.tail(bars).reset_index();d=d.rename(columns={d.columns[0]:"Time"});d["Lo"]=d[["Open","Close"]].min(axis=1);d["Hi"]=d[["Open","Close"]].max(axis=1);d["Dir"]=np.where(d.Close>=d.Open,"Up","Down")
    lo,hi=d.Low.min(),d.High.max();pad=max((hi-lo)*.08,abs(d.Close.iloc[-1])*.001);dom=[lo-pad,hi+pad];x=alt.X("Time:T",axis=alt.Axis(title=None,format="%H:%M"));y=alt.Y("Low:Q",scale=alt.Scale(domain=dom,zero=False),axis=alt.Axis(title=None,format="~f"))
    layers=[alt.Chart(d).mark_rule().encode(x=x,y=y,y2="High:Q",color=alt.Color("Dir:N",scale=alt.Scale(domain=["Up","Down"],range=["#16a34a","#dc2626"]),legend=None)),alt.Chart(d).mark_bar(size=5).encode(x=x,y=alt.Y("Lo:Q",scale=alt.Scale(domain=dom,zero=False)),y2="Hi:Q",color=alt.Color("Dir:N",scale=alt.Scale(domain=["Up","Down"],range=["#22c55e","#ef4444"]),legend=None),tooltip=["Time:T","Open:Q","High:Q","Low:Q","Close:Q"])]
    colors={"EMA9":"#f59e0b","EMA20":"#2563eb","EMA50":"#8b5cf6","EMA200":"#dc2626","VWAP":"#0891b2"}
    for e in emas:
        if e in d:layers.append(alt.Chart(d).mark_line(color=colors[e],strokeWidth=1.5).encode(x=x,y=alt.Y(f"{e}:Q",scale=alt.Scale(domain=dom,zero=False))))
    if levels:
        for n,v,c in [("Entry",levels[0],"#111827"),("Stop",levels[1],"#dc2626"),("TP1",levels[2],"#16a34a"),("TP2",levels[3],"#059669")]:layers.append(alt.Chart(pd.DataFrame({"v":[v]})).mark_rule(color=c,strokeDash=[6,4]).encode(y=alt.Y("v:Q",scale=alt.Scale(domain=dom,zero=False))))
    st.altair_chart(alt.layer(*layers).properties(height=340).interactive(bind_y=False),use_container_width=True)

st.sidebar.header("Marktuniversum");groups=st.sidebar.multiselect("Marktgruppen",list(MARKET_GROUPS),default=list(MARKET_GROUPS));max_assets=st.sidebar.slider("Max. Assets",10,60,54,2);only_open=st.sidebar.checkbox("Geschlossene Cash-Märkte überspringen",True);spread_ok=st.sidebar.checkbox("KO-Spread manuell akzeptabel",True);event=st.sidebar.checkbox("Event-Risiko aktiv",False);top_n=st.sidebar.slider("Top Ergebnisse",5,30,15);profile=sidebar_profile()
if st.sidebar.button("Cache leeren und neu scannen"):st.cache_data.clear();st.rerun()
items=list(build_universe(groups).values())[:max_assets];skipped=[x for x in items if only_open and not is_open(x["ticker"])];items=[x for x in items if not(only_open and not is_open(x["ticker"]))]
rows=[];d15s={};d5s={};d3s={};errors=[];start=tm.time();prog=st.progress(0)
for i,m in enumerate(items,1):
    try:r,a,b,c=scan_one(m,spread_ok,event);rows.append(r);d15s[m["ticker"]]=a;d5s[m["ticker"]]=b;d3s[m["ticker"]]=c
    except Exception as e:errors.append({"Asset":m["name"],"Fehler":str(e)})
    prog.progress(i/max(1,len(items)))
prog.empty()
if not rows:st.error("Keine Assets auswertbar");st.stop()
scan=pd.DataFrame(rows);prio=lambda x:0 if "EARLY" in x or "CONFIRMED" in x else 1 if "PRE" in x else 2 if "WATCH" in x else 3;gr={"A+":0,"A":1,"B":2,"C":3,"-":9};scan["p"]=scan.Signal.map(prio);scan["g"]=scan.Grade.map(gr);scan=scan.sort_values(["p","g","Score","ADX"],ascending=[True,True,False,False]);trades=int(scan.Signal.str.contains("EARLY|CONFIRMED").sum());watch=int(scan.Signal.str.contains("PRE|WATCH").sum())
st.caption(f"**{trades} Trade** · {watch} PRE/WATCH · {len(rows)}/{len(items)} analysiert · {len(skipped)} übersprungen · {tm.time()-start:.1f}s")
st.header("🔥 Top Market Radar");cols=["Asset","Signal","Grade","Score","60m Regime","15m Bias","5m Setup","3m Trigger","Entry Status","Setup-Hinweis","SC Suche"];st.dataframe(scan.head(top_n)[cols],use_container_width=True,hide_index=True)
with st.expander("📊 Alle technischen Daten"):st.dataframe(scan.drop(columns=["p","g"]),use_container_width=True,hide_index=True)
with st.expander(f"Geschlossene Märkte ({len(skipped)})"):st.dataframe(pd.DataFrame(skipped),hide_index=True)
with st.expander(f"Nicht auswertbar ({len(errors)})"):st.dataframe(pd.DataFrame(errors),hide_index=True)
st.header("🎯 Setup-Details");selected=st.selectbox("Asset",scan.Asset.tolist());r=scan[scan.Asset==selected].iloc[0];c=st.columns(8)
for col,name,val in zip(c,["Signal","Grade","Score","60m","15m","5m","3m","Entry"],[r.Signal,r.Grade,int(r.Score),r["60m Regime"],r["15m Bias"],r["5m Setup"],r["3m Trigger"],r["Entry Status"]]):col.metric(name,val)
st.markdown(f"<div class='hint'><b>Setup-Hinweis</b><br>{r['Setup-Hinweis']}</div>",unsafe_allow_html=True);st.markdown(f"<div class='search'><b>Scalable Capital Suche</b><br><b>{r['SC Suche']}</b><br>Basiswert-ISIN: {r['Basiswert ISIN'] or '–'} · Ticker: {r.Ticker}</div>",unsafe_allow_html=True)
st.subheader("💰 Basiswert-Level");l=st.columns(5)
for col,name in zip(l,["Entry","Stop","TP1","TP2","CRV"]):col.metric(name,f"{r[name]:.4f}" if name!="CRV" else f"{r[name]:.2f}")
product=st.session_state.get("resolved_product");render_ko(r,product,profile)
st.subheader("📈 Chartanalyse");tabs=st.tabs(["3m Entry","5m Setup","15m Trend"]);levels=[r.Entry,r.Stop,r.TP1,r.TP2]
with tabs[0]:candle(d3s[r.Ticker],["EMA9","EMA20"],90,levels)
with tabs[1]:candle(d5s[r.Ticker],["EMA9","EMA20","VWAP"],90,levels)
with tabs[2]:candle(d15s[r.Ticker],["EMA20","EMA50","EMA200","VWAP"],80,levels)

st.divider();st.header("💼 KO-Produkt prüfen / Position erfassen")
with st.form("lookup"):
    a,b,c=st.columns(3);wkn=a.text_input("WKN",max_chars=6).upper();buy=b.number_input("Kaufpreis EUR",min_value=.0001,format="%.4f");qty=c.number_input("Stückzahl",min_value=1,step=1);go=st.form_submit_button("Produkt suchen")
if go:st.session_state["resolved_product"]=resolve_wkn(wkn);st.session_state["buy"]=buy;st.session_state["qty"]=qty;st.rerun()
product=st.session_state.get("resolved_product")
if product:
    st.subheader(f"Produkt {product.get('wkn')}");q=st.columns(5);q[0].metric("Geld",product.get("bid") or "–");q[1].metric("Brief",product.get("ask") or "–");q[2].metric("Spread %",f"{product.get('spread_pct'):.2f}" if product.get("spread_pct") is not None else "–");q[3].metric("Hebel",product.get("leverage") or "–");q[4].metric("KO-Level",product.get("ko_level") or "–")
    ticker=map_underlying(product.get("underlying"));cur=next((x for x in scan.to_dict("records") if x["Ticker"]==ticker),None)
    if cur:
        current=float(cur["Entry"]);ko=product.get("ko_level");product["ko_distance_pct"]=abs(current-float(ko))/current*100 if ko else None;render_ko(pd.Series(cur),product,profile)
        if st.button("Position speichern"):
            save_position({"wkn":product["wkn"],"asset":cur["Asset"],"ticker":ticker,"direction":product.get("direction"),"ko_level":ko,"leverage":product.get("leverage"),"spread_pct":product.get("spread_pct"),"certificate_entry":st.session_state["buy"],"certificate_current":product.get("bid") or st.session_state["buy"],"quantity":st.session_state["qty"],"quote_source":product.get("source_name"),"quote_timestamp":product.get("quote_timestamp")});st.success("Gespeichert")
    else:st.warning("Basiswert konnte nicht automatisch dem Radar zugeordnet werden.")

positions=load_positions();st.subheader(f"Offene Positionen ({len(positions)})")
for pos in positions:
    with st.container(border=True):
        st.write(f"**{pos['wkn']} · {pos['asset']} · {pos.get('direction')}**");entry=float(pos['certificate_entry']);current=float(pos.get('certificate_current') or entry);perf=(current/entry-1)*100;trail=trailing_stop_pct(perf,profile);x=st.columns(5);x[0].metric("Kauf",f"{entry:.4f}");x[1].metric("Aktuell",f"{current:.4f}");x[2].metric("P/L %",f"{perf:+.2f}");x[3].metric("Trailing",f"{trail:+.0f}%");x[4].metric("P/L EUR",f"{(current-entry)*pos['quantity']:+.2f}")
        if st.button("Position löschen",key="del"+pos["wkn"]):delete_position(pos["wkn"]);st.rerun()
st.warning("Technische Entscheidungshilfe. Keine automatische Order. Spread, Emittent, KO-Barriere, Handelszeit und Ereignisrisiko vor jeder manuellen Order prüfen.")
