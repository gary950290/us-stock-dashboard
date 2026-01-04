import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json
import re

# 設定重試次數
MAX_RETRIES = 3 

# =========================
# 初始化 Gemini API
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    # 使用 2026 環境支援的模型
    model = genai.GenerativeModel('gemini-2.0-flash-exp') # 確保模型名稱正確
except Exception as e:
    st.error("❌ 找不到 GEMINI_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 設定與 CSS 注入
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

st.markdown(
    """
    <style>
    .stApp { overflow-y: auto !important; max-height: 100vh; }
    div[data-testid^="stVerticalBlock"] { overflow-y: auto !important; }
    </style>
    """,
    unsafe_allow_html=True
)

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

SECTOR_CONFIG = {
    "Mag7": {"weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "AI 變現效率與現金流"},
    "資安": {"weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "毛利率與平台定價權"},
    "能源": {"weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35}, "focus": "FCF 與政策補貼"},
    "半導體": {"weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15}, "focus": "前瞻盈餘與製程領先"},
    "NeoCloud": {"weights": {"Valuation": 0.10, "Quality": 0.15, "Growth": 0.60, "MoatPolicy": 0.15}, "focus": "未來規模與成長寬容度"}
}

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info
    except:
        return None

def get_tier(score):
    if score >= 80: return "Tier 1 (強烈優先配置) 🚀"
    elif score >= 60: return "Tier 2 (穩健配置) ⚖️"
    else: return "Tier 3 (觀察或減碼) ⚠️"

def calculate_2026_score(info, sector, manual_scores, sector_avg_data, custom_weights):
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = 50
    if fwd_pe:
        val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
    
    roe = info.get("returnOnEquity", 0)
    fcf = info.get("freeCashflow", 0)
    gross_margin = info.get("grossMargins", 0)
    op_margin = info.get("operatingMargins", 0)
    
    qual_score = 50
    if sector == "Mag7": qual_score = max(0, min(100, roe * 400))
    elif sector == "能源": qual_score = 100 if fcf > 0 else 50
    
    rev_growth = info.get("revenueGrowth", 0)
    growth_score = max(0, min(100, rev_growth * 200))
    
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score) / 2
    
    w = custom_weights
    total_score = (
        val_score * w["Valuation"] +
        qual_score * w["Quality"] +
        growth_score * w["Growth"] +
        moat_policy_score * w["MoatPolicy"]
    )
    
    final_adjustment = 0
    if sector == "能源" and fcf < 0: final_adjustment -= 10
    total_score = max(0, min(100, total_score + final_adjustment))
    
    return {
        "Total": round(total_score, 2), "Valuation": round(val_score, 2),
        "Quality": round(qual_score, 2), "Growth": round(growth_score, 2),
        "MoatPolicy": round(moat_policy_score, 2), "Adjustment": final_adjustment
    }

# =========================
# AI 分析邏輯 (加強 JSON 穩定性)
# =========================
def get_ai_market_insight(symbol, sector, current_weights, status):
    ticker = yf.Ticker(symbol)
    news = ticker.news[:5]
    news_text = "\n".join([f"- {n['title']}" for n in news if 'title' in n]) or "無最新相關新聞。"
    
    prompt = f"""
    You are a professional stock analyst. Analyze {symbol} ({sector}) for the year 2026.
    Latest News: {news_text}
    Current Weights: {current_weights}
    
    Return ONLY a JSON object with the following structure:
    {{
        "sentiment": "利好" or "利空",
        "summary": "Short 2026 outlook",
        "suggested_weights": {{ "Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float }},
        "reason": "Why the change?"
    }}
    The sum of suggested_weights MUST be 1.0. 
    """
    
    delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            status.write(f"🤖 嘗試分析第 {attempt + 1} 次...")
            response = model.generate_content(prompt)
            
            # 使用 Regex 尋找 JSON 區塊
            match = re.search(r"\{.*\}", response.text, re.DOTALL)
            if match:
                clean_json = match.group(0)
                insight = json.loads(clean_json)
                return insight
            else:
                raise ValueError("無法在回應中找到 JSON 格式")
                
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay); delay *= 2
            else:
                status.error(f"❌ AI 解析失敗: {e}")
                return None
    return None

# =========================
# 主程式 UI
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

if "weights" not in st.session_state:
    st.session_state.weights = {}

if selected_stock not in st.session_state.weights:
    st.session_state.weights[selected_stock] = SECTOR_CONFIG[selected_sector]["weights"].copy()

# 手動評分
if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = {}

current_stock = selected_stock
if current_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[current_stock] = {"Policy": 50, "Moat": 50}

m_policy = st.sidebar.slider("政策受益度", 0, 100, value=st.session_state.manual_scores[current_stock]["Policy"], key=f"{current_stock}_p")
m_moat = st.sidebar.slider("護城河粘性", 0, 100, value=st.session_state.manual_scores[current_stock]["Moat"], key=f"{current_stock}_m")

if st.sidebar.button("🤖 啟動 AI 實時新聞分析"):
    with st.status("🤖 正在執行 AI 投資分析...", expanded=True) as status:
        insight = get_ai_market_insight(selected_stock, selected_sector, st.session_state.weights[selected_stock], status)
        if insight:
            st.session_state.last_insight = insight
            st.session_state.weights[selected_stock] = insight["suggested_weights"]
            status.update(label=f"✅ {selected_stock} 權重更新完成！", state="complete", expanded=False)

if "last_insight" in st.session_state:
    ins = st.session_state.last_insight
    st.info(f"### AI 2026 投資洞察 ({ins['sentiment']})\n**總結**: {ins['summary']}\n\n**理由**: {ins['reason']}")

# 數據顯示
info = get_stock_data(selected_stock)
if info:
    sector_avg_data = {"avg_fwd_pe": 25} 
    scores = calculate_2026_score(info, selected_sector, {"Policy": m_policy, "Moat": m_moat}, sector_avg_data, st.session_state.weights[selected_stock])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", scores["Total"])
    col2.metric("投資評級", get_tier(scores["Total"]))
    col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    
    st.subheader(f"📊 {selected_stock} 評分細節")
    detail_df = pd.DataFrame({
        "維度": ["估值", "質量", "成長", "政策"],
        "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
        "權重": [st.session_state.weights[selected_stock][k] for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
    })
    st.table(detail_df)

    with st.expander(f"🏭 {selected_sector} 產業對比"):
        results = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            if s_info:
                s_w = st.session_state.weights.get(s, SECTOR_CONFIG[selected_sector]["weights"])
                s_scores = calculate_2026_score(s_info, selected_sector, {"Policy": 50, "Moat": 50}, sector_avg_data, s_w)
                results.append({"股票": s, "分數": s_scores["Total"], "評級": get_tier(s_scores["Total"])})
        st.dataframe(pd.DataFrame(results).sort_values("分數", ascending=False))
else:
    st.error("無法獲取數據，請檢查 API 或代碼。")
