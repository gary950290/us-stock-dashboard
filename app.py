import streamlit as st
import pandas as pd
import yfinance as yf
import os
import json
from datetime import datetime

# =========================
# 頁面設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（手動分數保留 + 快取版）")

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
# =========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},
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
# CSV快取手動分數 & yfinance快取
# =========================
CSV_SCORE_FILE="manual_scores.csv"
CACHE_DIR="yf_cache"
os.makedirs(CACHE_DIR,exist_ok=True)

def load_manual_scores():
    if os.path.exists(CSV_SCORE_FILE):
        df=pd.read_csv(CSV_SCORE_FILE,index_col=0)
        return df.to_dict('index')
    return {}

def save_manual_scores(scores_dict):
    df=pd.DataFrame(scores_dict).T
    df.to_csv(CSV_SCORE_FILE)

def load_yf_cache(symbol):
    path=os.path.join(CACHE_DIR,f"{symbol}.json")
    if os.path.exists(path):
        with open(path,"r") as f:
            return json.load(f)
    return None

def save_yf_cache(symbol,data):
    path=os.path.join(CACHE_DIR,f"{symbol}.json")
    with open(path,"w") as f:
        json.dump(data,f)

# =========================
# 工具函數
# =========================
def get_price(symbol):
    try:
        info=yf.Ticker(symbol).info
        save_yf_cache(symbol,info)
        return info.get("currentPrice"), info.get("regularMarketChangePercent")
    except:
        cached=load_yf_cache(symbol)
        if cached:
            return cached.get("currentPrice"), cached.get("regularMarketChangePercent")
        return None,None

def get_fundamentals(symbol):
    try:
        info=yf.Ticker(symbol).info
        save_yf_cache(symbol,info)
    except:
        info=load_yf_cache(symbol) or {}
    data={
        "股價":info.get("currentPrice"),
        "PE":info.get("trailingPE"),
        "Forward PE":info.get("forwardPE"),
        "EPS":info.get("trailingEps"),
        "ROE":info.get("returnOnEquity"),
        "市值":info.get("marketCap"),
        "FCF":info.get("freeCashflow")
    }
    for k in data:
        if isinstance(data[k],float):
            data[k]=round(data[k],4)
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

def format_df(df,decimals=2):
    display_df=df.copy()
    float_cols=display_df.select_dtypes(include=["float","float64"]).columns
    display_df[float_cols]=display_df[float_cols].round(decimals)
    return display_df

def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def compute_scores(row,manual_scores=None):
    PE=row.get("PE")
    Forward_PE=row.get("Forward PE")
    ROE=row.get("ROE")
    FCF=row.get("FCF")
    
    PE_score=50
    if Forward_PE: PE_score=min(max(100-(Forward_PE-15)/35*100,0),100)
    elif PE: PE_score=min(max(100-(PE-15)/35*100,0),100)
    
    ROE_score=50
    if ROE is not None:
        ROE_score=min(max(ROE/0.3*100,0),100)
        if FCF is not None and FCF<0: ROE_score*=0.8
    
    symbol=row["股票"]
    Policy_score=50
    Moat_score=calculate_moat(symbol)
    Growth_score=50
    
    if manual_scores and symbol in manual_scores:
        Policy_score=manual_scores[symbol].get("Policy_score",Policy_score)
        Moat_score=manual_scores[symbol].get("Moat_score",Moat_score)
        Growth_score=manual_scores[symbol].get("Growth_score",Growth_score)
    
    w=WEIGHTS[style]
    Total_score=round(PE_score*w["PE"]+ROE_score*w["ROE"]+Policy_score*w["Policy"]+
                      Moat_score*w["Moat"]+Growth_score*w["Growth"],2)
    return PE_score,ROE_score,Policy_score,Moat_score,Growth_score,Total_score

# =========================
# 初始化 session_state
# =========================
manual_scores_cache = load_manual_scores()
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"]=manual_scores_cache.get(symbol,{}).get("Policy_score",50)
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"]=manual_scores_cache.get(symbol,{}).get("Moat_score",calculate_moat(symbol))
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"]=manual_scores_cache.get(symbol,{}).get("Growth_score",50)

# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol=st.sidebar.text_input("輸入美股代碼","NVDA").upper()
    st.subheader(f"📌 {symbol} 分析")
    price,change=get_price(symbol)
    if price: st.metric("即時股價",f"${price:.2f}",f"{change:.2f}%")
    
    funds_df=get_fundamentals(symbol)
    for col in ["FCF","市值"]:
        if col in funds_df["指標"].values:
            funds_df.loc[funds_df["指標"]==col,"數值"]=funds_df.loc[funds_df["指標"]==col,"數值"].apply(format_large_numbers)
    st.table(funds_df)
    
    st.subheader("手動輸入分數")
    manual_policy = st.number_input("政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
    manual_moat = st.number_input("護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
    manual_growth = st.number_input("成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))
    
    st.session_state[f"{symbol}_policy"]=manual_policy
    st.session_state[f"{symbol}_moat"]=manual_moat
    st.session_state[f"{symbol}_growth"]=manual_growth
    save_manual_scores({sym:{
        "Policy_score": st.session_state[f"{sym}_policy"],
        "Moat_score": st.session_state[f"{sym}_moat"],
        "Growth_score": st.session_state[f"{sym}_growth"]
    } for sym in st.session_state if sym.endswith("_policy")})
    
    PE_val = funds_df.loc[funds_df["指標"]=="PE","數值"].values[0] if "PE" in funds_df["指標"].values else None
    ROE_val = funds_df.loc[funds_df["指標"]=="ROE","數值"].values[0] if "ROE" in funds_df["指標"].values else None
    FCF_val = funds_df.loc[funds_df["指標"]=="FCF","數值"].values[0] if "FCF" in funds_df["指標"].values else None
    
    PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
        {"股票":symbol,"PE":PE_val,"ROE":ROE_val,"FCF":FCF_val},
        manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}
    )
    st.metric("政策分數",Policy_s)
    st.metric("護城河分數",Moat_s)
    st.metric("成長分數",Growth_s)
    st.metric("綜合分數",Total_s)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector=st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
    st.subheader(f"🏭 {sector} 產業比較")
    
    manual_scores = {}
    for symbol in SECTORS[sector]:
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數",0,100,key=f"{symbol}_policy",value=st.session_state.get(f"{symbol}_policy",50))
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數",0,100,key=f"{symbol}_moat",value=st.session_state.get(f"{symbol}_moat",calculate_moat(symbol)))
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數",0,100,key=f"{symbol}_growth",value=st.session_state.get(f"{symbol}_growth",50))
        st.session_state[f"{symbol}_policy"]=manual_policy
        st.session_state[f"{symbol}_moat"]=manual_moat
        st.session_state[f"{symbol}_growth"]=manual_growth
        manual_scores[symbol] = {
            "Policy_score": manual_policy,
            "Moat_score": manual_moat,
            "Growth_score": manual_growth
        }
    save_manual_scores({sym:{
        "Policy_score": st.session_state[f"{sym}_policy"],
        "Moat_score": st.session_state[f"{sym}_moat"],
        "Growth_score": st.session_state[f"{sym}_growth"]
    } for sym in st.session_state if sym.endswith("_policy")})
    
    rows=[]
    for symbol in SECTORS[sector]:
        df=get_fundamentals(symbol)
        row={"股票":symbol}
        for _,r in df.iterrows(): row[r["指標"]]=r["數值"]
        PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(row,manual_scores)
        row["PE_score"]=round(PE_s,2)
        row["ROE_score"]=round(ROE_s,2)
        row["Policy_score"]=round(Policy_s,2)
        row["Moat_score"]=round(Moat_s,2)
        row["Growth_score"]=round(Growth_s,2)
        row["綜合分數"]=round(Total_s,2)
        for col in ["FCF","市值"]:
            if col in row: row[col]=format_large_numbers(row[col])
        rows.append(row)
    if rows:
        result_df=pd.DataFrame(rows)
        result_df=format_df(result_df)
        result_df=result_df.sort_values("綜合分數",ascending=False)
        st.dataframe(result_df,use_container_width=True)

st.sidebar.markdown("""
### ℹ️ 評分說明
- PE_score: 估值分數，Forward PE 優先
- ROE_score: ROE 質量分數，若 FCF<0 會折扣 20%
- Policy_score: 手動輸入政策分數
- Moat_score: 護城河分數（Retention,Switching,Patent,Network 加權）
- Growth_score: 手動輸入成長分數
- 總分依投資風格加權
""")
