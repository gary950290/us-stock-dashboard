import streamlit as st
import pandas as pd
import yfinance as yf
from functools import lru_cache

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（含Forward & PEG & 動態評分）")

# =========================
# 產業股票池
# Mag7 已移除 TSLA
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],
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
    # 其他產業略
}
MOAT_WEIGHTS = {"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)
WEIGHTS = {
    "穩健型":{"PE":0.2,"Forward_PE":0.3,"ROE":0.25,"Policy":0.1,"Moat":0.1,"Growth":0.05,"PEG":0.0},
    "成長型":{"PE":0.1,"Forward_PE":0.3,"ROE":0.2,"Policy":0.1,"Moat":0.05,"Growth":0.2,"PEG":0.05},
    "平衡型":{"PE":0.15,"Forward_PE":0.3,"ROE":0.25,"Policy":0.1,"Moat":0.1,"Growth":0.05,"PEG":0.05}
}

# =========================
# 快取 Yahoo Finance
# =========================
@st.cache_data(ttl=3600)
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

def calculate_peg(forward_pe, eps, forward_eps):
    try:
        if forward_pe and eps and forward_eps and eps != 0:
            growth_rate = ((forward_eps - eps) / abs(eps)) * 100
            if growth_rate != 0:
                return round(forward_pe / growth_rate, 2)
    except:
        pass
    return "-"

def compute_scores(row, sector_avg_pe=None, sector_avg_forward_pe=None, manual_scores=None):
    w = WEIGHTS[style]
    
    PE = row.get("PE")
    Forward_PE = row.get("Forward PE")
    ROE = row.get("ROE")
    FCF = row.get("FCF")
    NetDebtEBITDA = row.get("NetDebtEBITDA",0)
    PEG = row.get("PEG")

    # 動態評分
    if PE and sector_avg_pe:
        PE_score = max(0,min(100,(sector_avg_pe - PE)/sector_avg_pe*100 + 50))
    else:
        PE_score = 50
    if Forward_PE and sector_avg_forward_pe:
        Forward_PE_score = max(0,min(100,(sector_avg_forward_pe - Forward_PE)/sector_avg_forward_pe*100 + 50))
    else:
        Forward_PE_score = 50

    if ROE:
        ROE_score = min(max(ROE/0.3*100,0),100)
        # ROE 綜合質量校正
        if FCF is not None and FCF <0:
            ROE_score *= 0.8
        if NetDebtEBITDA > 3:
            ROE_score *=0.8
    else:
        ROE_score =50

    Policy_score = 50
    Moat_score = calculate_moat(row.get("股票"))
    Growth_score = 50
    PEG_score = 50 if PEG=="-" else min(max(100 - PEG*10,0),100)

    if manual_scores and row.get("股票") in manual_scores:
        Policy_score = manual_scores[row.get("股票")].get("Policy_score",Policy_score)
        Moat_score = manual_scores[row.get("股票")].get("Moat_score",Moat_score)
        Growth_score = manual_scores[row.get("股票")].get("Growth_score",Growth_score)

    Total_score = round(
        PE_score*w["PE"] + Forward_PE_score*w["Forward_PE"] + ROE_score*w["ROE"] +
        Policy_score*w["Policy"] + Moat_score*w["Moat"] + Growth_score*w["Growth"] +
        PEG_score*w.get("PEG",0),2
    )
    return PE_score, Forward_PE_score, ROE_score, Policy_score, Moat_score, Growth_score, PEG_score, Total_score

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
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA")
    info = get_info(symbol)
    if not info:
        st.warning("無法取得資料")
    else:
        st.subheader(f"📌 {symbol} 分析")
        st.metric("即時股價", f"${format_large_numbers(info.get('currentPrice'))}", f"{info.get('regularMarketChangePercent',0):.2f}%")
        
        PEG_value = calculate_peg(info.get("forwardPE"), info.get("trailingEps"), info.get("forwardEps"))
        
        funds_data = {
            "股價":format_large_numbers(info.get("currentPrice")),
            "PE":info.get("trailingPE"),
            "Forward PE":info.get("forwardPE"),
            "ROE":info.get("returnOnEquity"),
            "EPS":info.get("trailingEps"),
            "Forward EPS":info.get("forwardEps"),
            "市值":format_large_numbers(info.get("marketCap")),
            "FCF":info.get("freeCashflow"),
            "PEG": PEG_value
        }
        df = pd.DataFrame(funds_data.items(), columns=["指標","數值"])
        st.table(df)

        # 手動分數
        manual_policy = st.number_input("政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
        manual_moat = st.number_input("護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
        manual_growth = st.number_input("成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))
        
        PE_s, Forward_PE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = compute_scores(
            {"股票":symbol, **funds_data},
            manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}
        )
        st.metric("政策分數",Policy_s)
        st.metric("護城河分數",Moat_s)
        st.metric("成長分數",Growth_s)
        st.metric("PEG分數",PEG_s)
        st.metric("綜合分數",Total_s)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業比較")
    
    # 手動分數
    manual_scores={}
    for symbol in SECTORS[sector]:
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))
        manual_scores[symbol] = {
            "Policy_score": manual_policy,
            "Moat_score": manual_moat,
            "Growth_score": manual_growth
        }

    rows=[]
    # 計算產業平均 PE / Forward PE
    pe_list=[]
    fpe_list=[]
    for symbol in SECTORS[sector]:
        info = get_info(symbol)
        if info.get("trailingPE"): pe_list.append(info.get("trailingPE"))
        if info.get("forwardPE"): fpe_list.append(info.get("forwardPE"))
    sector_avg_pe = sum(pe_list)/len(pe_list) if pe_list else None
    sector_avg_forward_pe = sum(fpe_list)/len(fpe_list) if fpe_list else None

    for symbol in SECTORS[sector]:
        info = get_info(symbol)
        PEG_value = calculate_peg(info.get("forwardPE"), info.get("trailingEps"), info.get("forwardEps"))
        row = {
            "股票":symbol,
            "股價":format_large_numbers(info.get("currentPrice")),
            "PE":round(info.get("trailingPE") or 0,2),
            "Forward PE":round(info.get("forwardPE") or 0,2),
            "ROE":round(info.get("returnOnEquity") or 0,2),
            "EPS":round(info.get("trailingEps") or 0,2),
            "Forward EPS":round(info.get("forwardEps") or 0,2),
            "市值":format_large_numbers(info.get("marketCap")),
            "FCF":info.get("freeCashflow"),
            "PEG": PEG_value
        }
        PE_s, Forward_PE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = compute_scores(
            row, sector_avg_pe=sector_avg_pe, sector_avg_forward_pe=sector_avg_forward_pe, manual_scores=manual_scores
        )
        row.update({
            "PE_score":round(PE_s,2),
            "Forward_PE_score":round(Forward_PE_s,2),
            "ROE_score":round(ROE_s,2),
            "Policy_score":round(Policy_s,2),
            "Moat_score":round(Moat_s,2),
            "Growth_score":round(Growth_s,2),
            "PEG_score":round(PEG_s,2),
            "綜合分數":round(Total_s,2)
        })
        rows.append(row)
    if rows:
        result_df = pd.DataFrame(rows)
        st.dataframe(result_df, use_container_width=True)
