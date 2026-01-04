import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json

# 設定重試次數
MAX_RETRIES = 3 

# =========================
# 初始化 Gemini API
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    # 使用 2026 環境支援的模型
    model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
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

# 核心權重配置基準 (2026 預設)
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

# =========================
# 評分引擎 (修正：接收自定義權重參數)
# =========================
def calculate_2026_score(info, sector, manual_scores, sector_avg_data, custom_weights):
    symbol = info.get("symbol")
    
    # 1. 前瞻估值
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = 50
    if fwd_pe:
        val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
        if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9:
            val_score = min(100, val_score * 1.2)
    
    # 2. 獲利質量
    roe = info.get("returnOnEquity", 0)
    fcf = info.get("freeCashflow", 0)
    gross_margin = info.get("grossMargins", 0)
    op_margin = info.get("operatingMargins", 0)
    
    qual_score = 50
    if sector == "Mag7":
        qual_score = max(0, min(100, roe * 400))
    elif sector == "資安":
        qual_score = max(0, min(100, gross_margin * 100))
        if gross_margin > 0.75: qual_score += 20 
    elif sector == "能源":
        qual_score = 100 if fcf > 0 else 50
        if fcf < 0: qual_score -= 50
    elif sector == "半導體":
        qual_score = max(0, min(100, op_margin * 300))
    elif sector == "NeoCloud":
        qual_score = 50
        
    # 3. 成長動能
    rev_growth = info.get("revenueGrowth", 0)
    growth_score = max(0, min(100, rev_growth * 200))
    
    # 4. 政策與護城河
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score) / 2
    
    # 5. 綜合計算 (使用傳入的個股權重)
    w = custom_weights
    total_score = (
        val_score * w["Valuation"] +
        qual_score * w["Quality"] +
        growth_score * w["Growth"] +
        moat_policy_score * w["MoatPolicy"]
    )
    
    # 6. 懲罰調整
    final_adjustment = 0
    if sector == "資安" and gross_margin > 0.75: final_adjustment += 5
    if (sector == "能源" or sector == "NeoCloud") and fcf < 0: final_adjustment -= 10
    
    total_score = max(0, min(100, total_score + final_adjustment))
    
    return {
        "Total": round(total_score, 2),
        "Valuation": round(val_score, 2),
        "Quality": round(qual_score, 2),
        "Growth": round(growth_score, 2),
        "MoatPolicy": round(moat_policy_score, 2),
        "Adjustment": final_adjustment
    }

# =========================
# AI 分析邏輯 (保持穩定性)
# =========================
def call_gemini_with_retry(prompt, status, max_retries=MAX_RETRIES):
    delay = 2
    for attempt in range(max_retries):
        try:
            status.write(f"🤖 嘗試分析最新資訊 (第 {attempt + 1} 次)...")
            response = model.generate_content(prompt)
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            insight = json.loads(clean_json)
            return insight
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(delay); delay *= 2
            else:
                status.error(f"❌ Gemini 分析失敗: {e}")
                return None
    return None

def get_ai_market_insight(symbol, sector, current_weights, status):
    ticker = yf.Ticker(symbol)
    news = ticker.news[:5]
    news_text = "\n".join([f"- {n['title']}" for n in news if 'title' in n]) or "請基於 2026 總體經濟趨勢分析。"
    
    prompt = f"""
    分析 {symbol} ({sector}) 的 2026 投資評級。
    新聞：{news_text}
    當前權重：{current_weights}
    請回傳 JSON：{{ "sentiment": "利好"|"利空", "summary": "...", "suggested_weights": {{...}}, "reason": "..." }}
    """
    return call_gemini_with_retry(prompt, status)

# =========================
# 主程式 UI
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# --- 核心修改：初始化個股權重儲存 ---
if "weights" not in st.session_state:
    st.session_state.weights = {}

# 如果此股票還沒有獨立權重紀錄，則抓取產業預設
if selected_stock not in st.session_state.weights:
    st.session_state.weights[selected_stock] = SECTOR_CONFIG[selected_sector]["weights"].copy()

# 手動評分持久化
if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = {}

current_stock = selected_stock
if current_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[current_stock] = {"Policy": 50, "Moat": 50}

def update_policy_score(): st.session_state.manual_scores[current_stock]["Policy"] = st.session_state[f"{current_stock}_p"]
def update_moat_score(): st.session_state.manual_scores[current_stock]["Moat"] = st.session_state[f"{current_stock}_m"]

st.sidebar.subheader("✏️ 手動評分 (20%)")
m_policy = st.sidebar.slider("政策受益度", 0, 100, value=st.session_state.manual_scores[current_stock]["Policy"], key=f"{current_stock}_p", on_change=update_policy_score)
m_moat = st.sidebar.slider("護城河粘性", 0, 100, value=st.session_state.manual_scores[current_stock]["Moat"], key=f"{current_stock}_m", on_change=update_moat_score)

# AI 分析按鈕
if st.sidebar.button("🤖 啟動 AI 實時新聞分析"):
    with st.status("🤖 正在執行 AI 投資分析...", expanded=True) as status:
        # 傳入該股票獨有的權重
        insight = get_ai_market_insight(selected_stock, selected_sector, st.session_state.weights[selected_stock], status)
        if insight:
            st.session_state.last_insight = insight
            # 只儲存在當前股票的 Key 之下
            st.session_state.weights[selected_stock] = insight["suggested_weights"]
            status.update(label=f"✅ {selected_stock} 權重更新完成！", state="complete", expanded=False)

if "last_insight" in st.session_state:
    ins = st.session_state.last_insight
    st.info(f"### AI 2026 投資洞察 ({ins['sentiment']})\n**總結**: {ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

# 獲取數據並使用該股票的獨有權重計算
info = get_stock_data(selected_stock)
if info:
    sector_avg_data = {"avg_fwd_pe": 25} 
    # 使用 st.session_state.weights[selected_stock]
    scores = calculate_2026_score(info, selected_sector, {"Policy": m_policy, "Moat": m_moat}, sector_avg_data, st.session_state.weights[selected_stock])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", scores["Total"])
    col2.metric("投資評級", get_tier(scores["Total"]))
    col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    
    st.subheader(f"📊 {selected_stock} 評分維度 (權重已獨立配置)")
    
    detail_data = pd.DataFrame({
        "維度": ["前瞻估值 (Valuation)", "獲利質量 (Quality)", "成長動能 (Growth)", "政策與護城河 (MoatPolicy)"],
        "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
        "個股獨立權重": [st.session_state.weights[selected_stock][k] for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
    })
    st.table(detail_data) # 使用 table 更清晰

    with st.expander(f"🏭 {selected_sector} 產業橫向比較 (含 2026 政策評估)"):
        results = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            if s_info:
                # 比較時讀取各別股票已存的權重，若無則抓產業預設
                s_w = st.session_state.weights.get(s, SECTOR_CONFIG[selected_sector]["weights"])
                s_scores = calculate_2026_score(s_info, selected_sector, {"Policy": 50, "Moat": 50}, sector_avg_data, s_w)
                results.append({"股票": s, "綜合分數": s_scores["Total"], "評級": get_tier(s_scores["Total"]), "Fwd PE": s_info.get("forwardPE"), "FCF狀態": "正" if s_info.get("freeCashflow", 0) > 0 else "負"})
        st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False))
else:
    st.error("無法獲取股票數據")
