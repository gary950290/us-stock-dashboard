import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（產業可調權重＋評分拆解）")

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
# 預設產業 scoring（會被 sidebar 覆蓋）
# =========================
DEFAULT_SECTOR_SCORING = {
    "Mag7":    {"PE":0.9,"ROE":1.0,"Policy":1.0,"Moat":1.1,"Growth":1.1},
    "資安":    {"PE":0.8,"ROE":1.1,"Policy":1.2,"Moat":1.1,"Growth":1.0},
    "半導體":  {"PE":1.0,"ROE":1.2,"Policy":1.0,"Moat":1.0,"Growth":1.2},
    "能源":    {"PE":1.1,"ROE":0.9,"Policy":1.3,"Moat":1.0,"Growth":1.0},
    "NeoCloud":{"PE":0.85,"ROE":1.0,"Policy":1.0,"Moat":1.0,"Growth":1.3}
}

# =========================
# 投資風格權重
# =========================
WEIGHTS = {
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1}
}

# =========================
# Sidebar：產業 scoring 可調
# =========================
st.sidebar.header("⚙️ 分析設定")
style = st.sidebar.selectbox("投資風格", list(WEIGHTS.keys()), index=2)
mode = st.sidebar.selectbox("模式", ["單一股票分析","產業共同比較"])

st.sidebar.markdown("### 🏭 產業評分權重（Multiplier）")

SECTOR_SCORING = {}
for sector, base in DEFAULT_SECTOR_SCORING.items():
    with st.sidebar.expander(sector):
        SECTOR_SCORING[sector] = {
            k: st.slider(
                f"{k}", 0.5, 1.5, base[k], 0.05,
                key=f"{sector}_{k}"
            )
            for k in base
        }

# =========================
# 資料工具
# =========================
@st.cache_data
def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    return {
        "PE": info.get("trailingPE"),
        "ROE": info.get("returnOnEquity"),
        "FCF": info.get("freeCashflow"),
        "市值": info.get("marketCap"),
        "股價": info.get("currentPrice")
    }

def compute_scores(row, sector, manual, sector_avg):
    explain = {}

    # ===== PE =====
    PE = row["PE"]
    if PE and sector_avg["PE"]:
        raw_pe = max(0, min(100, (sector_avg["PE"] - PE) / sector_avg["PE"] * 100))
    else:
        raw_pe = 50
    pe_score = raw_pe * SECTOR_SCORING[sector]["PE"]
    explain["PE"] = (PE, raw_pe, pe_score)

    # ===== ROE =====
    ROE = row["ROE"]
    if ROE and sector_avg["ROE"]:
        raw_roe = min(max(ROE / sector_avg["ROE"] * 100, 0), 100)
    else:
        raw_roe = 50
    if row["FCF"] and row["FCF"] < 0:
        raw_roe *= 0.8
    roe_score = raw_roe * SECTOR_SCORING[sector]["ROE"]
    explain["ROE"] = (ROE, raw_roe, roe_score)

    # ===== Manual =====
    policy = manual["Policy"] * SECTOR_SCORING[sector]["Policy"]
    moat = manual["Moat"] * SECTOR_SCORING[sector]["Moat"]
    growth = manual["Growth"] * SECTOR_SCORING[sector]["Growth"]

    explain["Policy"] = policy
    explain["Moat"] = moat
    explain["Growth"] = growth

    # ===== 加權 =====
    w = WEIGHTS[style]
    total = (
        pe_score * w["PE"] +
        roe_score * w["ROE"] +
        policy * w["Policy"] +
        moat * w["Moat"] +
        growth * w["Growth"]
    )
    total = total / (100 * sum(w.values())) * 100

    return round(total,2), explain

# =========================
# 單一股票分析
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("股票代碼","NVDA")
    sector = next((s for s,v in SECTORS.items() if symbol in v), None)

    if not sector:
        st.warning("不在既定產業池中")
        st.stop()

    data = get_fundamentals(symbol)

    manual = {
        "Policy": st.slider("政策分數",0,100,50),
        "Moat": st.slider("護城河分數",0,100,50),
        "Growth": st.slider("成長分數",0,100,50)
    }

    peers = [get_fundamentals(s) for s in SECTORS[sector]]
    sector_avg = {
        "PE": pd.Series([p["PE"] for p in peers if p["PE"]]).mean(),
        "ROE": pd.Series([p["ROE"] for p in peers if p["ROE"]]).mean()
    }

    total, explain = compute_scores(data, sector, manual, sector_avg)

    st.metric("綜合分數", total)

    with st.expander("🔍 評分拆解"):
        st.json(explain)

# =========================
# 產業共同比較
# =========================
else:
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    rows = []

    peers = [get_fundamentals(s) for s in SECTORS[sector]]
    sector_avg = {
        "PE": pd.Series([p["PE"] for p in peers if p["PE"]]).mean(),
        "ROE": pd.Series([p["ROE"] for p in peers if p["ROE"]]).mean()
    }

    for s in SECTORS[sector]:
        manual = {
            "Policy": st.sidebar.slider(f"{s} 政策",0,100,50),
            "Moat": st.sidebar.slider(f"{s} 護城河",0,100,50),
            "Growth": st.sidebar.slider(f"{s} 成長",0,100,50)
        }
        total, explain = compute_scores(get_fundamentals(s), sector, manual, sector_avg)
        rows.append({"股票":s,"綜合分數":total,"Explain":explain})

    df = pd.DataFrame(rows).sort_values("綜合分數",ascending=False)
    st.dataframe(df[["股票","綜合分數"]], use_container_width=True)

    with st.expander("🔍 各公司評分拆解"):
        st.json({r["股票"]:r["Explain"] for r in rows})
