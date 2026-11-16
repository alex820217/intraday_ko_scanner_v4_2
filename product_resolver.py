import re
from datetime import datetime,timezone
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote,urljoin
BASE="https://www.onvista.de";HEAD={"User-Agent":"Mozilla/5.0","Accept-Language":"de-DE"}
def _num(x):
    if not x:return None
    x=re.sub(r"[^0-9,.-]","",x)
    if "," in x:x=x.replace(".","").replace(",", ".")
    try:return float(x)
    except:return None
def _one(p,t):
    m=re.search(p,t,re.I|re.S);return m.group(1).strip() if m else None
def resolve_wkn(wkn):
    out={"wkn":wkn.upper(),"source_name":"Onvista","fetched_at":datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        s=requests.Session();s.headers.update(HEAD);r=s.get(f"{BASE}/suche/?searchValue={quote(wkn)}",timeout=20);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser")
        url=None
        for a in soup.select("a[href]"):
            if wkn.upper() in (a.get("href","")+a.get_text()).upper() and "/derivate/" in a.get("href",""):url=urljoin(BASE,a["href"]);break
        if not url:out["error"]="Produktseite nicht gefunden";return out
        r=s.get(url,timeout=20);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser");t=" ".join(soup.stripped_strings);out["source_url"]=url
        out.update({"isin":_one(r"ISIN\s+([A-Z]{2}[A-Z0-9]{10})",t),"issuer":_one(r"Emittent\s+(.+?)(?=\s+(?:Basiswert|Geld|Brief|WKN|ISIN))",t),"underlying":_one(r"Basiswert\s+(.+?)(?=\s+(?:Basispreis|K\.O\.|Hebel|Bezugsverhältnis))",t),"ko_level":_num(_one(r"(?:K\.O\.-?Schwelle|K\.O\.)\s+([0-9.,]+)",t)),"ratio":_num(_one(r"Bezugsverhältnis\s+([0-9.,]+)",t)),"leverage":_num(_one(r"Hebel\s+([0-9.,]+)",t)),"quote_timestamp":_one(r"(\d{2}\.\d{2}\.\d{4},\s*\d{2}:\d{2}:\d{2})",t)})
        out["direction"]="LONG" if re.search(r"\b(LONG|CALL)\b",t[:1200],re.I) else "SHORT" if re.search(r"\b(SHORT|PUT)\b",t[:1200],re.I) else None
        bm=re.search(r"Geld\s*[•·]?\s*([0-9.]+)\s*Stk\.?\s*([0-9.,]+)\s*(EUR|USD|GBP|GBp|CHF)",t,re.I);am=re.search(r"Brief\s*[•·]?\s*([0-9.]+)\s*Stk\.?\s*([0-9.,]+)\s*(EUR|USD|GBP|GBp|CHF)",t,re.I)
        if bm and am:
            out["bid"]=_num(bm.group(2));out["ask"]=_num(am.group(2));out["currency"]=bm.group(3);out["spread_pct"]=(out["ask"]-out["bid"])/out["bid"]*100
    except Exception as e:out["error"]=f"Produktabruf fehlgeschlagen: {type(e).__name__}"
    return out
def quote_age_minutes(*_):return None
def freshness_label(_):return "Quelle prüfen"
