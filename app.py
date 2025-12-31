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
# 股票池與護城河
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

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
    "穩健型":{"PE":0.2,"Forward_PE":0.2,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.1,"Forward_PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.15,"Forward_PE":0.25,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.1}
}

# =========================
# 快取財報
# =========================
@lru_cache(maxsize=256)
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
# 護城河計算
# =========================
def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    return round(sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100,2)

# =========================
# 大數字格式化
# =========================
def format_large_numbers(value):
    if value is None:
        return None
    if value >= 1e9:
        return f"{value/1e9:.2f} B"
    elif value >= 1e6:
        return f"{value/1e6:.2f} M"
    else:
        return f"{value:.2f}"

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
# 計算分數
# =========================
def compute_scores(symbol, manual_scores, sector_avg_pe=None, sector_avg_forward_pe=None):
    data = get_info(symbol)
    PE = data.get("PE")
    Forward_PE = data.get("Forward PE")
    ROE = data.get("ROE")
    FCF = data.get("FCF")
    
    # 動態調整分數
    PE_score = max(0,min(100,(sector_avg_pe/PE*100))) if PE and sector_avg_pe else 50
    Forward_PE_score = max(0,min(100,(sector_avg_forward_pe/Forward_PE*100))) if Forward_PE and sector_avg_forward_pe else 50
    ROE_score = min(max(ROE/0.3*100,0),100) if ROE else 50
    if FCF is not None and FCF<0:
        ROE_score *= 0.8  # ROE 綜合質量校正
    
    Policy_score = manual_scores.get("Policy_score",50)
    Moat_score = manual_scores.get("Moat_score", calculate_moat(symbol))
    Growth_score = manual_scores.get("Growth_score",50)
    
    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w.get("PE",0)+Forward_PE_score*w.get("Forward_PE",0)+ROE_score*w.get("ROE",0)+
        Policy_score*w.get("Policy",0)+Moat_score*w.get("Moat",0)+Growth_score*w.get("Growth",0),2
    )
    
    # 將股價放在第一欄
    return {"股票":symbol,"股價":data.get("股價"),"PE_score":PE_score,"Forward_PE_score":Forward_PE_score,
            "ROE_score":ROE_score,"Policy_score":Policy_score,"Moat_score":Moat_score,
            "Growth_score":Growth_score,"綜合分數":Total_score,
            "PE":data.get("PE"),"Forward PE":data.get("Forward PE"),"ROE":ROE,
            "EPS":data.get("EPS"),"市值":data.get("市值"),"FCF":data.get("FCF")}

# =========================
# 單一股票分析模式
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA").upper()
    st.subheader(f"📌 {symbol} 分析")
    
    # 手動輸入保留 session_state
    manual_scores = {
        "Policy_score": st.number_input("政策分數",0,100,value=int(st.session_state.get(f"{symbol}_policy",50)),key=f"{symbol}_policy"),
        "Moat_score": st.number_input("護城河分數",0,100,value=int(st.session_state.get(f"{symbol}_moat",calculate_moat(symbol))),key=f"{symbol}_moat"),
        "Growth_score": st.number_input("成長分數",0,100,value=int(st.session_state.get(f"{symbol}_growth",50)),key=f"{symbol}_growth")
    }
    
    # 計算分數
    scores = compute_scores(symbol, manual_scores)
    # 格式化大數字
    for k in ["市值","FCF","股價","EPS"]:
        if scores.get(k) is not None:
            scores[k] = format_large_numbers(scores[k])
    
    # 顯示
    st.metric("即時股價", f"{scores['股價']}")
    df = pd.DataFrame(scores.items(),columns=["指標","數值"])
    st.table(df)
    st.metric("綜合分數", scores["綜合分數"])

# =========================
# 產業共同比較模式
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業比較")
    
    # 先算產業平均
    sector_data = []
    pe_list, forward_pe_list = [],[]
    for symbol in SECTORS[sector]:
        data = get_info(symbol)
        if data.get("PE"): pe_list.append(data.get("PE"))
        if data.get("Forward PE"): forward_pe_list.append(data.get("Forward PE"))
    
    sector_avg_pe = sum(pe_list)/len(pe_list) if pe_list else None
    sector_avg_forward_pe = sum(forward_pe_list)/len(forward_pe_list) if forward_pe_list else None
    
    # 建立 dataframe
    rows = []
    for symbol in SECTORS[sector]:
        manual_scores = {
            "Policy_score": st.sidebar.number_input(f"{symbol} 政策分數",0,100,value=int(st.session_state.get(f"{symbol}_policy",50)),key=f"{symbol}_policy"),
            "Moat_score": st.sidebar.number_input(f"{symbol} 護城河分數",0,100,value=int(st.session_state.get(f"{symbol}_moat",calculate_moat(symbol))),key=f"{symbol}_moat"),
            "Growth_score": st.sidebar.number_input(f"{symbol} 成長分數",0,100,value=int(st.session_state.get(f"{symbol}_growth",50)),key=f"{symbol}_growth")
        }
        score_row = compute_scores(symbol, manual_scores, sector_avg_pe, sector_avg_forward_pe)
        for col in ["股價","市值","FCF","EPS"]:
            if score_row.get(col) is not None:
                score_row[col] = format_large_numbers(score_row[col])
        rows.append(score_row)
    
    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("綜合分數",ascending=False)
    st.dataframe(result_df,use_container_width=True)
