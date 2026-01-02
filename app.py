import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股 AI 智慧分析儀表板", layout="wide")
st.title("📊 美股分析儀表板 (2026 產業模式切換版)")

# =========================
# 產業配置與專屬評分細節
# =========================
SECTOR_CONFIG = {
    "資安": {
        "mode": "SaaS",
        "val_metric": "PS/PSG",
        "desc": "側重政府零信任政策 (FedRAMP) 與營收成長效率 (Rule of 40)。",
        "stocks": ["CRWD", "PANW", "ZS", "OKTA", "FTNT", "S"]
    },
    "Mag7": {
        "mode": "Mature",
        "val_metric": "Forward PE",
        "desc": "側重 AI 基礎設施落地與反壟斷政策影響。",
        "stocks": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
    },
    "半導體": {
        "mode": "Growth",
        "val_metric": "Forward PE",
        "desc": "側重晶片法案補貼與出口管制政策風險。",
        "stocks": ["NVDA", "AMD", "INTC", "TSM", "AVGO"]
    },
    "能源": {
        "mode": "Value",
        "val_metric": "P/B or PE",
        "desc": "側重碳中和補貼與電網現代化政策。",
        "stocks": ["TSLA", "CEG", "FLNC", "VST", "GEV", "NEE"]
    }
}

# 2026 預校準初始值 (作為 Session State 的初始來源)
PRESET_DATA = {
    "CRWD": {"policy": 91, "moat": 94, "growth": 86},
    "PANW": {"policy": 89, "moat": 90, "growth": 80},
    "ZS":   {"policy": 90, "moat": 87, "growth": 83},
    "FTNT": {"policy": 87, "moat": 88, "growth": 79},
    "NVDA": {"policy": 92, "moat": 95, "growth": 90},
    "TSM":  {"policy": 85, "moat": 96, "growth": 82},
}

# 基礎護城河邏輯 (當無預設值時使用)
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
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
# 工具函數
# =========================
@st.cache_data
def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("forwardPE") or info.get("trailingPE"),
        "PS": info.get("priceToSalesTrailing12Months"),
        "ROE": info.get("returnOnEquity"),
        "RevGrowth": info.get("revenueGrowth", 0.1),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
    return pd.DataFrame(data.items(), columns=["指標", "數值"])

def format_large_numbers(value):
    if isinstance(value, (int, float)) and value is not None:
        if value >= 1e9: return f"{value/1e9:.2f} B"
        elif value >= 1e6: return f"{value/1e6:.2f} M"
        else: return f"{value:.2f}"
    return value

# =========================
# 初始化 Session State (整合預設值與手動權限)
# =========================
for s_cfg in SECTOR_CONFIG.values():
    for symbol in s_cfg["stocks"]:
        preset = PRESET_DATA.get(symbol, {})
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = preset.get("policy", 50)
        if f"{symbol}_moat" not in st.session_state:
            # 優先級：預設 > 護城河公式 > 50
            if symbol in PRESET_DATA:
                initial_moat = PRESET_DATA[symbol]["moat"]
            elif symbol in COMPANY_MOAT_DATA:
                d = COMPANY_MOAT_DATA[symbol]
                initial_moat = sum([d[k] * MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS]) * 100
            else:
                initial_moat = 50
            st.session_state[f"{symbol}_moat"] = float(initial_moat)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = preset.get("growth", 50)

# =========================
# 核心評分邏輯 (修正手動輸入優先級)
# =========================
def compute_scores(row, manual_scores, sector_avg_pe, sector_avg_roe, sector_mode):
    symbol = row["股票"]
    
    # 1. 估值分 (Valuation)
    PE = row.get("PE")
    PS = row.get("PS")
    RevG = row.get("RevGrowth", 0.1)
    PE_score = 50
    if sector_mode == "SaaS":
        psg = PS / (RevG * 100) if (PS and RevG) else 1
        PE_score = max(0, min(100, (1.5 / psg) * 50))
    elif PE and sector_avg_pe:
        PE_score = max(0, min(100, (sector_avg_pe / PE) * 50))
    
    # 2. 品質分 (ROE)
    ROE = row.get("ROE")
    ROE_score = 50
    if ROE is not None:
        adj_roe = min(ROE, 1.0) 
        ROE_score = min(max(adj_roe / 0.2 * 100, 0), 100)
    if row.get("FCF") and row["FCF"] < 0:
        ROE_score *= 0.8
    
    # 3. 獲取分數 (手動輸入優先)
    # 從 manual_scores (來自 session_state) 獲取最新值
    Policy_score = manual_scores[symbol]["Policy_score"]
    Moat_score = manual_scores[symbol]["Moat_score"]
    Growth_score = manual_scores[symbol]["Growth_score"]
    
    w = WEIGHTS[style]
    Total_score = (PE_score*w["PE"] + ROE_score*w["ROE"] + Policy_score*w["Policy"] +
                   Moat_score*w["Moat"] + Growth_score*w["Growth"])
    
    return PE_score, ROE_score, Policy_score, Moat_score, Growth_score, round(Total_score, 2)

# =========================
# UI 邏輯
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入代碼", "CRWD").upper()
    st.subheader(f"📌 {symbol} 深度分析")
    
    # 建立手動輸入介面並同步至 session_state
    c1, c2, c3 = st.columns(3)
    p_input = c1.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    m_input = c2.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    g_input = c3.number_input("成長分數", 0, 100, key=f"{symbol}_growth")

    try:
        df = get_fundamentals(symbol)
        d = dict(zip(df["指標"], df["數值"])); d["股票"] = symbol
        
        # 取得當前產業模式
        cur_mode = "Mature"
        for sn, cfg in SECTOR_CONFIG.items():
            if symbol in cfg["stocks"]: cur_mode = cfg["mode"]; break

        m_scores = {symbol: {"Policy_score": p_input, "Moat_score": m_input, "Growth_score": g_input}}
        res = compute_scores(d, m_scores, 35, 0.2, cur_mode)
        
        st.metric("綜合評分", res[5])
        st.table(df.assign(數值=df['數值'].apply(format_large_numbers)))
    except: st.error("數據獲取失敗")

elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()), index=1) # 預設資安
    cfg = SECTOR_CONFIG[sector]
    st.subheader(f"🏭 {sector} 產業比較 | 模式：{cfg['mode']}")
    
    # 側邊欄：手動輸入區
    manual_scores = {}
    st.sidebar.markdown("---")
    st.sidebar.subheader("✍️ 評分微調")
    for symbol in cfg["stocks"]:
        with st.sidebar.expander(f"{symbol} 分數設定"):
            p = st.number_input("政策", 0, 100, key=f"{symbol}_policy")
            m = st.number_input("護城河", 0, 100, key=f"{symbol}_moat")
            g = st.number_input("成長", 0, 100, key=f"{symbol}_growth")
            manual_scores[symbol] = {"Policy_score": p, "Moat_score": m, "Growth_score": g}

    # 計算平均與繪表
    rows = []; pe_l = []; roe_l = []
    for s in cfg["stocks"]:
        try:
            d = dict(zip(get_fundamentals(s)["指標"], get_fundamentals(s)["數值"]))
            if d.get("PE"): pe_l.append(d["PE"])
            if d.get("ROE"): roe_l.append(d["ROE"])
        except: pass
    
    avg_pe = sum(pe_l)/len(pe_l) if pe_l else 30
    avg_roe = sum(roe_l)/len(roe_l) if roe_l else 0.15

    for s in cfg["stocks"]:
        try:
            row = dict(zip(get_fundamentals(s)["指標"], get_fundamentals(s)["數值"])); row["股票"] = s
            v_s, q_s, p_s, m_s, g_s, total = compute_scores(row, manual_scores, avg_pe, avg_roe, cfg["mode"])
            row.update({"估值分": v_s, "品質分": q_s, "政策分": p_s, "護城河": m_s, "成長分": g_s, "綜合分數": total})
            for col in ["FCF", "市值", "股價"]:
                if col in row: row[col] = format_large_numbers(row[col])
            rows.append(row)
        except: pass

    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("綜合分數", ascending=False), use_container_width=True)
