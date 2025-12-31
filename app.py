import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（手動分數 + 行業動態PE/ROE + Forward PE/PEG加權）")

# =========================
# 產業股票池（Mag7 移除 TSLA）
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],  # TSLA移除
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

# =========================
# 護城河資料
# =========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7}
}
MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)
WEIGHTS = {
    "穩健型":{"PE":0.25,"Forward PE":0.15,"PEG":0.1,"ROE":0.25,"Policy":0.1,"Moat":0.15,"Growth":0.0},
    "成長型":{"PE":0.1,"Forward PE":0.2,"PEG":0.15,"ROE":0.15,"Policy":0.2,"Moat":0.05,"Growth":0.15},
    "平衡型":{"PE":0.15,"Forward PE":0.15,"PEG":0.15,"ROE":0.2,"Policy":0.15,"Moat":0.1,"Growth":0.1}
}

# =========================
# 快取工具函數
# =========================
@st.cache_data
def get_price(symbol):
    info=yf.Ticker(symbol).info
    return info.get("currentPrice"), info.get("regularMarketChangePercent")

@st.cache_data
def get_fundamentals(symbol):
    info=yf.Ticker(symbol).info
    data={
        "股價":info.get("currentPrice"),
        "PE":info.get("trailingPE"),
        "Forward PE":info.get("forwardPE"),
        "EPS":info.get("trailingEps"),
        "Forward EPS": info.get("forwardEps"),
        "ROE":info.get("returnOnEquity"),
        "市值":info.get("marketCap"),
        "FCF":info.get("freeCashflow")
    }
    return pd.DataFrame(data.items(),columns=["指標","數值"])

def format_large_numbers(value):
    if isinstance(value,(int,float)) and value is not None:
        if value>=1e9:
            return f"{value/1e9:.2f} B"
        elif value>=1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def calculate_peg(pe, eps_growth):
    if pe is None or eps_growth is None or eps_growth==0:
        return "-"
    return round(pe/eps_growth,2)

def compute_scores(row,manual_scores=None,sector_avg_pe=None,sector_avg_roe=None):
    symbol=row["股票"]
    PE=row.get("PE")
    Forward_PE=row.get("Forward PE")
    EPS=row.get("EPS")
    Forward_EPS=row.get("Forward EPS")
    ROE=row.get("ROE")
    FCF=row.get("FCF")

    # 計算 PEG
    PEG_val = calculate_peg(Forward_PE, Forward_EPS)
    
    # PE score
    PE_score = 50
    if PE is not None and sector_avg_pe is not None:
        PE_score = max(0,min(100,(sector_avg_pe - PE)/sector_avg_pe*100))
    Forward_PE_score = 50
    if Forward_PE is not None and sector_avg_pe is not None:
        Forward_PE_score = max(0,min(100,(sector_avg_pe - Forward_PE)/sector_avg_pe*100))
    PEG_score = 50
    if PEG_val != "-":
        PEG_score = max(0,min(100,(sector_avg_pe - Forward_PE)/sector_avg_pe*100))
    
    # ROE score
    ROE_score = 50
    if ROE is not None and sector_avg_roe is not None:
        ROE_score = min(max(ROE / sector_avg_roe *100,0),100)
    # ROE質量校正
    if FCF is not None and isinstance(FCF,(int,float)) and FCF<0:
        ROE_score *=0.8

    Policy_score = 50
    Moat_score = calculate_moat(symbol)
    Growth_score = 50
    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score",Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score",Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score",Growth_score)
    
    w=WEIGHTS[style]
    Total_score=round(
        PE_score*w.get("PE",0)+Forward_PE_score*w.get("Forward PE",0)+
        PEG_score*w.get("PEG",0)+ROE_score*w.get("ROE",0)+
        Policy_score*w.get("Policy",0)+Moat_score*w.get("Moat",0)+
        Growth_score*w.get("Growth",0),
        2
    )
    
    return PE_score,Forward_PE_score,PEG_score,ROE_score,Policy_score,Moat_score,Growth_score,Total_score

# =========================
# 初始化 session_state
# =========================
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = 50
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = 50

# =========================
# 後續單一股票分析與產業共同比較程式碼與原版相同
# 可以直接沿用你原有邏輯，僅呼叫 compute_scores 會得到 Forward PE/PEG 加權+ROE校正
