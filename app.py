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
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],  # 減 TSLA
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
    "CRWD":{"retention":0.88,"switching":0.75,"patent":0.6,"network":0.8},
    "PANW":{"retention":0.85,"switching":0.7,"patent":0.65,"network":0.75},
    "ZS":{"retention":0.8,"switching":0.65,"patent":0.5,"network":0.7},
    "OKTA":{"retention":0.82,"switching":0.6,"patent":0.55,"network":0.65},
    "S":{"retention":0.78,"switching":0.55,"patent":0.5,"network":0.6},
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
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0,"Forward":0.5,"PEG":0.3},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3,"Forward":0.5,"PEG":0.4},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1,"Forward":0.5,"PEG":0.3}
}

# =========================
# 快取函數
# =========================
@st.cache_data(ttl=300)
def get_info(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    return info

# =========================
# 工具函數
# =========================
def format_large_numbers(val):
    if val is None:
        return "-"
    if val>=1e9:
        return f"{val/1e9:.2f} B"
    elif val>=1e6:
        return f"{val/1e6:.2f} M"
    else:
        return f"{val:.2f}"

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score = sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def compute_scores(row, sector_avg_pe=None, sector_avg_forward=None, manual_scores=None):
    PE = row.get("PE")
    Forward_PE = row.get("Forward PE")
    ROE = row.get("ROE")
    FCF = row.get("FCF")
    PEG = row.get("PEG")
    
    # =================
    # PE 動態分數
    # =================
    if PE and sector_avg_pe:
        PE_score = max(0, min(100, (sector_avg_pe*1.5 - PE)/(sector_avg_pe*1.5 - sector_avg_pe*0.5)*100))
    else:
        PE_score = 50
    
    # =================
    # Forward PE 動態分數
    # =================
    if Forward_PE and sector_avg_forward:
        Forward_score = max(0,min(100,(sector_avg_forward*1.5 - Forward_PE)/(sector_avg_forward*1.5 - sector_avg_forward*0.5)*100))
    else:
        Forward_score = 50
    
    # =================
    # ROE 綜合質量校正
    # =================
    if ROE is not None:
        ROE_score = min(max(ROE/0.3*100,0),100)
        if FCF is not None and FCF<0:
            ROE_score *= 0.8
    else:
        ROE_score = 50
    
    # 手動分數
    Policy_score = 50
    Moat_score = calculate_moat(row["股票"])
    Growth_score = 50
    if manual_scores and row["股票"] in manual_scores:
        Policy_score = manual_scores[row["股票"]].get("Policy_score",Policy_score)
        Moat_score = manual_scores[row["股票"]].get("Moat_score",Moat_score)
        Growth_score = manual_scores[row["股票"]].get("Growth_score",Growth_score)
    
    # 加權總分
    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w["PE"] + ROE_score*w["ROE"] + Policy_score*w["Policy"] +
        Moat_score*w["Moat"] + Growth_score*w["Growth"] +
        Forward_score*w["Forward"] + (PEG if PEG else 50)*w["PEG"],2
    )
    
    return round(PE_score,2), round(ROE_score,2), round(Policy_score,2), round(Moat_score,2), round(Growth_score,2), round(Total_score,2)

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
# 主程式
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入股票代碼","NVDA").upper()
    try:
        info = get_info(symbol)
        price = info.get("currentPrice")
        st.metric("股價", f"${price:.2f}" if price else "-")
        PE_val = info.get("trailingPE")
        Forward_PE_val = info.get("forwardPE")
        ROE_val = info.get("returnOnEquity")
        FCF_val = info.get("freeCashflow")
        PEG_val = info.get("pegRatio")
        EPS_forward = info.get("forwardEps")
        
        df = pd.DataFrame({
            "指標":["股價","PE","Forward PE","ROE","FCF","PEG","Forward EPS"],
            "數值":[price, PE_val, Forward_PE_val, ROE_val, FCF_val, PEG_val, EPS_forward]
        })
        df["數值"] = df["數值"].apply(lambda x: format_large_numbers(x) if isinstance(x,(int,float)) else ("-" if x is None else round(x,2)))
        st.table(df)
        
        # 手動分數
        manual_policy = st.number_input(f"{symbol} 政策分數",0,100,key=f"{symbol}_policy")
        manual_moat = st.number_input(f"{symbol} 護城河分數",0,100,key=f"{symbol}_moat")
        manual_growth = st.number_input(f"{symbol} 成長分數",0,100,key=f"{symbol}_growth")
        
        # 計算動態分數
        PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
            {"股票":symbol,"PE":PE_val,"Forward PE":Forward_PE_val,"ROE":ROE_val,"FCF":FCF_val,"PEG":PEG_val},
            sector_avg_pe=None, sector_avg_forward=None,
            manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}
        )
        st.metric("政策分數",Policy_s)
        st.metric("護城河分數",Moat_s)
        st.metric("成長分數",Growth_s)
        st.metric("綜合分數",Total_s)
    except Exception as e:
        st.error(f"取得資料失敗: {e}")

elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()))
    rows = []
    
    symbols = SECTORS[sector]
    infos = {}
    for symbol in symbols:
        try:
            infos[symbol] = get_info(symbol)
        except:
            infos[symbol] = {}
    
    # 計算產業平均
    sector_pe_list = [infos[s].get("trailingPE") for s in symbols if infos[s].get("trailingPE") is not None]
    sector_forward_list = [infos[s].get("forwardPE") for s in symbols if infos[s].get("forwardPE") is not None]
    sector_avg_pe = sum(sector_pe_list)/len(sector_pe_list) if sector_pe_list else None
    sector_avg_forward = sum(sector_forward_list)/len(sector_forward_list) if sector_forward_list else None
    
    manual_scores = {}
    for symbol in symbols:
        # 初始化 session_state
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"]=50
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"]=calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"]=50
        
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數",0,100,key=f"{symbol}_policy")
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數",0,100,key=f"{symbol}_moat")
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數",0,100,key=f"{symbol}_growth")
        
        manual_scores[symbol] = {
            "Policy_score":manual_policy,
            "Moat_score":manual_moat,
            "Growth_score":manual_growth
        }
    
    for symbol in symbols:
        info = infos.get(symbol,{})
        row = {"股票":symbol,"股價":info.get("currentPrice")}
        for k in ["PE","Forward PE","ROE","FCF","PEG","forwardEps"]:
            row[k] = info.get(k) if info.get(k) is not None else None
        PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
            {"股票":symbol,"PE":row.get("PE"),"Forward PE":row.get("Forward PE"),
             "ROE":row.get("ROE"),"FCF":row.get("FCF"),"PEG":row.get("PEG")},
            sector_avg_pe, sector_avg_forward,
            manual_scores
        )
        row["PE_score"]=PE_s
        row["ROE_score"]=ROE_s
        row["Policy_score"]=Policy_s
        row["Moat_score"]=Moat_s
        row["Growth_score"]=Growth_s
        row["綜合分數"]=Total_s
        
        for col in ["股價","FCF"]:
            if row[col] is not None:
                row[col]=format_large_numbers(row[col])
        rows.append(row)
    
    df = pd.DataFrame(rows)
    # 將股價放第一欄
    cols = ["股票","股價"] + [c for c in df.columns if c not in ["股票","股價"]]
    df = df[cols]
    st.dataframe(df.round(2),use_container_width=True)
