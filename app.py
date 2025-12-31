import streamlit as st
import pandas as pd
import yfinance as yf
from functools import lru_cache

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板（全手動分數版）", layout="wide")
st.title("📊 美股分析儀表板（政策 & 護城河 & 成長手動輸入版）")

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
# 護城河資料
# ==========================
COMPANY_MOAT_DATA = {
    # Mag7
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},
    # 資安
    "CRWD":{"retention":0.88,"switching":0.75,"patent":0.6,"network":0.8},
    "PANW":{"retention":0.85,"switching":0.7,"patent":0.65,"network":0.75},
    "ZS":{"retention":0.8,"switching":0.65,"patent":0.5,"network":0.7},
    "OKTA":{"retention":0.82,"switching":0.6,"patent":0.55,"network":0.65},
    "S":{"retention":0.78,"switching":0.55,"patent":0.5,"network":0.6},
    # 半導體
    "AMD":{"retention":0.8,"switching":0.7,"patent":0.6,"network":0.7},
    "INTC":{"retention":0.75,"switching":0.65,"patent":0.7,"network":0.6},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.9,"network":0.8},
    "AVGO":{"retention":0.85,"switching":0.8,"patent":0.85,"network":0.75},
    # 能源
    "CEG":{"retention":0.7,"switching":0.6,"patent":0.5,"network":0.6},
    "FLNC":{"retention":0.65,"switching":0.6,"patent":0.55,"network":0.65},
    "TE":{"retention":0.75,"switching":0.7,"patent":0.65,"network":0.7},
    "NEE":{"retention":0.8,"switching":0.75,"patent":0.7,"network":0.75},
    "ENPH":{"retention":0.78,"switching":0.7,"patent":0.65,"network":0.7},
    "EOSE":{"retention":0.7,"switching":0.65,"patent":0.6,"network":0.65},
    "VST":{"retention":0.75,"switching":0.7,"patent":0.65,"network":0.7},
    "PLUG":{"retention":0.72,"switching":0.65,"patent":0.6,"network":0.65},
    "OKLO":{"retention":0.7,"switching":0.6,"patent":0.55,"network":0.6},
    "SMR":{"retention":0.68,"switching":0.6,"patent":0.55,"network":0.6},
    "BE":{"retention":0.7,"switching":0.65,"patent":0.6,"network":0.65},
    "GEV":{"retention":0.72,"switching":0.66,"patent":0.6,"network":0.65},
    # NeoCloud
    "NBIS":{"retention":0.8,"switching":0.7,"patent":0.65,"network":0.7},
    "IREN":{"retention":0.75,"switching":0.7,"patent":0.6,"network":0.65},
    "CRWV":{"retention":0.78,"switching":0.72,"patent":0.65,"network":0.7},
    "APLD":{"retention":0.7,"switching":0.65,"patent":0.6,"network":0.65}
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)
WEIGHTS = {
    "穩健型":{"PE":0.25,"Forward_PE":0.15,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.15,"Forward_PE":0.25,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.2,"Forward_PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.1}
}

# =========================
# 快取財報函數
# =========================
@lru_cache(maxsize=128)
def get_info(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
    return data

# =========================
# 計算護城河
# =========================
def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    return round(sum(data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS)*100,2)

# =========================
# 計算分數
# =========================
def compute_scores(symbol, manual_scores, sector_avg_pe=None, sector_avg_forward_pe=None):
    data = get_info(symbol)
    PE, Forward_PE, ROE, FCF = data.get("PE"), data.get("Forward PE"), data.get("ROE"), data.get("FCF")
    
    PE_score = max(0, min(100, (sector_avg_pe/PE*100))) if PE and sector_avg_pe else 50
    Forward_PE_score = max(0, min(100, (sector_avg_forward_pe/Forward_PE*100))) if Forward_PE and sector_avg_forward_pe else 50
    ROE_score = min(max(ROE/0.3*100,0),100) if ROE else 50
    if FCF is not None and FCF<0:
        ROE_score *=0.8
    Policy_score = manual_scores.get("Policy_score",50)
    Moat_score = manual_scores.get("Moat_score", calculate_moat(symbol))
    Growth_score = manual_scores.get("Growth_score",50)
    
    w=WEIGHTS[style]
    Total_score=round(PE_score*w.get("PE",0)+Forward_PE_score*w.get("Forward_PE",0)+ROE_score*w.get("ROE",0)+
                      Policy_score*w.get("Policy",0)+Moat_score*w.get("Moat",0)+Growth_score*w.get("Growth",0),2)
    
    return {"PE_score":PE_score,"Forward_PE_score":Forward_PE_score,"ROE_score":ROE_score,
            "Policy_score":Policy_score,"Moat_score":Moat_score,"Growth_score":Growth_score,"Total_score":Total_score,
            **data}

# =========================
# 初始化 session_state
# =========================
for sector in SECTORS:
    for symbol in SECTORS[sector]:
        for key in ["policy","moat","growth"]:
            skey = f"{symbol}_{key}"
            if skey not in st.session_state:
                if key=="moat":
                    st.session_state[skey]=calculate_moat(symbol)
                else:
                    st.session_state[skey]=50

# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA").upper()
    st.subheader(f"📌 {symbol} 分析")
    
    manual_scores = {
        "Policy_score": st.number_input("政策分數",0,100,value=int(st.session_state.get(f"{symbol}_policy",50)),key=f"{symbol}_policy"),
        "Moat_score": st.number_input("護城河分數",0,100,value=int(st.session_state.get(f"{symbol}_moat",calculate_moat(symbol))),key=f"{symbol}_moat"),
        "Growth_score": st.number_input("成長分數",0,100,value=int(st.session_state.get(f"{symbol}_growth",50)),key=f"{symbol}_growth")
    }
    
    scores = compute_scores(symbol,manual_scores)
    st.metric("即時股價", f"${scores['股價']:.2f}")
    st.write(pd.DataFrame(scores.items(),columns=["指標","數值"]))
    st.metric("綜合分數", scores["Total_score"])
