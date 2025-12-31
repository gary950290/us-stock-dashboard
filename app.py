import streamlit as st
import pandas as pd
import yfinance as yf
from functools import lru_cache

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（政策 & 護城河 & 成長手動輸入版）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],  # TSLA 去掉
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
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
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)

WEIGHTS = {
    "穩健型":{"PE":0.3,"ForwardPE":0.2,"ROE":0.3,"Policy":0.1,"Moat":0.1,"Growth":0.0,"PEG":0.0},
    "成長型":{"PE":0.15,"ForwardPE":0.25,"ROE":0.2,"Policy":0.1,"Moat":0.1,"Growth":0.2,"PEG":0.2},
    "平衡型":{"PE":0.2,"ForwardPE":0.2,"ROE":0.25,"Policy":0.1,"Moat":0.1,"Growth":0.1,"PEG":0.15}
}

# =========================
# 快取 Yahoo Finance
# =========================
@st.cache_data(ttl=300)
def get_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info
    except:
        return {}

# =========================
# 工具函數
# =========================
def format_large_numbers(value):
    if value is None:
        return "-"
    if isinstance(value,(int,float)):
        if value>=1e9:
            return f"{value/1e9:.2f} B"
        elif value>=1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score = sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def compute_scores(row, manual_scores=None):
    PE = row.get("PE") or 50
    ForwardPE = row.get("Forward PE") or 50
    ROE = row.get("ROE") or 0.15
    PEG = row.get("PEG") or None
    FCF = row.get("FCF") or 0

    # ROE 校正
    if FCF < 0:
        ROE *= 0.8

    # PEG 計算
    if PEG is None or PEG==0:
        growth = row.get("EPS_Growth") or 0.1
        if growth>0:
            PEG = PE/growth
        else:
            PEG = None

    # 分數計算
    PE_score = max(0,min(100,(50-PE)/(50-15)*100))
    ForwardPE_score = max(0,min(100,(50-ForwardPE)/(50-15)*100))
    ROE_score = min(max(ROE/0.3*100,0),100)
    PEG_score = min(max(10/PEG*100,0),100) if PEG else 50

    Policy_score = 50
    Moat_score = calculate_moat(row.get("股票"))
    Growth_score = 50

    if manual_scores and row.get("股票") in manual_scores:
        scores = manual_scores[row.get("股票")]
        Policy_score = scores.get("Policy_score",Policy_score)
        Moat_score = scores.get("Moat_score",Moat_score)
        Growth_score = scores.get("Growth_score",Growth_score)

    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w.get("PE",0)+ForwardPE_score*w.get("ForwardPE",0)+
        ROE_score*w.get("ROE",0)+Policy_score*w.get("Policy",0)+
        Moat_score*w.get("Moat",0)+Growth_score*w.get("Growth",0)+
        PEG_score*w.get("PEG",0)
        ,2
    )

    return PE_score, ForwardPE_score, ROE_score, Policy_score, Moat_score, Growth_score, PEG_score, Total_score

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
    symbol=st.sidebar.text_input("輸入美股代碼","AAPL")
    st.subheader(f"📌 {symbol} 分析")
    info = get_info(symbol)

    price = info.get("currentPrice")
    st.metric("股價", f"${format_large_numbers(price)}")

    row = {
        "股票": symbol,
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "ROE": info.get("returnOnEquity"),
        "FCF": info.get("freeCashflow"),
        "PEG": info.get("pegRatio"),
        "Forward EPS": info.get("forwardEps"),
        "EPS_Growth": info.get("earningsQuarterlyGrowth")
    }

    # 手動分數
    manual_policy = st.number_input("政策分數",0,100,value=st.session_state[f"{symbol}_policy"], key=f"{symbol}_policy")
    manual_moat = st.number_input("護城河分數",0,100,value=st.session_state[f"{symbol}_moat"], key=f"{symbol}_moat")
    manual_growth = st.number_input("成長分數",0,100,value=st.session_state[f"{symbol}_growth"], key=f"{symbol}_growth")

    scores = compute_scores(row, manual_scores={symbol:{
        "Policy_score": manual_policy,
        "Moat_score": manual_moat,
        "Growth_score": manual_growth
    }})

    PE_s, ForwardPE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = scores

    st.metric("PE分數", round(PE_s,2))
    st.metric("Forward PE分數", round(ForwardPE_s,2))
    st.metric("ROE分數", round(ROE_s,2))
    st.metric("PEG分數", round(PEG_s,2) if PEG_s else "-")
    st.metric("政策分數", Policy_s)
    st.metric("護城河分數", Moat_s)
    st.metric("成長分數", Growth_s)
    st.metric("綜合分數", Total_s)
    st.write(pd.DataFrame([row]).T.style.format("{:.2f}"))

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業比較")
    manual_scores = {}
    rows = []

    for symbol in SECTORS[sector]:
        info = get_info(symbol)
        row = {
            "股票": symbol,
            "股價": info.get("currentPrice"),
            "PE": info.get("trailingPE"),
            "Forward PE": info.get("forwardPE"),
            "ROE": info.get("returnOnEquity"),
            "FCF": info.get("freeCashflow"),
            "PEG": info.get("pegRatio"),
            "Forward EPS": info.get("forwardEps"),
            "EPS_Growth": info.get("earningsQuarterlyGrowth")
        }

        # 手動分數
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數",0,100,value=st.session_state[f"{symbol}_policy"], key=f"{symbol}_policy")
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數",0,100,value=st.session_state[f"{symbol}_moat"], key=f"{symbol}_moat")
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數",0,100,value=st.session_state[f"{symbol}_growth"], key=f"{symbol}_growth")

        manual_scores[symbol] = {
            "Policy_score": manual_policy,
            "Moat_score": manual_moat,
            "Growth_score": manual_growth
        }

        PE_s, ForwardPE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = compute_scores(row, manual_scores)
        row.update({
            "PE_score": round(PE_s,2),
            "ForwardPE_score": round(ForwardPE_s,2),
            "ROE_score": round(ROE_s,2),
            "Policy_score": Policy_s,
            "Moat_score": Moat_s,
            "Growth_score": Growth_s,
            "PEG_score": round(PEG_s,2) if PEG_s else "-",
            "綜合分數": Total_s
        })

        # 大數字格式化
        for col in ["股價"]:
            row[col] = format_large_numbers(row[col])

        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        df = df[["股票","股價","PE","Forward PE","ROE","PEG","Forward EPS",
                 "PE_score","ForwardPE_score","ROE_score","PEG_score",
                 "Policy_score","Moat_score","Growth_score","綜合分數"]]
        st.dataframe(df.style.format("{:.2f}"), use_container_width=True)
