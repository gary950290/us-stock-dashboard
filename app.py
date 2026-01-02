import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 1. 基本設定
# =========================
st.set_page_config(page_title="美股 AI 智慧分析儀表板", layout="wide")
st.title("📊 美股分析儀表板 (2026 產業模式校準版)")

# =========================
# 2. 產業配置與專屬評分細節 (統一變數名稱)
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
    },
    "NeoCloud": {
        "mode": "SaaS",
        "val_metric": "PS",
        "desc": "側重主權雲端政策與 AI 算力需求。",
        "stocks": ["NBIS", "IREN", "CRWV", "APLD"]
    }
}

# 2026 預校準初始值 (存入 Session State 的初始參考)
PRESET_DATA = {
    "CRWD": {"policy": 91, "moat": 94, "growth": 86},
    "PANW": {"policy": 89, "moat": 90, "growth": 80},
    "ZS":   {"policy": 90, "moat": 87, "growth": 83},
    "FTNT": {"policy": 87, "moat": 88, "growth": 79},
    "NVDA": {"policy": 92, "moat": 95, "growth": 90},
    "TSM":  {"policy": 85, "moat": 96, "growth": 82},
}

# =========================
# 3. 側邊欄與權重設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式", ["產業共同比較", "單一股票分析"])
style = st.sidebar.selectbox("投資風格", ["穩健型", "成長型", "平衡型"], index=2)

WEIGHTS = {
    "穩健型": {"PE": 0.4, "ROE": 0.3, "Policy": 0.1, "Moat": 0.2, "Growth": 0.0},
    "成長型": {"PE": 0.2, "ROE": 0.2, "Policy": 0.2, "Moat": 0.1, "Growth": 0.3},
    "平衡型": {"PE": 0.3, "ROE": 0.2, "Policy": 0.2, "Moat": 0.2, "Growth": 0.1}
}

# =========================
# 4. 快取與工具函數
# =========================
@st.cache_data
def get_fundamentals(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
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
        if value >= 1e12: return f"{value/1e12:.2f} T"
        elif value >= 1e9: return f"{value/1e9:.2f} B"
        elif value >= 1e6: return f"{value/1e6:.2f} M"
        else: return f"{value:.2f}"
    return value

# =========================
# 5. 初始化 Session State (確保手動輸入可運作)
# =========================
for s_cfg in SECTOR_CONFIG.values():
    for symbol in s_cfg["stocks"]:
        preset = PRESET_DATA.get(symbol, {})
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = preset.get("policy", 50)
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"] = preset.get("moat", 50)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = preset.get("growth", 50)

# =========================
# 6. 核心評分邏輯 (動態指標 + 縮尾修正)
# =========================
def compute_scores(row, manual_scores, sector_avg_pe, sector_avg_roe, sector_mode):
    symbol = row["股票"]
    
    # 1. 估值分 (Valuation)
    PE = row.get("PE")
    PS = row.get("PS")
    RevG = row.get("RevGrowth", 0.1)
    Val_score = 50
    if sector_mode == "SaaS":
        psg = PS / (RevG * 100) if (PS and RevG) else 1
        Val_score = max(0, min(100, (1.5 / psg) * 50))
    elif PE and sector_avg_pe:
        Val_score = max(0, min(100, (sector_avg_pe / PE) * 50))
    
    # 2. 品質分 (ROE 縮尾修正)
    ROE = row.get("ROE")
    Qual_score = 50
    if ROE is not None:
        adj_roe = min(ROE, 1.0) # 修正：ROE 最高計為 100%
        Qual_score = min(max(adj_roe / 0.2 * 100, 0), 100) # 以 20% 為滿分基準
    if row.get("FCF") and row["FCF"] < 0:
        Qual_score *= 0.8 # FCF 為負則打 8 折
    
    # 3. 獲取手動輸入分數 (從 session_state 獲取)
    p_s = manual_scores[symbol]["Policy_score"]
    m_s = manual_scores[symbol]["Moat_score"]
    g_s = manual_scores[symbol]["Growth_score"]
    
    w = WEIGHTS[style]
    Total_score = (Val_score*w["PE"] + Qual_score*w["ROE"] + p_s*w["Policy"] +
                   m_s*w["Moat"] + g_s*w["Growth"])
    
    return round(Val_score, 1), round(Qual_score, 1), p_s, m_s, g_s, round(Total_score, 2)

# =========================
# 7. UI 頁面邏輯
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "CRWD").upper()
    st.subheader(f"📌 {symbol} 深度分析 (2026 校準模式)")
    
    # 手動輸入區域
    c1, c2, c3 = st.columns(3)
    p_in = c1.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    m_in = c2.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    g_in = c3.number_input("成長分數", 0, 100, key=f"{symbol}_growth")

    try:
        funds_df = get_fundamentals(symbol)
        d = dict(zip(funds_df["指標"], funds_df["數值"])); d["股票"] = symbol
        
        # 自動判斷產業模式
        cur_mode = "Mature"
        for s_n, cfg in SECTOR_CONFIG.items():
            if symbol in cfg["stocks"]: cur_mode = cfg["mode"]; break

        m_scores = {symbol: {"Policy_score": p_in, "Moat_score": m_in, "Growth_score": g_in}}
        v_s, q_s, p_s, m_s, g_s, total = compute_scores(d, m_scores, 35, 0.2, cur_mode)
        
        st.metric("綜合評分", total)
        st.table(funds_df.assign(數值=funds_df['數值'].apply(format_large_numbers)))
    except:
        st.error("請確認代碼是否正確或網路連接正常")

elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTOR_CONFIG.keys()), index=0)
    cfg = SECTOR_CONFIG[sector]
    st.subheader(f"🏭 {sector} 產業比較 | 評估細節：{cfg['desc']}")
    
    # 側邊欄手動輸入
    manual_scores = {}
    st.sidebar.markdown("---")
    st.sidebar.subheader("✍️ 評分微調")
    for symbol in cfg["stocks"]:
        with st.sidebar.expander(f"{symbol} 分數設定"):
            p = st.number_input("政策", 0, 100, key=f"{symbol}_policy")
            m = st.number_input("護城河", 0, 100, key=f"{symbol}_moat")
            g = st.number_input("成長", 0, 100, key=f"{symbol}_growth")
            manual_scores[symbol] = {"Policy_score": p, "Moat_score": m, "Growth_score": g}

    # 計算平均值
    rows, pe_l, roe_l = [], [], []
    with st.spinner("抓取同業數據中..."):
        for s in cfg["stocks"]:
            try:
                data = get_fundamentals(s)
                d = dict(zip(data["指標"], data["數值"]))
                if d.get("PE"): pe_l.append(d["PE"])
                if d.get("ROE"): roe_l.append(d["ROE"])
            except: pass
        
    avg_pe = sum(pe_l)/len(pe_l) if pe_l else 30
    avg_roe = sum(roe_l)/len(roe_l) if roe_l else 0.15

    # 計算綜合評分
    for s in cfg["stocks"]:
        try:
            df_s = get_fundamentals(s)
            row = dict(zip(df_s["指標"], df_s["數值"])); row["股票"] = s
            v_s, q_s, p_s, m_s, g_s, total = compute_scores(row, manual_scores, avg_pe, avg_roe, cfg["mode"])
            
            row.update({"估值分": v_s, "品質分": q_s, "政策分": p_s, "護城河": m_s, "成長分": g_s, "綜合分數": total})
            for col in ["FCF", "市值", "股價"]:
                if col in row: row[col] = format_large_numbers(row[col])
            rows.append(row)
        except: pass

    if rows:
        final_df = pd.DataFrame(rows).sort_values("綜合分數", ascending=False)
        st.dataframe(final_df, use_container_width=True)

# =========================
# 8. 腳註知識
# =========================
with st.expander("ℹ️ 產業評估說明"):
    st.markdown("""
    - **資安 (SaaS 模式)**：對於高成長但虧損的公司，自動切換至 **PSG** 估值邏輯，避免 PE 失真。
    - **縮尾處理**：ROE 超過 100% (如 FTNT) 會被修正為 100%，以維持評分系統穩定。
    - **2026 政策分**：初始分已根據最新聯邦資安預算與 2026 晶片法案補貼進度預填。
    """)
