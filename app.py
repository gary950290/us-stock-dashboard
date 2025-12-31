import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（手動分數 + 行業動態PE/ROE）")

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
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1}
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

def compute_scores(row,manual_scores=None,sector_avg_pe=None,sector_avg_roe=None):
    PE=row.get("PE")
    PE_score = 50
    if PE is not None and sector_avg_pe is not None:
        PE_score = max(0,min(100,(sector_avg_pe - PE)/sector_avg_pe*100))
    
    ROE=row.get("ROE")
    ROE_score = 50
    if ROE is not None and sector_avg_roe is not None:
        ROE_score = min(max(ROE / sector_avg_roe *100,0),100)
    
    FCF=row.get("FCF")
    if FCF is not None and FCF<0:
        ROE_score *=0.8
    
    symbol=row["股票"]
    
    Policy_score = 50
    Moat_score = calculate_moat(symbol)
    Growth_score = 50
    
    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score",Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score",Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score",Growth_score)
    
    w=WEIGHTS[style]
    Total_score=round(PE_score*w["PE"]+ROE_score*w["ROE"]+Policy_score*w["Policy"]+
                      Moat_score*w["Moat"]+Growth_score*w["Growth"],2)
    
    return PE_score,ROE_score,Policy_score,Moat_score,Growth_score,Total_score

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
    symbol=st.sidebar.text_input("輸入美股代碼","NVDA")
    st.subheader(f"📌 {symbol} 分析")
    
    # 找到股票所屬產業
    sector_found=None
    for sector_name,stocks in SECTORS.items():
        if symbol in stocks:
            sector_found=sector_name
            break
    
    price,change=None,None
    try:
        price,change=get_price(symbol)
    except:
        price,change="N/A","N/A"
    
    if price != "N/A":
        st.metric("即時股價",f"${price:.2f}",f"{change:.2f}%")
    
    funds_df=pd.DataFrame()
    try:
        funds_df=get_fundamentals(symbol)
        for col in ["FCF","市值"]:
            if col in funds_df["指標"].values:
                funds_df.loc[funds_df["指標"]==col,"數值"]=funds_df.loc[funds_df["指標"]==col,"數值"].apply(format_large_numbers)
    except:
        st.warning("無法抓取財報數據")
    
    st.table(funds_df)
    
    st.subheader("手動輸入分數")
    manual_policy = st.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    manual_moat = st.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    manual_growth = st.number_input("成長分數", 0, 100, key=f"{symbol}_growth")
    
    # 計算行業平均PE/ROE
    sector_avg_pe,sector_avg_roe=None,None
    if sector_found:
        pe_list=[]
        roe_list=[]
        for s in SECTORS[sector_found]:
            try:
                df=get_fundamentals(s)
                pe_val=df.loc[df["指標"]=="PE","數值"].values
                roe_val=df.loc[df["指標"]=="ROE","數值"].values
                if len(pe_val)>0 and pe_val[0]:
                    pe_list.append(pe_val[0])
                if len(roe_val)>0 and roe_val[0]:
                    roe_list.append(roe_val[0])
            except:
                pass
        if pe_list: sector_avg_pe=sum(pe_list)/len(pe_list)
        if roe_list: sector_avg_roe=sum(roe_list)/len(roe_list)
    
    PE_val=ROE_val=FCF_val=None
    if not funds_df.empty:
        PE_val=funds_df.loc[funds_df["指標"]=="PE","數值"].values[0] if len(funds_df.loc[funds_df["指標"]=="PE","數值"])>0 else None
        ROE_val=funds_df.loc[funds_df["指標"]=="ROE","數值"].values[0] if len(funds_df.loc[funds_df["指標"]=="ROE","數值"])>0 else None
        FCF_val=funds_df.loc[funds_df["指標"]=="FCF","數值"].values[0] if len(funds_df.loc[funds_df["指標"]=="FCF","數值"])>0 else None
    
    PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
        {"股票":symbol,"PE":PE_val,"ROE":ROE_val,"FCF":FCF_val},
        manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}},
        sector_avg_pe=sector_avg_pe,
        sector_avg_roe=sector_avg_roe
    )
    
    st.metric("PE_score", PE_s)
    st.metric("ROE_score", ROE_s)
    st.metric("政策分數", Policy_s)
    st.metric("護城河分數", Moat_s)
    st.metric("成長分數", Growth_s)
    st.metric("綜合分數", Total_s)
