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
    # Mag7
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
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
style = st.sidebar.selectbox("投資風格",["穩健型","平衡型","成長型"],index=1)
WEIGHTS = {
    "穩健型":{"PE":0.3,"Forward_PE":0.2,"ROE":0.3,"Policy":0.1,"Moat":0.1,"Growth":0.0,"PEG":0.0},
    "平衡型":{"PE":0.25,"Forward_PE":0.25,"ROE":0.2,"Policy":0.1,"Moat":0.1,"Growth":0.05,"PEG":0.05},
    "成長型":{"PE":0.2,"Forward_PE":0.3,"ROE":0.15,"Policy":0.1,"Moat":0.05,"Growth":0.1,"PEG":0.1}
}

# =========================
# 快取 Yahoo Finance
# =========================
@st.cache_data(ttl=3600)
def get_info(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    return info

# =========================
# 格式化大數字
# =========================
def format_large_numbers(value):
    if value is None:
        return "-"
    if isinstance(value,(int,float)):
        if abs(value)>=1e9:
            return f"{value/1e9:.2f}B"
        elif abs(value)>=1e6:
            return f"{value/1e6:.2f}M"
        else:
            return f"{value:.2f}"
    return value

# =========================
# 護城河分數
# =========================
def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

# =========================
# 計算分數
# =========================
def compute_scores(stock,manual_scores=None,sector_avg_pe=None,sector_avg_forward_pe=None,sector_avg_roe=None):
    # PE
    PE_score = 50
    if stock.get("PE") and sector_avg_pe:
        PE_score = max(0,min(100,(sector_avg_pe - stock["PE"])/sector_avg_pe*100))

    # Forward PE
    FPE_score = 50
    if stock.get("Forward_PE") and sector_avg_forward_pe:
        FPE_score = max(0,min(100,(sector_avg_forward_pe - stock["Forward_PE"])/sector_avg_forward_pe*100))

    # ROE
    ROE_score = 50
    ROE = stock.get("ROE")
    FCF = stock.get("FCF")
    NetDebt = stock.get("NetDebt")
    EBITDA = stock.get("EBITDA")
    if ROE:
        ROE_score = min(max(ROE/0.3*100,0),100)
        # 質量校正
        if FCF is not None and FCF<0:
            ROE_score *= 0.8
        if NetDebt is not None and EBITDA and EBITDA>0 and NetDebt/EBITDA>3:
            ROE_score *= 0.8

    # PEG 自動計算
    PEG_score = 50
    PEG = stock.get("PEG")
    if PEG is None or PEG==0:
        EPS = stock.get("EPS")
        Forward_EPS = stock.get("Forward_EPS")
        if EPS and Forward_EPS and EPS>0:
            growth_rate = (Forward_EPS - EPS)/EPS
            if growth_rate>0:
                PEG_calc = stock.get("Forward_PE",stock.get("PE")) / (growth_rate*100)
                stock["PEG"] = round(PEG_calc,2)
            else:
                stock["PEG"]="-"
        else:
            stock["PEG"]="-"
    else:
        stock["PEG"]=round(PEG,2)

    # 手動分數
    Policy_score = stock.get("Policy_score",50)
    Moat_score = stock.get("Moat_score",50)
    Growth_score = stock.get("Growth_score",50)

    if manual_scores and stock["股票"] in manual_scores:
        Policy_score = manual_scores[stock["股票"]].get("Policy_score",Policy_score)
        Moat_score = manual_scores[stock["股票"]].get("Moat_score",Moat_score)
        Growth_score = manual_scores[stock["股票"]].get("Growth_score",Growth_score)

    w = WEIGHTS[style]
    Total_score = round(PE_score*w["PE"] + FPE_score*w["Forward_PE"] + ROE_score*w["ROE"] +
                        Policy_score*w["Policy"] + Moat_score*w["Moat"] + Growth_score*w["Growth"] +
                        (stock["PEG"] if stock["PEG"]!="-"/100*100 else 0)*w["PEG"],2)

    return PE_score,FPE_score,ROE_score,Policy_score,Moat_score,Growth_score,Total_score

# =========================
# 初始化 session_state
# =========================
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"]=50
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"]=calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"]=50

# =========================
# 模式：單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA")
    st.subheader(f"📌 {symbol} 分析")

    info = get_info(symbol)
    price = info.get("currentPrice")
    change = info.get("regularMarketChangePercent")
    st.metric("即時股價", format_large_numbers(price), f"{change:.2f}%")

    # 財報資料
    stock_data = {
        "股票":symbol,
        "股價":price,
        "PE":info.get("trailingPE"),
        "Forward_PE":info.get("forwardPE"),
        "EPS":info.get("trailingEps"),
        "Forward_EPS":info.get("forwardEps"),
        "ROE":info.get("returnOnEquity"),
        "FCF":info.get("freeCashflow"),
        "NetDebt":info.get("totalDebt"),
        "EBITDA":info.get("ebitda"),
        "市值":info.get("marketCap")
    }

    # 手動分數
    manual_policy = st.number_input("政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
    manual_moat = st.number_input("護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
    manual_growth = st.number_input("成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))

    manual_scores = {symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}

    PE_s,FPE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(stock_data,manual_scores=manual_scores)

    st.metric("PE 分數",round(PE_s,2))
    st.metric("Forward PE 分數",round(FPE_s,2))
    st.metric("ROE 分數",round(ROE_s,2))
    st.metric("政策分數",round(Policy_s,2))
    st.metric("護城河分數",round(Moat_s,2))
    st.metric("成長分數",round(Growth_s,2))
    st.metric("PEG", stock_data.get("PEG","-"))
    st.metric("綜合分數",round(Total_s,2))

# =========================
# 模式：產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
    st.subheader(f"🏭 {sector} 產業比較")

    manual_scores={}
    rows=[]
    symbols = SECTORS[sector]
    # 計算產業平均值
    sector_pe_list=[]
    sector_forward_pe_list=[]
    sector_roe_list=[]
    for symbol in symbols:
        info = get_info(symbol)
        if info.get("trailingPE"): sector_pe_list.append(info["trailingPE"])
        if info.get("forwardPE"): sector_forward_pe_list.append(info["forwardPE"])
        if info.get("returnOnEquity"): sector_roe_list.append(info["returnOnEquity"])
    sector_avg_pe = sum(sector_pe_list)/len(sector_pe_list) if sector_pe_list else None
    sector_avg_forward_pe = sum(sector_forward_pe_list)/len(sector_forward_pe_list) if sector_forward_pe_list else None
    sector_avg_roe = sum(sector_roe_list)/len(sector_roe_list) if sector_roe_list else None

    for symbol in symbols:
        info = get_info(symbol)
        price = info.get("currentPrice")
        stock_data = {
            "股票":symbol,
            "股價":format_large_numbers(price),
            "PE":info.get("trailingPE"),
            "Forward_PE":info.get("forwardPE"),
            "EPS":info.get("trailingEps"),
            "Forward_EPS":info.get("forwardEps"),
            "ROE":info.get("returnOnEquity"),
            "FCF":info.get("freeCashflow"),
            "NetDebt":info.get("totalDebt"),
            "EBITDA":info.get("ebitda"),
            "市值":info.get("marketCap")
        }

        # 手動分數
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))

        manual_scores[symbol] = {"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}

        PE_s,FPE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(stock_data,manual_scores=manual_scores,
                                                                            sector_avg_pe=sector_avg_pe,
                                                                            sector_avg_forward_pe=sector_avg_forward_pe,
                                                                            sector_avg_roe=sector_avg_roe)
        row = {
            "股票":symbol,
            "股價":format_large_numbers(price),
            "PE":round(info.get("trailingPE",0) or 0,2),
            "Forward PE":round(info.get("forwardPE",0) or 0,2),
            "EPS":round(info.get("trailingEps",0) or 0,2),
            "Forward EPS":round(info.get("forwardEps",0) or 0,2),
            "ROE":round(info.get("returnOnEquity",0) or 0,2),
            "PEG": stock_data.get("PEG","-"),
            "市值":format_large_numbers(info.get("marketCap")),
            "PE_score":round(PE_s,2),
            "Forward_PE_score":round(FPE_s,2),
            "ROE_score":round(ROE_s,2),
            "Policy_score":round(Policy_s,2),
            "Moat_score":round(Moat_s,2),
            "Growth_score":round(Growth
