import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（手動分數 + 行業動態PE/ROE + Forward加權）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],  # TSLA 移除
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
    "穩健型":{"PE":0.3,"ForwardPE":0.3,"ROE":0.2,"Policy":0.1,"Moat":0.1,"Growth":0.0,"PEG":0.0},
    "成長型":{"PE":0.2,"ForwardPE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.2,"PEG":0.1},
    "平衡型":{"PE":0.25,"ForwardPE":0.25,"ROE":0.2,"Policy":0.15,"Moat":0.1,"Growth":0.05,"PEG":0.0}
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
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "Forward EPS": info.get("forwardEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
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

def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def compute_scores(row,manual_scores=None,sector_avg_pe=None,sector_avg_roe=None):
    PE=row.get("PE")
    ForwardPE=row.get("Forward PE")
    ROE=row.get("ROE")
    FCF=row.get("FCF")
    EPS=row.get("EPS") or 0.1
    ForwardEPS=row.get("Forward EPS") or EPS
    
    # PEG計算
    PEG_val = None
    try:
        if EPS>0 and ForwardEPS>0 and ForwardPE>0:
            PEG_val = ForwardPE / ((ForwardEPS - EPS)/EPS)
            if PEG_val <=0:
                PEG_val = None
    except:
        PEG_val=None
    
    # PE / Forward PE 分數
    PE_score = 50
    if PE is not None and sector_avg_pe is not None:
        PE_score = max(0,min(100,(sector_avg_pe - PE)/sector_avg_pe*100))
    ForwardPE_score=50
    if ForwardPE is not None and sector_avg_pe is not None:
        ForwardPE_score = max(0,min(100,(sector_avg_pe - ForwardPE)/sector_avg_pe*100))
    
    # ROE 分數
    ROE_score = 50
    if ROE is not None and sector_avg_roe is not None:
        ROE_score = min(max(ROE / sector_avg_roe *100,0),100)
    # ROE 質量校正
    if FCF is not None and isinstance(FCF,(int,float)) and FCF<0:
        ROE_score *=0.8
    
    symbol=row["股票"]
    Policy_score=50
    Moat_score=calculate_moat(symbol)
    Growth_score=50
    
    if manual_scores and symbol in manual_scores:
        Policy_score=manual_scores[symbol].get("Policy_score",Policy_score)
        Moat_score=manual_scores[symbol].get("Moat_score",Moat_score)
        Growth_score=manual_scores[symbol].get("Growth_score",Growth_score)
    
    w=WEIGHTS[style]
    Total_score = round(
        PE_score*w.get("PE",0) + ForwardPE_score*w.get("ForwardPE",0) + ROE_score*w.get("ROE",0) +
        Policy_score*w.get("Policy",0) + Moat_score*w.get("Moat",0) + Growth_score*w.get("Growth",0) +
        (PEG_val if PEG_val else 0)*w.get("PEG",0)
        ,2)
    
    return PE_score, ForwardPE_score, ROE_score, Policy_score, Moat_score, Growth_score, PEG_val, Total_score

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
    symbol=st.sidebar.text_input("輸入美股代碼","NVDA")
    st.subheader(f"📌 {symbol} 分析")
    
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
    if price!="N/A":
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
    
    # 行業平均
    sector_avg_pe,sector_avg_roe=None,None
    if sector_found:
        pe_list=[]
        roe_list=[]
        for s in SECTORS[sector_found]:
            try:
                df=get_fundamentals(s)
                pe_val=df.loc[df["指標"]=="PE","數值"].values
                roe_val=df.loc[df["指標"]=="ROE","數值"].values
                if len(pe_val)>0 and pe_val[0]: pe_list.append(pe_val[0])
                if len(roe_val)>0 and roe_val[0]: roe_list.append(roe_val[0])
            except:
                pass
        if pe_list: sector_avg_pe=sum(pe_list)/len(pe_list)
        if roe_list: sector_avg_roe=sum(roe_list)/len(roe_list)
    
    # EPS 安全抓取
    EPS_val=0.1
    ForwardEPS_val=EPS_val
    if not funds_df.empty:
        PE_val=funds_df.loc[funds_df["指標"]=="PE","數值"].values[0] if "PE" in funds_df["指標"].values else None
        ROE_val=funds_df.loc[funds_df["指標"]=="ROE","數值"].values[0] if "ROE" in funds_df["指標"].values else None
        FCF_val=funds_df.loc[funds_df["指標"]=="FCF","數值"].values[0] if "FCF" in funds_df["指標"].values else None
        if "EPS" in funds_df["指標"].values:
            EPS_val=funds_df.loc[funds_df["指標"]=="EPS","數值"].values[0]
        if "Forward EPS" in funds_df["指標"].values:
            ForwardEPS_val=funds_df.loc[funds_df["指標"]=="Forward EPS","數值"].values[0]
    
    PE_s, ForwardPE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = compute_scores(
        {"股票":symbol,"PE":PE_val,"Forward PE":PE_val,"ROE":ROE_val,"FCF":FCF_val,"EPS":EPS_val,"Forward EPS":ForwardEPS_val},
        manual_scores={symbol:{"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}},
        sector_avg_pe=sector_avg_pe,
        sector_avg_roe=sector_avg_roe
    )
    
    st.metric("PE_score", PE_s)
    st.metric("Forward PE_score", ForwardPE_s)
    st.metric("ROE_score", ROE_s)
    st.metric("政策分數", Policy_s)
    st.metric("護城河分數", Moat_s)
    st.metric("成長分數", Growth_s)
    st.metric("PEG", f"{PEG_s:.2f}" if PEG_s else "-")
    st.metric("綜合分數", Total_s)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector=st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
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
    
    # 計算行業平均 PE/ROE
    pe_list=[]
    roe_list=[]
    for s in SECTORS[sector]:
        try:
            df=get_fundamentals(s)
            pe_val=df.loc[df["指標"]=="PE","數值"].values
            roe_val=df.loc[df["指標"]=="ROE","數值"].values
            if len(pe_val)>0 and pe_val[0]: pe_list.append(pe_val[0])
            if len(roe_val)>0 and roe_val[0]: roe_list.append(roe_val[0])
        except:
            pass
    sector_avg_pe=sum(pe_list)/len(pe_list) if pe_list else None
    sector_avg_roe=sum(roe_list)/len(roe_list) if roe_list else None
    
    rows=[]
    for symbol in SECTORS[sector]:
        row={"股票":symbol}
        try:
            df=get_fundamentals(symbol)
            for _,r in df.iterrows():
                row[r["指標"]]=r["數值"]
            
            EPS_val=row.get("EPS",0.1)
            ForwardEPS_val=row.get("Forward EPS",EPS_val)
            
            PE_s, ForwardPE_s, ROE_s, Policy_s, Moat_s, Growth_s, PEG_s, Total_s = compute_scores(
                row,manual_scores,sector_avg_pe,sector_avg_roe
            )
            
            row["PE_score"]=round(PE_s,2)
            row["ForwardPE_score"]=round(ForwardPE_s,2)
            row["ROE_score"]=round(ROE_s,2)
            row["Policy_score"]=round(Policy_s,2)
            row["Moat_score"]=round(Moat_s,2)
            row["Growth_score"]=round(Growth_s,2)
            row["PEG"]=f"{PEG_s:.2f}" if PEG_s else "-"
            row["綜合分數"]=round(Total_s,2)
            
            for col in ["FCF","市值","股價"]:
                if col in row:
                    row[col]=format_large_numbers(row[col])
            
            rows.append(row)
        except:
            pass
    
    if rows:
        result_df=pd.DataFrame(rows)
        result_df=result_df.sort_values("綜合分數",ascending=False)
        st.dataframe(result_df,use_container_width=True)
