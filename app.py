import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股 AI 智慧分析儀表板", layout="wide")
st.title("📊 美股分析儀表板 (2026 產業模式切換版)")

# =========================
# 產業配置與專屬評分細節 (新增)
# =========================
# 這裡定義不同產業該看 PE 還是 PS，以及 2026 的政策權重方向
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

# 2026 預校準分數 (Policy/Moat/Growth)
PRESET_DATA = {
    "CRWD": {"policy": 91, "moat": 94, "growth": 86},
    "PANW": {"policy": 89, "moat": 90, "growth": 80},
    "ZS":   {"policy": 90, "moat": 87, "growth": 83},
    "FTNT": {"policy": 87, "moat": 88, "growth": 79},
    "NVDA": {"policy": 92, "moat": 95, "growth": 90},
    "TSM":  {"policy": 85, "moat": 96, "growth": 82},
}

# =========================
# 護城河資料
# ==========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
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

def calculate_moat(symbol):
    if symbol in PRESET_DATA: return PRESET_DATA[symbol]["moat"]
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.6, "switching":0.5, "patent":0.5, "network":0.5})
    return round(sum([data.get(k, 0.5) * MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS]) * 100, 2)

# =========================
# 核心評分邏輯 (動態調整)
# =========================
def compute_scores(row, manual_scores=None, sector_avg_pe=None, sector_avg_roe=None, sector_mode="Mature"):
    # 1. 估值分 (Valuation Score)
    PE = row.get("PE")
    PS = row.get("PS")
    RevG = row.get("RevGrowth", 0.1)
    PE_score = 50
    
    if sector_mode == "SaaS":
        # 對於 SaaS，PE 往往失效，改用 PSG (PS / Growth) 邏輯轉換
        psg = PS / (RevG * 100) if (PS and RevG) else 1
        PE_score = max(0, min(100, (1.5 / psg) * 50)) # 基準 PSG 1.5 給 50 分
    elif PE and sector_avg_pe:
        PE_score = max(0, min(100, (sector_avg_pe / PE) * 50))
    
    # 2. 品質分 (ROE Score - 增加縮尾處理)
    ROE = row.get("ROE")
    ROE_score = 50
    if ROE is not None and sector_avg_roe is not None:
        # 修正：ROE 進行縮尾 (Cap at 100%) 防止 FTNT 等異常值
        adjusted_roe = min(ROE, 1.0) 
        ROE_score = min(max(adjusted_roe / 0.2 * 100, 0), 100) # 以 20% ROE 為滿分基準
    
    # FCF 負值懲罰
    FCF = row.get("FCF")
    if isinstance(FCF, (int, float)) and FCF < 0:
        ROE_score *= 0.8
    
    symbol = row["股票"]
    
    # 3. 獲取手動分數 (優先使用預校準值)
    preset = PRESET_DATA.get(symbol, {"policy": 50, "growth": 50})
    Policy_score = preset["policy"]
    Moat_score = calculate_moat(symbol)
    Growth_score = preset["growth"]
    
    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score", Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score", Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score", Growth_score)
    
    w = WEIGHTS[style]
    Total_score = round(PE_score*w["PE"] + ROE_score*w["ROE"] + Policy_score*w["Policy"] +
                        Moat_score*w["Moat"] + Growth_score*w["Growth"], 2)
    
    return PE_score, ROE_score, Policy_score, Moat_score, Growth_score, Total_score

# =========================
# 初始化 Session State
# =========================
for s_cfg in SECTOR_CONFIG.values():
    for symbol in s_cfg["stocks"]:
        preset = PRESET_DATA.get(symbol, {"policy": 50, "moat": 50, "growth": 50})
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = preset.get("policy", 50)
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = preset.get("growth", 50)

# =========================
# UI 邏輯
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "CRWD").upper()
    st.subheader(f"📌 {symbol} 深度分析 (2026 校準版)")
    
    # 判斷產業模式
    current_mode = "Mature"
    for s_n, cfg in SECTOR_CONFIG.items():
        if symbol in cfg["stocks"]:
            current_mode = cfg["mode"]
            st.info(f"檢測到產業：{s_n} | 評估模式：{current_mode}")
            break

    try:
        funds_df = get_fundamentals(symbol)
        st.table(funds_df.assign(數值=funds_df['數值'].apply(format_large_numbers)))
        
        # 獲取數值進行評分
        d = dict(zip(funds_df["指標"], funds_df["數值"]))
        d["股票"] = symbol
        ps_val, roe_val, pol_s, moat_s, gro_s, total = compute_scores(d, sector_mode=current_mode, sector_avg_pe=35, sector_avg_roe=0.2)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("估值分 (PE/PSG)", round(ps_val,1))
        c2.metric("品質分 (ROE)", round(roe_val,1))
        c3.metric("政策分", pol_s)
        c4.metric("綜合評分", total)
    except:
        st.error("無法取得該股票數據")

elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTOR_CONFIG.keys()), index=0)
    cfg = SECTOR_CONFIG[sector]
    st.subheader(f"🏭 {sector} 產業比較分析")
    st.caption(f"💡 評估細節：{cfg['desc']}")
    
    # 側邊欄分數微調
    st.sidebar.markdown("---")
    st.sidebar.subheader("手動調整")
    manual_scores = {}
    for symbol in cfg["stocks"]:
        with st.sidebar.expander(f"{symbol} 評分"):
            p = st.number_input("政策", 0, 100, key=f"{symbol}_policy")
            g = st.number_input("成長", 0, 100, key=f"{symbol}_growth")
            manual_scores[symbol] = {"Policy_score": p, "Growth_score": g}

    # 抓取數據與計算
    rows = []
    pe_list, roe_list = [], []
    
    # 第一遍：抓取平均值
    for symbol in cfg["stocks"]:
        try:
            df = get_fundamentals(symbol)
            d = dict(zip(df["指標"], df["數值"]))
            if d.get("PE"): pe_list.append(d["PE"])
            if d.get("ROE"): roe_list.append(d["ROE"])
        except: pass
        
    avg_pe = sum(pe_list)/len(pe_list) if pe_list else 30
    avg_roe = sum(roe_list)/len(roe_list) if roe_list else 0.15

    # 第二遍：計算評分
    for symbol in cfg["stocks"]:
        try:
            df = get_fundamentals(symbol)
            row = dict(zip(df["指標"], df["數值"]))
            row["股票"] = symbol
            
            p_s, r_s, pol_s, m_s, g_s, total = compute_scores(
                row, manual_scores, avg_pe, avg_roe, sector_mode=cfg["mode"]
            )
            
            row.update({
                "估值分": p_s, "品質分": r_s, "政策分": pol_s, 
                "護城河": m_s, "成長分": g_s, "綜合分數": total
            })
            # 格式化
            for col in ["FCF", "市值", "股價"]:
                if col in row: row[col] = format_large_numbers(row[col])
            rows.append(row)
        except: pass

    if rows:
        res_df = pd.DataFrame(rows)[["股票", "股價", "PE", "ROE", "估值分", "品質分", "政策分", "護城河", "成長分", "綜合分數"]]
        st.dataframe(res_df.sort_values("綜合分數", ascending=False), use_container_width=True)

