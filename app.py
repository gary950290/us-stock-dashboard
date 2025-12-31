import streamlit as st
import pandas as pd
import yfinance as yf
from functools import lru_cache
import numpy as np

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板（手動分數版）", layout="wide")
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
mode = st.sidebar.selectbox("選擇模式", ["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格", ["穩健型","成長型","平衡型"], index=2)
WEIGHTS = {
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1}
}

# =========================
# 快取財報與股價
# =========================
@st.cache_data(ttl=3600)
def get_ticker_info(symbol):
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        info = {}
    return info

# =========================
# 工具函數
# =========================
def get_price(symbol):
    info = get_ticker_info(symbol)
    price = info.get("currentPrice")
    change = info.get("regularMarketChangePercent")
    return price, change

def get_fundamentals(symbol):
    info = get_ticker_info(symbol)
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
    for k in data:
        if isinstance(data[k], float):
            data[k] = round(data[k], 4)
    return pd.DataFrame(data.items(), columns=["指標","數值"])

def format_large_numbers(value):
    if isinstance(value,(int,float)) and value is not None:
        if value>=1e9:
            return f"{value/1e9:.2f} B"
        elif value>=1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def format_df(df, decimals=2):
    display_df = df.copy()
    float_cols = display_df.select_dtypes(include=["float","float64"]).columns
    display_df[float_cols] = display_df[float_cols].round(decimals)
    return display_df

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score = sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def compute_scores(row, manual_scores=None):
    def safe_float(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    PE = safe_float(row.get("PE"))
    ROE = safe_float(row.get("ROE"))
    FCF = safe_float(row.get("FCF"))

    PE_score = 50 if PE is None else max(0, min(100, (50-PE)/(50-15)*100))
    ROE_score = 50 if ROE is None else min(max(ROE/0.3*100,0),100)
    if FCF is not None and FCF <0:
        ROE_score *= 0.8

    symbol = row["股票"]

    # 手動分數
    Policy_score = 50
    Moat_score = calculate_moat(symbol)
    Growth_score = 50

    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score", Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score", Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score", Growth_score)

    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w["PE"] + ROE_score*w["ROE"] + Policy_score*w["Policy"] + Moat_score*w["Moat"] + Growth_score*w["Growth"], 2
    )
    return PE_score, ROE_score, Policy_score, Moat_score, Growth_score, Total_score

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
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA").upper()
    st.subheader(f"📌 {symbol} 分析")
    price, change = get_price(symbol)
    if price:
        st.metric("即時股價", f"${price:.2f}", f"{change:.2f}%")
    df_fund = get_fundamentals(symbol)
    for col in ["FCF","市值"]:
        if col in df_fund["指標"].values:
            df_fund.loc[df_fund["指標"]==col,"數值"] = df_fund.loc[df_fund["指標"]==col,"數值"].apply(format_large_numbers)
    st.table(df_fund)

    # 手動輸入分數
    st.subheader("手動輸入分數")
    manual_policy = st.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    manual_moat = st.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    manual_growth = st.number_input("成長分數", 0, 100, key=f"{symbol}_growth")

    PE_val = df_fund.loc[df_fund["指標"]=="PE","數值"].values[0]
    ROE_val = df_fund.loc[df_fund["指標"]=="ROE","數值"].values[0]
    FCF_val = df_fund.loc[df_fund["指標"]=="FCF","數值"].values[0] if "FCF" in df_fund["指標"].values else None

    PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_scores(
        {"股票":symbol, "PE":PE_val, "ROE":ROE_val, "FCF":FCF_val},
        manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}
    )

    st.metric("政策分數", Policy_s)
    st.metric("護城河分數", Moat_s)
    st.metric("成長分數", Growth_s)
    st.metric("綜合分數", Total_s)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業比較")

    manual_scores = {}
    for symbol in SECTORS[sector]:
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數", 0, 100, key=f"{symbol}_policy")
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數", 0, 100, key=f"{symbol}_moat")
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數", 0, 100, key=f"{symbol}_growth")
        manual_scores[symbol] = {
            "Policy_score": st.session_state[f"{symbol}_policy"],
            "Moat_score": st.session_state[f"{symbol}_moat"],
            "Growth_score": st.session_state[f"{symbol}_growth"]
        }

    rows=[]
    for symbol in SECTORS[sector]:
        try:
            df = get_fundamentals(symbol)
            row = {"股票":symbol}
            for _, r in df.iterrows():
                row[r["指標"]] = r["數值"]
            PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_scores(row, manual_scores)
            row["PE_score"] = round(PE_s,2)
            row["ROE_score"] = round(ROE_s,2)
            row["Policy_score"] = round(Policy_s,2)
            row["Moat_score"] = round(Moat_s,2)
            row["Growth_score"] = round(Growth_s,2)
            row["綜合分數"] = round(Total_s,2)
            for col in ["FCF","市值"]:
                if col in row:
                    row[col] = format_large_numbers(row[col])
            rows.append(row)
        except:
            continue
    if rows:
        result_df = pd.DataFrame(rows)
        result_df = format_df(result_df)
        result_df = result_df.sort_values("綜合分數", ascending=False)
        st.dataframe(result_df, use_container_width=True)

# =========================
# 評分公式說明
# =========================
with st.expander("📘 評分依據與公式"):
    st.markdown("""
    **各因子計算方式**：
    - **PE_score (估值)**：PE 越低越好，行業合理區間 15~50，線性映射 0~100
    - **ROE_score (盈利能力)**：ROE 越高越好，30% ROE 為滿分，線性映射 0~100；若自由現金流為負，扣 20%
    - **Policy_score (政策)**：完全手動輸入，可保留輸入值
    - **Moat_score (護城河)**：續約率、轉換成本、專利、網路效應加權計算 0~100，可手動調整
    - **Growth_score (成長潛力)**：完全手動輸入，可保留輸入值
    - **綜合分數** = 加權總分，依投資風格調整權重
    """)
