import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime, timedelta

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（產業專屬評分 + 行業動態PE/ROE）")

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
# 護城河資料（擴充版）
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
    "CRWD":{"retention":0.88,"switching":0.82,"patent":0.75,"network":0.8},
    "PANW":{"retention":0.85,"switching":0.8,"patent":0.78,"network":0.75},
    "ZS":{"retention":0.82,"switching":0.78,"patent":0.7,"network":0.8},
    "OKTA":{"retention":0.8,"switching":0.75,"patent":0.65,"network":0.75},
    "FTNT":{"retention":0.83,"switching":0.77,"patent":0.72,"network":0.7},
    "S":{"retention":0.78,"switching":0.72,"patent":0.68,"network":0.72},
    # 半導體
    "AMD":{"retention":0.82,"switching":0.75,"patent":0.88,"network":0.7},
    "INTC":{"retention":0.8,"switching":0.72,"patent":0.85,"network":0.68},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.92,"network":0.75},
    "AVGO":{"retention":0.85,"switching":0.78,"patent":0.9,"network":0.73},
    # 能源
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
    # NeoCloud
    "NBIS":{"retention":0.65,"switching":0.6,"patent":0.55,"network":0.7},
    "IREN":{"retention":0.63,"switching":0.58,"patent":0.52,"network":0.68},
    "CRWV":{"retention":0.62,"switching":0.57,"patent":0.5,"network":0.67},
    "APLD":{"retention":0.64,"switching":0.59,"patent":0.53,"network":0.69},
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)

# 產業專屬權重配置
SECTOR_WEIGHTS = {
    "Mag7": {
        "穩健型":{"PE":0.35,"ROE":0.25,"Policy":0.15,"Moat":0.2,"Growth":0.05},
        "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.15,"Growth":0.25},
        "平衡型":{"PE":0.28,"ROE":0.22,"Policy":0.18,"Moat":0.18,"Growth":0.14}
    },
    "資安": {
        "穩健型":{"PE":0.3,"ROE":0.25,"Policy":0.2,"Moat":0.15,"Growth":0.1},
        "成長型":{"PE":0.15,"ROE":0.2,"Policy":0.25,"Moat":0.1,"Growth":0.3},
        "平衡型":{"PE":0.25,"ROE":0.22,"Policy":0.23,"Moat":0.13,"Growth":0.17}
    },
    "半導體": {
        "穩健型":{"PE":0.35,"ROE":0.3,"Policy":0.15,"Moat":0.15,"Growth":0.05},
        "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
        "平衡型":{"PE":0.28,"ROE":0.25,"Policy":0.18,"Moat":0.13,"Growth":0.16}
    },
    "能源": {
        "穩健型":{"PE":0.25,"ROE":0.2,"Policy":0.35,"Moat":0.15,"Growth":0.05},
        "成長型":{"PE":0.15,"ROE":0.15,"Policy":0.3,"Moat":0.1,"Growth":0.3},
        "平衡型":{"PE":0.2,"ROE":0.18,"Policy":0.32,"Moat":0.13,"Growth":0.17}
    },
    "NeoCloud": {
        "穩健型":{"PE":0.3,"ROE":0.25,"Policy":0.2,"Moat":0.1,"Growth":0.15},
        "成長型":{"PE":0.15,"ROE":0.2,"Policy":0.15,"Moat":0.05,"Growth":0.45},
        "平衡型":{"PE":0.23,"ROE":0.22,"Policy":0.18,"Moat":0.08,"Growth":0.29}
    }
}

# =========================
# 快取工具函數（改進版）
# =========================
@st.cache_data(ttl=300)  # 5分鐘快取
def get_price_safe(symbol, retry=3, delay=2):
    """安全獲取股價，帶重試機制"""
    for attempt in range(retry):
        try:
            info = yf.Ticker(symbol).info
            return info.get("currentPrice"), info.get("regularMarketChangePercent")
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))  # 遞增延遲
            else:
                st.warning(f"⚠️ {symbol}: 無法獲取股價")
                return None, None
    return None, None

@st.cache_data(ttl=300)
def get_fundamentals_safe(symbol, retry=3, delay=2):
    """安全獲取基本面數據，帶重試機制"""
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
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(delay * (attempt + 1))
            else:
                st.warning(f"⚠️ {symbol}: 無法獲取財報數據 - {str(e)}")
                return pd.DataFrame()
    return pd.DataFrame()

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

def compute_sector_specific_scores(row, sector, manual_scores=None, sector_avg_pe=None, sector_avg_roe=None, style="平衡型"):
    """
    根據產業特性計算專屬評分
    """
    PE = row.get("PE")
    ROE = row.get("ROE")
    FCF = row.get("FCF")
    revenue_growth = row.get("營收成長")
    gross_margin = row.get("毛利率")
    operating_margin = row.get("營業利潤率")
    symbol = row["股票"]
    
    # PE評分（動態比較）
    PE_score = 50
    if PE is not None and sector_avg_pe is not None and sector_avg_pe > 0:
        if sector == "Mag7":
            PE_score = max(0, min(100, (sector_avg_pe - PE) / sector_avg_pe * 100))
        elif sector == "資安":
            PE_score = max(0, min(100, (sector_avg_pe * 1.2 - PE) / (sector_avg_pe * 1.2) * 100))
        elif sector == "半導體":
            PE_score = max(0, min(100, (sector_avg_pe - PE) / sector_avg_pe * 120))
        elif sector == "能源":
            PE_score = max(0, min(100, (sector_avg_pe - PE) / sector_avg_pe * 100))
        elif sector == "NeoCloud":
            PE_score = max(0, min(100, (sector_avg_pe * 1.5 - PE) / (sector_avg_pe * 1.5) * 100))
    
    # ROE評分（動態比較 + 產業特性）
    ROE_score = 50
    if ROE is not None and sector_avg_roe is not None and sector_avg_roe > 0:
        base_roe_score = min(max(ROE / sector_avg_roe * 100, 0), 100)
        
        if sector == "Mag7":
            ROE_score = base_roe_score * 1.1 if ROE > 0.2 else base_roe_score
        elif sector == "資安":
            ROE_score = base_roe_score * 1.05 if ROE > 0.15 else base_roe_score * 0.95
        elif sector == "半導體":
            ROE_score = base_roe_score
        elif sector == "能源":
            ROE_score = base_roe_score * 1.15 if ROE > 0.1 else base_roe_score * 0.9
        elif sector == "NeoCloud":
            ROE_score = base_roe_score * 0.9 if ROE and ROE < 0 else base_roe_score
        
        ROE_score = min(max(ROE_score, 0), 100)
    
    # FCF調整
    if FCF is not None and isinstance(FCF, (int, float)):
        if sector == "能源" or sector == "半導體":
            if FCF < 0:
                ROE_score *= 0.7
        elif sector == "資安" or sector == "NeoCloud":
            if FCF < 0:
                ROE_score *= 0.9
    
    # 利潤率加分
    if sector == "資安" and gross_margin and gross_margin > 0.7:
        ROE_score = min(ROE_score * 1.1, 100)
    if sector == "半導體" and operating_margin and operating_margin > 0.25:
        ROE_score = min(ROE_score * 1.08, 100)
    
    # 手動評分
    Policy_score = 50
    Moat_score = calculate_moat(symbol)
    Growth_score = 50
    
    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score", Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score", Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score", Growth_score)
    
    # 成長性額外調整
    if revenue_growth and revenue_growth > 0.3 and sector in ["資安", "NeoCloud"]:
        Growth_score = min(Growth_score * 1.15, 100)
    
    # 使用產業專屬權重
    w = SECTOR_WEIGHTS.get(sector, {}).get(style, SECTOR_WEIGHTS["Mag7"][style])
    
    Total_score = round(
        PE_score * w["PE"] + 
        ROE_score * w["ROE"] + 
        Policy_score * w["Policy"] + 
        Moat_score * w["Moat"] + 
        Growth_score * w["Growth"], 
        2
    )
    
    return round(PE_score, 2), round(ROE_score, 2), round(Policy_score, 2), round(Moat_score, 2), round(Growth_score, 2), Total_score

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
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "NVDA")
    st.subheader(f"📌 {symbol} 分析")
    
    sector_found = None
    for sector_name, stocks in SECTORS.items():
        if symbol in stocks:
            sector_found = sector_name
            break
    
    if sector_found:
        st.info(f"所屬產業: **{sector_found}**")
    
    # 獲取股價
    price, change = get_price_safe(symbol)
    
    if price is not None:
        st.metric("即時股價", f"${price:.2f}", f"{change:.2f}%" if change else "N/A")
    else:
        st.warning("無法獲取即時股價")
    
    # 獲取財報數據
    funds_df = get_fundamentals_safe(symbol)
    
    if not funds_df.empty:
        for col in ["FCF", "市值", "股價"]:
            if col in funds_df["指標"].values:
                funds_df.loc[funds_df["指標"] == col, "數值"] = funds_df.loc[funds_df["指標"] == col, "數值"].apply(format_large_numbers)
        st.table(funds_df)
    else:
        st.warning("無法顯示財報數據")
    
    st.subheader("📝 手動輸入分數")
    col1, col2, col3 = st.columns(3)
    with col1:
        manual_policy = st.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    with col2:
        manual_moat = st.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    with col3:
        manual_growth = st.number_input("成長分數", 0, 100, key=f"{symbol}_growth")
    
    # 行業平均
    sector_avg_pe, sector_avg_roe = None, None
    if sector_found:
        pe_list = []
        roe_list = []
        for s in SECTORS[sector_found]:
            df = get_fundamentals_safe(s)
            if not df.empty:
                pe_val = df.loc[df["指標"] == "PE", "數值"].values
                roe_val = df.loc[df["指標"] == "ROE", "數值"].values
                if len(pe_val) > 0 and pe_val[0]: pe_list.append(pe_val[0])
                if len(roe_val) > 0 and roe_val[0]: roe_list.append(roe_val[0])
            time.sleep(0.5)  # 延遲避免頻率限制
        if pe_list: sector_avg_pe = sum(pe_list) / len(pe_list)
        if roe_list: sector_avg_roe = sum(roe_list) / len(roe_list)
    
    # 準備評分數據
    row = {"股票": symbol}
    if not funds_df.empty:
        for _, r in funds_df.iterrows():
            row[r["指標"]] = r["數值"]
    
    PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_sector_specific_scores(
        row,
        sector_found if sector_found else "Mag7",
        manual_scores={symbol: {"Policy_score": manual_policy, "Moat_score": manual_moat, "Growth_score": manual_growth}},
        sector_avg_pe=sector_avg_pe,
        sector_avg_roe=sector_avg_roe,
        style=style
    )
    
    st.subheader("📊 評分結果")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("PE評分", PE_s)
        st.metric("ROE評分", ROE_s)
    with col2:
        st.metric("政策評分", Policy_s)
        st.metric("護城河評分", Moat_s)
    with col3:
        st.metric("成長評分", Growth_s)
        st.metric("🎯 綜合分數", Total_s, delta=None)

# =========================
# 產業共同比較
# =========================
elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()), index=0)
    st.subheader(f"🏭 {sector} 產業比較")
    
    # 顯示產業專屬權重
    with st.expander("📋 查看產業專屬評分權重"):
        weights_df = pd.DataFrame(SECTOR_WEIGHTS[sector]).T
        st.dataframe(weights_df.style.format("{:.0%}"))
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("✏️ 手動輸入分數")
    
    manual_scores = {}
    for symbol in SECTORS[sector]:
        with st.sidebar.expander(f"{symbol}"):
            manual_policy = st.number_input(f"政策分數", 0, 100, key=f"{symbol}_policy")
            manual_moat = st.number_input(f"護城河分數", 0, 100, key=f"{symbol}_moat")
            manual_growth = st.number_input(f"成長分數", 0, 100, key=f"{symbol}_growth")
            manual_scores[symbol] = {
                "Policy_score": st.session_state[f"{symbol}_policy"],
                "Moat_score": st.session_state[f"{symbol}_moat"],
                "Growth_score": st.session_state[f"{symbol}_growth"]
            }
    
    # 顯示進度條
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 計算行業平均 PE/ROE
    status_text.text("正在計算產業平均值...")
    pe_list = []
    roe_list = []
    total_stocks = len(SECTORS[sector])
    
    for idx, s in enumerate(SECTORS[sector]):
        df = get_fundamentals_safe(s)
        if not df.empty:
            pe_val = df.loc[df["指標"] == "PE", "數值"].values
            roe_val = df.loc[df["指標"] == "ROE", "數值"].values
            if len(pe_val) > 0 and pe_val[0]: pe_list.append(pe_val[0])
            if len(roe_val) > 0 and roe_val[0]: roe_list.append(roe_val[0])
        progress_bar.progress((idx + 1) / total_stocks)
        time.sleep(0.8)  # 延遲避免頻率限制
    
    sector_avg_pe = sum(pe_list) / len(pe_list) if pe_list else None
    sector_avg_roe = sum(roe_list) / len(roe_list) if roe_list else None
    
    progress_bar.empty()
    status_text.empty()
    
    if sector_avg_pe:
        st.info(f"📊 產業平均 PE: {sector_avg_pe:.2f}")
    if sector_avg_roe:
        st.info(f"📊 產業平均 ROE: {sector_avg_roe*100:.2f}%")
    
    # 收集所有股票數據
    status_text.text("正在分析各股票...")
    progress_bar = st.progress(0)
    
    rows = []
    for idx, symbol in enumerate(SECTORS[sector]):
        row = {"股票": symbol}
        df = get_fundamentals_safe(symbol)
        
        if not df.empty:
            for _, r in df.iterrows():
                row[r["指標"]] = r["數值"]
            
            PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_sector_specific_scores(
                row, sector, manual_scores, sector_avg_pe, sector_avg_roe, style
            )
            
            row["PE評分"] = PE_s
            row["ROE評分"] = ROE_s
            row["政策評分"] = Policy_s
            row["護城河評分"] = Moat_s
            row["成長評分"] = Growth_s
            row["綜合分數"] = Total_s
            
            for col in ["FCF", "市值", "股價"]:
                if col in row:
                    row[col] = format_large_numbers(row[col])
            
            rows.append(row)
        
        progress_bar.progress((idx + 1) / total_stocks)
        time.sleep(0.8)  # 延遲避免頻率限制
    
    progress_bar.empty()
    status_text.empty()
    
    if rows:
        result_df = pd.DataFrame(rows)
        result_df = result_df.sort_values("綜合分數", ascending=False)
        
        # 顯示完整表格
        st.dataframe(
            result_df.style.background_gradient(subset=["綜合分數"], cmap="RdYlGn", vmin=0, vmax=100),
            use_container_width=True
        )
        
        # 下載按鈕
        csv = result_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下載結果為CSV",
            data=csv,
            file_name=f"{sector}_分析結果.csv",
            mime="text/csv"
        )
    else:
        st.error("無法獲取任何股票數據，請稍後再試")

st.sidebar.markdown("---")
st.sidebar.info("💡 提示：如遇到請求限制，請等待幾分鐘後重試")
