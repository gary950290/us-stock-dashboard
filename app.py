import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json

# =========================

# Initialize Gemini API

# =========================

try:
gemini_key = st.secrets[“GEMINI_API_KEY”]
genai.configure(api_key=gemini_key)
model = genai.GenerativeModel(“gemini-1.5-flash”)
except Exception as e:
st.error(“找不到 GEMINI_API_KEY”)
st.stop()

# =========================

# Config

# =========================

st.set_page_config(page_title=“2026 專業美股投資評比系統”, layout=“wide”)
st.title(“2026 專業美股投資評比系統”)
st.caption(“基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板”)

# =========================

# Stock Sectors

# =========================

SECTORS = {
“Mag7”: [“AAPL”,“MSFT”,“GOOGL”,“AMZN”,“META”,“NVDA”,“TSLA”],
“資安”: [“CRWD”,“PANW”,“ZS”,“OKTA”,“FTNT”,“S”],
“半導體”: [“NVDA”,“AMD”,“INTC”,“TSM”,“AVGO”],
“能源”: [“TSLA”,“CEG”,“FLNC”,“TE”,“NEE”,“ENPH”,“EOSE”,“VST”,“PLUG”,“OKLO”,“SMR”,“BE”,“GEV”],
“NeoCloud”: [“NBIS”,“IREN”,“CRWV”,“APLD”]
}

# =========================

# Sector Config

# =========================

SECTOR_CONFIG = {
“Mag7”: {
“weights”: {“Valuation”: 0.25, “Quality”: 0.25, “Growth”: 0.30, “MoatPolicy”: 0.20},
“focus”: “AI 變現效率與現金流”
},
“資安”: {
“weights”: {“Valuation”: 0.20, “Quality”: 0.30, “Growth”: 0.30, “MoatPolicy”: 0.20},
“focus”: “毛利率與平台定價權”
},
“能源”: {
“weights”: {“Valuation”: 0.15, “Quality”: 0.35, “Growth”: 0.15, “MoatPolicy”: 0.35},
“focus”: “FCF 與政策補貼”
},
“半導體”: {
“weights”: {“Valuation”: 0.30, “Quality”: 0.25, “Growth”: 0.30, “MoatPolicy”: 0.15},
“focus”: “前瞻盈餘與製程領先”
},
“NeoCloud”: {
“weights”: {“Valuation”: 0.10, “Quality”: 0.15, “Growth”: 0.60, “MoatPolicy”: 0.15},
“focus”: “未來規模與成長寬容度”
}
}

# =========================

# Initialize Session State

# =========================

if “weights” not in st.session_state:
st.session_state.weights = {s: SECTOR_CONFIG[s][“weights”].copy() for s in SECTORS.keys()}

if “manual_scores” not in st.session_state:
st.session_state.manual_scores = {}
for sector, stocks in SECTORS.items():
for stock in stocks:
st.session_state.manual_scores[stock] = {“Policy”: 50, “Moat”: 50}

# =========================

# Utility Functions

# =========================

@st.cache_data(ttl=300)
def get_stock_data(symbol):
try:
ticker = yf.Ticker(symbol)
return ticker.info
except:
return None

def get_tier(score):
if score >= 80:
return “Tier 1 (強烈優先配置)”
elif score >= 60:
return “Tier 2 (穩健配置)”
else:
return “Tier 3 (觀察或減碼)”

# =========================

# Scoring Engine

# =========================

def calculate_2026_score(info, sector, manual_scores, sector_avg_data):
symbol = info.get(“symbol”)

```
# 1. Valuation
fwd_pe = info.get("forwardPE")
avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
val_score = 50
if fwd_pe:
    val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
    if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9:
        val_score = min(100, val_score * 1.2)

# 2. Quality
roe = info.get("returnOnEquity", 0)
fcf = info.get("freeCashflow", 0)
gross_margin = info.get("grossMargins", 0)
op_margin = info.get("operatingMargins", 0)

qual_score = 50
if sector == "Mag7":
    qual_score = max(0, min(100, roe * 400))
elif sector == "資安":
    qual_score = max(0, min(100, gross_margin * 100))
    if gross_margin > 0.75: 
        qual_score += 20
elif sector == "能源":
    qual_score = 100 if fcf > 0 else 50
    if fcf < 0: 
        qual_score -= 50
elif sector == "半導體":
    qual_score = max(0, min(100, op_margin * 300))
elif sector == "NeoCloud":
    qual_score = 50
    
# 3. Growth
rev_growth = info.get("revenueGrowth", 0)
growth_score = max(0, min(100, rev_growth * 200))

if sector == "Mag7" and rev_growth > 0.2: 
    growth_score *= 1.2
if sector == "NeoCloud" and rev_growth > 0.4: 
    growth_score = 100

# 4. MoatPolicy
policy_score = manual_scores.get("Policy", 50)
moat_score = manual_scores.get("Moat", 50)
moat_policy_score = (policy_score + moat_score) / 2

# 5. Total Score
w = SECTOR_CONFIG[sector]["weights"]
total_score = (
    val_score * w["Valuation"] +
    qual_score * w["Quality"] +
    growth_score * w["Growth"] +
    moat_policy_score * w["MoatPolicy"]
)

# 6. Adjustments
final_adjustment = 0
if sector == "資安" and gross_margin > 0.75: 
    final_adjustment += 5
if (sector == "能源" or sector == "NeoCloud") and fcf < 0: 
    final_adjustment -= 10

total_score = max(0, min(100, total_score + final_adjustment))

return {
    "Total": round(total_score, 2),
    "Valuation": round(val_score, 2),
    "Quality": round(qual_score, 2),
    "Growth": round(growth_score, 2),
    "MoatPolicy": round(moat_policy_score, 2),
    "Policy": policy_score,
    "Moat": moat_score,
    "Adjustment": final_adjustment
}
```

# =========================

# AI Insights

# =========================

def get_ai_market_insight(symbol, sector, current_weights):
try:
ticker = yf.Ticker(symbol)
news = ticker.news[:5]
news_text = “\n”.join([f”- {n[‘title’]}” for n in news])

```
    prompt = f"""
```

你是一位資深美股分析師。請針對 {symbol} ({sector}產業) 的最新新聞進行 2026 投資評級分析：
{news_text}

請根據新聞內容，判斷對該公司的利好/利空影響，並建議是否需要微調以下權重（總和需為 1.0）：
{list(current_weights.keys())}

請嚴格以 JSON 格式回覆
“””
response = model.generate_content(prompt)
clean_json = response.text.replace(”`json", "").replace("`”, “”).strip()
return json.loads(clean_json)
except:
return None

# =========================

# UI Layout

# =========================

st.sidebar.header(“2026 評比設定”)
selected_sector = st.sidebar.selectbox(“選擇產業”, list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox(“選擇股票”, SECTORS[selected_sector])

# Manual Scores

st.sidebar.subheader(“手動評分”)
m_policy = st.sidebar.slider(
“政策受益度”,
0, 100,
st.session_state.manual_scores[selected_stock][“Policy”],
key=f”{selected_stock}_p”
)
m_moat = st.sidebar.slider(
“護城河粘性”,
0, 100,
st.session_state.manual_scores[selected_stock][“Moat”],
key=f”{selected_stock}_m”
)

# Update session state

st.session_state.manual_scores[selected_stock][“Policy”] = m_policy
st.session_state.manual_scores[selected_stock][“Moat”] = m_moat

if st.sidebar.button(“啟動 AI 實時新聞分析”):
with st.spinner(“Gemini 正在分析 2026 投資影響…”):
insight = get_ai_market_insight(selected_stock, selected_sector, st.session_state.weights[selected_sector])
if insight:
st.session_state.last_insight = insight
st.session_state.weights[selected_sector] = insight[“suggested_weights”]

# Display AI insights

if “last_insight” in st.session_state:
ins = st.session_state.last_insight
st.info(f”AI 2026 投資洞察 ({ins[‘sentiment’]})\n總結: {ins[‘summary’]}\n\n權重調整理由: {ins[‘reason’]}”)

# Get data and calculate

info = get_stock_data(selected_stock)
if info:
sector_avg_data = {“avg_fwd_pe”: 25}

```
scores = calculate_2026_score(
    info, 
    selected_sector, 
    st.session_state.manual_scores[selected_stock], 
    sector_avg_data
)

col1, col2, col3 = st.columns(3)
col1.metric("綜合評分", scores["Total"])
col2.metric("投資評級", get_tier(scores["Total"]))
col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))

st.subheader(f"{selected_sector} 評分維度 (焦點：{SECTOR_CONFIG[selected_sector]['focus']})")

# Detail table with manual scores
detail_data = pd.DataFrame({
    "維度": [
        "前瞻估值 (Valuation)", 
        "獲利質量 (Quality)", 
        "成長動能 (Growth)", 
        "政策與護城河 (MoatPolicy)",
        "└ 政策受益度 (手動)",
        "└ 護城河粘性 (手動)"
    ],
    "得分": [
        scores["Valuation"], 
        scores["Quality"], 
        scores["Growth"], 
        scores["MoatPolicy"],
        scores["Policy"],
        scores["Moat"]
    ],
    "權重": [
        st.session_state.weights[selected_sector]["Valuation"],
        st.session_state.weights[selected_sector]["Quality"],
        st.session_state.weights[selected_sector]["Growth"],
        st.session_state.weights[selected_sector]["MoatPolicy"],
        "-",
        "-"
    ]
})
st.table(detail_data)

if scores["Adjustment"] != 0:
    st.warning(f"觸發懲罰/加成機制：總分已調整 {scores['Adjustment']} 分")

# Sector comparison
with st.expander(f"查看 {selected_sector} 產業橫向排序"):
    results = []
    for s in SECTORS[selected_sector]:
        s_info = get_stock_data(s)
        if s_info:
            s_scores = calculate_2026_score(
                s_info, 
                selected_sector, 
                st.session_state.manual_scores[s], 
                sector_avg_data
            )
            results.append({
                "股票": s,
                "綜合分數": s_scores["Total"],
                "評級": get_tier(s_scores["Total"]),
                "Fwd PE": s_info.get("forwardPE"),
                "FCF": s_info.get("freeCashflow"),
                "政策分數": s_scores["Policy"],
                "護城河分數": s_scores["Moat"]
            })
    st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False))
```

else:
st.error(“無法獲取股票數據”)
