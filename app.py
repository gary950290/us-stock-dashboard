import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# Page Config
# =========================
st.set_page_config(page_title="美股分析儀表板（專業投資版）", layout="wide")
st.title("📊 美股分析儀表板（股價優先・雙層分析）")

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
# 投資風格權重
# =========================
WEIGHTS = {
    "穩健型":{"Valuation":0.35,"Quality":0.35,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "平衡型":{"Valuation":0.3,"Quality":0.25,"Policy":0.15,"Moat":0.2,"Growth":0.1},
    "成長型":{"Valuation":0.2,"Quality":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3}
}

# =========================
# Sidebar
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("分析模式", ["單一股票分析", "產業共同比較"])
style = st.sidebar.selectbox("投資風格", list(WEIGHTS.keys()), index=1)

# =========================
# 工具函數
# =========================
def format_number(x):
    if x is None:
        return "-"
    if abs(x) >= 1e9:
        return f"{x/1e9:.2f} B"
    if abs(x) >= 1e6:
        return f"{x/1e6:.2f} M"
    return f"{x:.2f}"

def get_raw_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    return {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "FCF": info.get("freeCashflow"),
        "市值": info.get("marketCap"),
        "NetDebt": info.get("netDebt"),
        "EBITDA": info.get("ebitda")
    }

# =========================
# 評分核心（進階版）
# =========================
def valuation_score(pe, sector_pe):
    if not pe or not sector_pe:
        return 50
    ratio = pe / sector_pe
    return max(0, min(100, (1.5 - ratio) / 1.0 * 100))

def quality_score(roe, fcf, mktcap, netdebt, ebitda):
    score = 0
    if roe:
        score += min(roe / 0.25 * 60, 60)
    if fcf and mktcap and fcf > 0:
        score += min((fcf / mktcap) * 100 * 20, 20)
    if netdebt and ebitda and netdebt / ebitda > 3:
        score *= 0.8
    return round(score, 2)

def total_score(scores, style):
    w = WEIGHTS[style]
    return round(sum(scores[k] * w[k] for k in w), 2)

# =========================
# Session State 初始化
# =========================
for sector in SECTORS.values():
    for s in sector:
        st.session_state.setdefault(f"{s}_policy", 50)
        st.session_state.setdefault(f"{s}_moat", 50)
        st.session_state.setdefault(f"{s}_growth", 50)

# =========================
# 單一股票分析
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("股票代碼", "NVDA").upper()
    raw = get_raw_fundamentals(symbol)

    st.subheader(f"📌 {symbol}｜即時股價")
    if raw["股價"]:
        st.metric("股價", f"${raw['股價']:.2f}")

    st.subheader("📄 財報數據")
    display_df = pd.DataFrame({
        "項目": raw.keys(),
        "數值": [format_number(v) for v in raw.values()]
    })
    st.table(display_df)

    st.subheader("✍️ 手動調整分數")
    st.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
    st.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
    st.number_input("成長分數", 0, 100, key=f"{symbol}_growth")

    sector_pe = raw["PE"]  # 單股暫以自身為基準
    scores = {
        "Valuation": valuation_score(raw["PE"], sector_pe),
        "Quality": quality_score(raw["ROE"], raw["FCF"], raw["市值"], raw["NetDebt"], raw["EBITDA"]),
        "Policy": st.session_state[f"{symbol}_policy"],
        "Moat": st.session_state[f"{symbol}_moat"],
        "Growth": st.session_state[f"{symbol}_growth"]
    }

    st.subheader("🏁 最終評分")
    st.metric("綜合分數", total_score(scores, style))

# =========================
# 產業共同比較
# =========================
else:
    sector = st.sidebar.selectbox("選擇產業", SECTORS.keys())
    rows = []

    sector_pes = []
    for s in SECTORS[sector]:
        pe = yf.Ticker(s).info.get("trailingPE")
        if pe:
            sector_pes.append(pe)
    sector_pe_avg = sum(sector_pes) / len(sector_pes) if sector_pes else None

    for s in SECTORS[sector]:
        raw = get_raw_fundamentals(s)
        scores = {
            "Valuation": valuation_score(raw["PE"], sector_pe_avg),
            "Quality": quality_score(raw["ROE"], raw["FCF"], raw["市值"], raw["NetDebt"], raw["EBITDA"]),
            "Policy": st.session_state[f"{s}_policy"],
            "Moat": st.session_state[f"{s}_moat"],
            "Growth": st.session_state[f"{s}_growth"]
        }
        rows.append({
            "股票": s,
            "股價": raw["股價"],
            "綜合分數": total_score(scores, style),
            **scores
        })

    df = pd.DataFrame(rows).sort_values("綜合分數", ascending=False)
    df["股價"] = df["股價"].apply(lambda x: f"${x:.2f}" if x else "-")
    st.dataframe(df, use_container_width=True)
