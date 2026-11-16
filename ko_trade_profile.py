from dataclasses import dataclass
import math
import streamlit as st

@dataclass(frozen=True)
class KOProfile:
    investment: float = 1500.0
    leverage_min: float = 4.0
    leverage_max: float = 6.0
    ko_min: float = 17.0
    ko_max: float = 23.0
    stop_pct: float = 5.0
    max_stop_pct: float = 8.0
    target_pct: float = 10.0
    trail_step: float = 5.0
    max_spread: float = 1.5

def sidebar_profile():
    with st.sidebar.expander("KO-Handelsprofil",False):
        investment=st.number_input("Plan-Einsatz EUR",1000.0,2000.0,1500.0,100.0)
        lev_min=st.number_input("Hebel min.",1.0,20.0,4.0,.5)
        lev_max=st.number_input("Hebel max.",lev_min,30.0,6.0,.5)
        ko_min=st.number_input("KO-Abstand min. %",1.0,50.0,17.0,1.0)
        ko_max=st.number_input("KO-Abstand max. %",ko_min,80.0,23.0,1.0)
        stop=st.number_input("Standard-Stop %",1.0,20.0,5.0,.5)
        max_stop=st.number_input("Maximalverlust %",stop,30.0,8.0,.5)
        target=st.number_input("Gewinnziel %",2.0,50.0,10.0,1.0)
        trail=st.number_input("Trailing-Schritt %-Punkte",1.0,20.0,5.0,1.0)
        spread=st.number_input("Max. Spread %",.1,10.0,1.5,.1)
    return KOProfile(investment,lev_min,lev_max,ko_min,ko_max,stop,max_stop,target,trail,spread)

def trailing_stop_pct(perf,p):
    if perf<p.trail_step:return -p.stop_pct
    return math.floor(perf/p.trail_step)*p.trail_step-p.trail_step

def analyze(row,product,p):
    product=product or {}; blocks=[]; warnings=[]; positives=[]
    signal=str(row.get("Signal","")); grade=str(row.get("Grade","-"))
    if not any(x in signal for x in ("EARLY","CONFIRMED")):blocks.append("Kein EARLY-/CONFIRMED-Signal")
    if grade not in {"A+","A","B"}:blocks.append(f"Grade {grade} nicht ausreichend")
    if "SPÄT" in str(row.get("Entry Status","")):blocks.append("Entry bereits zu spät")
    lev=product.get("leverage"); ko=product.get("ko_distance_pct"); spread=product.get("spread_pct")
    if lev is None:warnings.append("Hebel fehlt")
    elif p.leverage_min<=float(lev)<=p.leverage_max:positives.append(f"Hebel {float(lev):.1f}x passend")
    else:blocks.append(f"Hebel {float(lev):.1f}x unpassend")
    if ko is None:warnings.append("KO-Abstand fehlt")
    elif p.ko_min<=float(ko)<=p.ko_max:positives.append(f"KO-Abstand {float(ko):.1f}% passend")
    else:blocks.append(f"KO-Abstand {float(ko):.1f}% unpassend")
    if spread is None:warnings.append("Spread fehlt")
    elif float(spread)<=p.max_spread:positives.append(f"Spread {float(spread):.2f}% okay")
    else:blocks.append(f"Spread {float(spread):.2f}% zu hoch")
    verdict="🔴 KEIN ENTRY" if blocks else "🟡 PRODUKT PRÜFEN" if warnings else "🟢 ENTRY FREIGEGEBEN"
    price=product.get("ask") or product.get("certificate_entry")
    qty=math.floor(p.investment/float(price)) if price else None
    invest=qty*float(price) if qty else p.investment
    return {"verdict":verdict,"blocks":blocks,"warnings":warnings,"positives":positives,"price":price,"qty":qty,"invest":invest}

def render(row,product,p):
    a=analyze(row,product,p);st.subheader("🧭 KO Entry Analyzer");st.markdown(f"### {a['verdict']}")
    c=st.columns(5);c[0].metric("Plan-Einsatz",f"{a['invest']:.0f} EUR");c[1].metric("Risiko -5%",f"-{a['invest']*p.stop_pct/100:.0f} EUR");c[2].metric("Max -8%",f"-{a['invest']*p.max_stop_pct/100:.0f} EUR");c[3].metric("Ziel +10%",f"+{a['invest']*p.target_pct/100:.0f} EUR");c[4].metric("Trailing",f"{p.trail_step:.0f} %-Punkte")
    if a['price']:
        d=st.columns(4);d[0].metric("Brief/Entry",f"{float(a['price']):.4f}");d[1].metric("Stück",a['qty']);d[2].metric("Stop",f"{float(a['price'])*(1-p.stop_pct/100):.4f}");d[3].metric("Ziel",f"{float(a['price'])*(1+p.target_pct/100):.4f}")
    if a['blocks']:st.error(" · ".join(a['blocks']))
    if a['warnings']:st.warning(" · ".join(a['warnings']))
    if a['positives']:st.success(" · ".join(a['positives']))
    st.caption("Trailing: +5% → Break-even, +10% → Stop +5%, +15% → Stop +10%.")
