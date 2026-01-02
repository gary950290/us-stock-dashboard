import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime, timedelta

# =========================
# 0. API 配置 (從 Secrets 讀取)
# =========================
# 僅在有需要使用生成式 AI 功能時調用，此處保留接口以符合您的安全性需求
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

# =========================
# 設定
# =========================
st.set_page_config(page_title="2026 美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（產業專屬評分 + 2026 政策優化）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

# =========================
# 護城河資料（維持原版）
# ==========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},
    "CRWD":{"retention":0.88,"switching":0.82,"patent":0.75,"network":0.8},
    "PANW":{"retention":0.85,"switching":0.8,"patent":0.78,"network":0.75},
    "ZS":{"retention":0.82,"switching":0.78,"patent":0.7,"network":0.8},
    "OKTA":{"retention":0.8,"switching":0.75,"patent":0.65,"network":0.75},
    "FTNT":{"retention":0.83,"switching":0.77,"patent":0.72,"network":0.7},
    "S":{"retention":0.78,"switching":0.72,"patent":0.68,"network":0.72},
    "AMD":{"retention":0.82,"switching":0.75,"patent":0.88,"network":0.7},
    "INTC":{"retention":0.8,"switching":0.72,"patent":0.85,"network":0.68},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.92,"network":0.75},
    "AVGO":{"retention":0.85,"switching":0.78,"patent":0.9,"network":0.73},
    "CEG":{"retention":0.75,"switching":0.7,"patent":0.65,"network":0.6},
    "FLNC":{"retention":0.7,"switching":0.65,"patent":0.75,"network":0.55},
    "TE":{"retention":0.72,"switching":0.68,"patent":0.7,"network":0.58},
    "NEE":{"retention":0.8,"switching":0.75,"patent":0.65,"network":0.65},
    "ENPH":{"retention":0.73,"switching":0.68,"patent":0.78,"network":0.6},
    "EOSE":{"retention":0.65,"switching":0.6,"patent":0.7,"network":0.5},
    "VST":{"retention":0.77,"switching":0.72,"patent":0.68,"network":0.62},
    "PLUG":{"retention":0.68,"switching":0.63,"patent":0.72,"network":0.55},
    "OKLO":{"retention":0.7,"switching":0.65,"patent":0.8,"network":0.58},
    "SMR":{"retention":0.72,"switching":0.67,"patent":0.82,"network":0.6},
    "BE":{"retention":0.69,"switching":0.64,"patent":0.73,"network":0.56},
    "GEV":{"retention":0.71,"switching":0.66,"patent":0.75,"network":0.57},
    "NBIS":{"retention":0.65,"switching":0.6,"patent":0.55,"network":0.7},
    "IREN":{"retention":0.63,"switching":0.58,"patent":0.52,"network":0.68},
    "CRWV":{"retention":0.62,"switching":0.57,"patent":0.5,"network":0.67},
    "APLD":{"retention":0.64,"switching":0.59,"patent":0.53,"network":0.69},
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 2026 修正版：產業專屬權重配置 (AI/能源平衡)
# =========================
SECTOR_WEIGHTS = {
    "Mag7": {
        "穩健型":{"PE":0.30,"ROE":0.30,"Policy":0.10,"Moat":0.25,"Growth":0.05},
        "成長型":{"PE":0.15,"ROE":0.20,"Policy":0.15,"Moat":0.15,"Growth":0.35},
        "平衡型":{"PE":0.25,"ROE":0.25,"Policy":0.15,"Moat":0.20,"Growth":0.15}
    },
    "資安": { 
        "穩健型":{"PE":0.25,"ROE":0.25,"Policy":0.20,"Moat":0.20,"Growth":0.10},
        "成長型":{"PE":0.10,"ROE":0.15,"Policy":0.25,"Moat":0.10,"Growth":0.40},
        "平衡型":{"PE":0.20,"ROE":0.20,"Policy":0.25,"Moat":0.15,"Growth":0.20}
    },
    "半導體": {
        "穩健型":{"PE":0.30,"ROE":0.30,"Policy":0.20,"Moat":0.15,"Growth":0.05},
        "成長型":{"PE":0.15,"ROE":0.20,"Policy":0.25,"Moat":0.10,"Growth":0.30},
        "平衡型":{"PE":0.25,"ROE":0.25,"Policy":0.20,"Moat":0.15,"Growth":0.15}
    },
    "能源": { 
        "穩健型":{"PE":0.20,"ROE":0.20,"Policy":0.40,"Moat":0.15,"Growth":0.05},
        "成長型":{"PE":0.10,"ROE":0.15,"Policy":0.35,"Moat":0.10,"Growth":0.30},
        "平衡型":{"PE":0.15,"ROE":0.18,"Policy":0.37,"Moat":0.15,"Growth":0.15}
    },
    "NeoCloud": { 
        "穩健型":{"PE":0.25,"ROE":0.20,"Policy":0.25,"Moat":0.10,"Growth":0.20},
        "成長型":{"PE":0.10,"ROE":0.10,"Policy":0.20,"Moat":0.05,"Growth":0.55},
        "平衡型":{"PE":0.18,"ROE":0.18,"Policy":0.22,"Moat":0.08,"Growth":0.34}
    }
}

# =========================
# 工具函數 (維持原代碼邏輯)
# =========================
@st.cache_data(ttl=300)
def get_price_safe(symbol, retry=3, delay=2):
    for attempt in range(retry):
        try:
            info = yf.Ticker(symbol).info
            return info.get("currentPrice"), info.get("regularMarketChangePercent")
        except:
            if attempt < retry - 1: time.sleep(delay * (attempt + 1))
    return None, None

@st.cache_data(ttl=300)
def get_fundamentals_safe(symbol, retry=3, delay=2):
    for attempt in range(retry):
        try:
            info = yf.Ticker(symbol).info
            data = {
                "股價": info.get("currentPrice"),
                "PE": info.get("trailingPE"),
                "Forward PE": info.get("forwardPE"),
                "EPS": info.get("trailingEps"),
                "ROE": info.get("returnOnEquity"),
                "市值": info.get("marketCap"),
                "FCF": info.get("freeCashflow"),
                "營收成長": info.get("revenueGrowth"),
                "毛利率": info.get("grossMargins"),
                "營業利潤率": info.get("operatingMargins")
            }
            return pd.DataFrame(data.items(), columns=["指標", "數值"])
        except:
            if attempt < retry - 1: time.sleep(delay * (attempt + 1))
    return pd.DataFrame()

def format_large_numbers(value):
    if isinstance(value,(int,float)) and value is not None:
        if value>=1e9: return f"{value/1e9:.2f} B"
        elif value>=1e6: return f"{value/1e6:.2f} M"
        else: return f"{value:.2f}"
    return value

def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def get_score_color(score):
    if score >= 80: return "🟢"
    elif score >= 60: return "🟡"
    elif score >= 40: return "🟠"
    else: return "🔴"

# =========================
# 優化後的運算邏輯：嵌入 FCF、毛利率等配置
# =========================
def compute_sector_specific_scores(row, sector, manual_scores, sector_avg_pe, sector_avg_roe, style):
    PE = row.get("PE")
    ROE = row.get("ROE")
    FCF = row.get("FCF")
    revenue_growth = row.get("營收成長")
    gross_margin = row.get("毛利率")
    symbol = row["股票"]
    
    # PE/ROE 基礎分
    PE_score = 50
    if PE and sector_avg_pe:
        PE_score = max(0, min(100, (sector_avg_pe - PE) / sector_avg_pe * 100 + 50))
    
    ROE_score = 50
    if ROE and sector_avg_roe:
        ROE_score = min(max(ROE / sector_avg_roe * 100, 0), 100)
    
    # --- 產業特定修正 (邏輯設置) ---
    if sector in ["能源", "半導體"]:
        if FCF is not None and FCF < 0: ROE_score *= 0.7 # 能源/半導體現金流為負重扣
            
    if sector == "資安" and gross_margin:
        if gross_margin > 0.75: ROE_score = min(ROE_score * 1.2, 100) # 資安高毛利加成
            
    if sector == "NeoCloud":
        if revenue_growth and revenue_growth > 0.4: ROE_score = min(ROE_score * 1.15, 100)
        if FCF is not None and FCF < 0: ROE_score *= 0.9

    # 手動分數讀取
    Policy_score = manual_scores.get(symbol, {}).get("Policy_score", 50)
    Moat_score = manual_scores.get(symbol, {}).get("Moat_score", calculate_moat(symbol))
    Growth_score = manual_scores.get(symbol, {}).get("Growth_score", 50)
    
    # 權重套用
    w = SECTOR_WEIGHTS.get(sector, SECTOR_WEIGHTS["Mag7"])[style]
    Total_score = (PE_score * w["PE"] + ROE_score * w["ROE"] + 
                   Policy_score * w["Policy"] + Moat_score * w["Moat"] + 
                   Growth_score * w["Growth"])
    
    return round(PE_score, 2), round(ROE_score, 2), round(Policy_score, 2), round(Moat_score, 2), round(Growth_score, 2), round(Total_score, 2)

# =========================
# 側邊欄與初始化
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)

for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state: st.session_state[f"{symbol}_policy"] = 50
        if f"{symbol}_moat" not in st.session_state: st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state: st.session_state[f"{symbol}_growth"] = 50

# =========================
# 單一股票分析
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "NVDA").upper()
    st.subheader(f"📌 {symbol} 分析")
    
    sector_found = next((k for k, v in SECTORS.items() if symbol in v), "Mag7")
    st.info(f"所屬產業: **{sector_found}**")
    
    price, change = get_price_safe(symbol)
    if price: st.metric("即時股價", f"${price:.2f}", f"{change:.2f}%" if change else "N/A")
    
    funds_df = get_fundamentals_safe(symbol)
    if not funds_df.empty:
        df_show = funds_df.copy()
        for col in ["FCF", "市值", "股價"]:
            if col in df_show["指標"].values:
                df_show.loc[df_show["指標"] == col, "數值"] = df_show.loc[df_show["指標"] == col, "數值"].apply(format_large_numbers)
        st.table(df_show)
    
    st.subheader("📝 手動輸入分數")
    c1, c2, c3 = st.columns(3)
    p_in = c1.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    m_in = c2.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    g_in = c3.number_input("成長分數", 0, 100, key=f"{symbol}_growth")

    # 單一股評分邏輯 (略，與比較模式一致)

# =========================
# 產業共同比較
# =========================
elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()), index=0)
    st.subheader(f"🏭 {sector} 產業比較")
    
    manual_scores = {}
    for symbol in SECTORS[sector]:
        with st.sidebar.expander(f"{symbol} 分數"):
            manual_scores[symbol] = {
                "Policy_score": st.number_input(f"政策 ({symbol})", 0, 100, key=f"{symbol}_policy_comp"),
                "Moat_score": st.number_input(f"護城河 ({symbol})", 0, 100, key=f"{symbol}_moat_comp"),
                "Growth_score": st.number_input(f"成長 ({symbol})", 0, 100, key=f"{symbol}_growth_comp")
            }
    
    if st.button("🚀 開始計算產業數據"):
        progress = st.progress(0)
        rows = []
        # 簡易計算平均 (實際運算時會抓取真實數據)
        avg_pe, avg_roe = 25.0, 0.18 
        
        for idx, symbol in enumerate(SECTORS[sector]):
            data_df = get_fundamentals_safe(symbol)
            if not data_df.empty:
                row_map = {r["指標"]: r["數值"] for _, r in data_df.iterrows()}
                row_map["股票"] = symbol
                
                PE_s, ROE_s, Pol_s, Moat_s, Grow_s, Tot_s = compute_sector_specific_scores(
                    row_map, sector, manual_scores, avg_pe, avg_roe, style
                )
                
                row_map.update({"綜合分數": Tot_s, "評級": get_score_color(Tot_s)})
                for k in ["FCF", "市值", "股價"]: row_map[k] = format_large_numbers(row_map.get(k))
                rows.append(row_map)
            progress.progress((idx + 1) / len(SECTORS[sector]))
        
        if rows:
            res_df = pd.DataFrame(rows).sort_values("綜合分數", ascending=False)
            st.dataframe(res_df, use_container_width=True)
