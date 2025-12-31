import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="美股分析儀表板（進階評分版）", layout="wide")
st.title("📊 美股分析儀表板（行業相對 × 現金流校正）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

# =========================
# 投資風格權重
# =========================
STYLE_WEIGHTS = {
    "穩健型":{"Valuation":0.35,"Quality":0.35,"Policy":0.15,"Moat":0.15},
    "平衡型":{"Valuation":0.3,"Quality":0.3,"Policy":0.2,"Moat":0.2},
    "成長型":{"Valuation":0.25,"Quality":0.25,"Policy":0.25,"Moat":0.25},
}

# =========================
# Sidebar
# =========================
st.sidebar.header("⚙️ 設定")
mode = st.sidebar.selectbox("分析模式", ["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格", list(STYLE_WEIGHTS.keys()), index=1)
policy_alpha = st.sidebar.slider("2026 政策風險係數", 0.8, 1.2, 1.0, 0.05)

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=3600)
def get_info(symbol):
    try:
        return yf.Ticker(symbol).info or {}
    except:
        return {}

def safe(v):
    return np.nan if v in [None, "None"] else v

def get_fundamentals(symbol):
    info = get_info(symbol)
    return {
        "Price": safe(info.get("currentPrice")),
        "PE": safe(info.get("trailingPE")),
        "FPE": safe(info.get("forwardPE")),
        "ROE": safe(info.get("returnOnEquity")),
        "FCF": safe(info.get("freeCashflow")),
        "MarketCap": safe(info.get("marketCap")),
        "NetDebt": safe(info.get("totalDebt",0)) - safe(info.get("cash",0)),
        "EBITDA": safe(info.get("ebitda"))
    }

def sector_avg_pe(sector):
    pes=[]
    for s in SECTORS[sector]:
        pe = safe(get_info(s).get("trailingPE"))
        if isinstance(pe,(int,float)) and pe>0:
            pes.append(pe)
    return np.mean(pes) if pes else np.nan

# =========================
# 評分核心
# =========================
def valuation_score(pe, fpe, sector_pe):
    if np.isnan(pe) or np.isnan(sector_pe):
        return 50
    relative = pe / sector_pe
    base = np.clip((1.5 - relative) * 100, 0, 100)
    if isinstance(fpe,(int,float)) and fpe>0:
        base = base*0.4 + np.clip((1.5 - fpe/sector_pe)*100,0,100)*0.6
    return round(base,2)

def quality_score(roe, fcf, mcap, netdebt, ebitda):
    if not isinstance(roe,(int,float)):
        return 50
    score = np.clip(roe/0.25*100,0,100)
    if not isinstance(fcf,(int,float)) or fcf<=0:
        score *= 0.8
    if isinstance(netdebt,(int,float)) and isinstance(ebitda,(int,float)) and ebitda>0:
        if netdebt/ebitda > 3:
            score *= 0.8
    return round(score,2)

# =========================
# Session State 初始化
# =========================
for sector in SECTORS.values():
    for s in sector:
        st.session_state.setdefault(f"{s}_policy",50)
        st.session_state.setdefault(f"{s}_moat",50)

# =========================
# 主畫面
# =========================
def render(symbol, sector):
    f = get_fundamentals(symbol)
    v = valuation_score(f["PE"],f["FPE"],sector_avg_pe(sector))
    q = quality_score(f["ROE"],f["FCF"],f["MarketCap"],f["NetDebt"],f["EBITDA"])
    w = STYLE_WEIGHTS[style]
    total = (
        v*w["Valuation"] +
        q*w["Quality"] +
        st.session_state[f"{symbol}_policy"]*w["Policy"] +
        st.session_state[f"{symbol}_moat"]*w["Moat"]
    ) * policy_alpha
    return round(total,2), v, q

if mode=="產業共同比較":
    sector = st.selectbox("選擇產業", SECTORS.keys())
    rows=[]
    for s in SECTORS[sector]:
        st.sidebar.number_input(f"{s} 政策分數",0,100,key=f"{s}_policy")
        st.sidebar.number_input(f"{s} 護城河分數",0,100,key=f"{s}_moat")
        total,v,q = render(s,sector)
        rows.append({
            "股票":s,
            "估值分":v,
            "品質分":q,
            "政策":st.session_state[f"{s}_policy"],
            "護城河":st.session_state[f"{s}_moat"],
            "總分":total
        })
    df=pd.DataFrame(rows).sort_values("總分",ascending=False)
    st.dataframe(df,use_container_width=True)

else:
    symbol=st.text_input("股票代碼","NVDA")
    sector = next((k for k,v in SECTORS.items() if symbol in v),"Mag7")
    st.number_input("政策分數",0,100,key=f"{symbol}_policy")
    st.number_input("護城河分數",0,100,key=f"{symbol}_moat")
    total,v,q = render(symbol,sector)
    st.metric("估值分",v)
    st.metric("品質分",q)
    st.metric("總分",total)
