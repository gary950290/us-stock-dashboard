import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json

# =========================
# 初始化 Gemini API
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error("❌ 找不到 GEMINI_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 設定
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

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
# 核心權重配置 (2026 邏輯)
# =========================
SECTOR_CONFIG = {
    "Mag7": {
        "weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20},
        "focus": "AI 變現效率與現金流"
    },
    "資安": {
        "weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20},
        "focus": "毛利率與平台定價權"
    },
    "能源": {
        "weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35},
        "focus": "FCF 與政策補貼"
    },
    "半導體": {
        "weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15},
        "focus": "前瞻盈餘與製程領先"
    },
    "NeoCloud": {
        "weights": {"Valuation": 0.10, "Quality": 0.15, "Growth": 0.60, "MoatPolicy": 0.15},
        "focus": "未來規模與成長寬容度"
    }
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
# 評分引擎 (2026 專業邏輯)
# =========================
def calculate_2026_score(info, sector, manual_scores, sector_avg_data):
    symbol = info.get("symbol")
    
    # 1. 前瞻估值 (Valuation)
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = 50
    if fwd_pe:
        # 標準化：個股 Fwd PE / 產業平均
        val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
        if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9: # 低於均值 10% 以上
            val_score = min(100, val_score * 1.2)
    
    # 2. 獲利質量 (Quality)
    roe = info.get("returnOnEquity", 0)
    fcf = info.get("freeCashflow", 0)
    gross_margin = info.get("grossMargins", 0)
    op_margin = info.get("operatingMargins", 0)
    
    qual_score = 50
    if sector == "Mag7":
        qual_score = max(0, min(100, roe * 400))
    elif sector == "資安":
        qual_score = max(0, min(100, gross_margin * 100))
        if gross_margin > 0.75: qual_score += 20 # 75% 毛利溢價
    elif sector == "能源":
        qual_score = 100 if fcf > 0 else 50
        if fcf < 0: qual_score -= 50 # FCF 為負硬性扣減
    elif sector == "半導體":
        qual_score = max(0, min(100, op_margin * 300))
    elif sector == "NeoCloud":
        qual_score = 50 # 關注 Burn Rate，預設中性
        
    # 3. 成長動能 (Growth)
    rev_growth = info.get("revenueGrowth", 0)
    growth_score = max(0, min(100, rev_growth * 200))
    
    if sector == "Mag7" and rev_growth > 0.2: growth_score *= 1.2
    if sector == "NeoCloud" and rev_growth > 0.4: growth_score = 100
    
    # 4. 政策與護城河 (MoatPolicy)
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score) / 2
    
    # 5. 綜合計算
    w = SECTOR_CONFIG[sector]["weights"]
    total_score = (
        val_score * w["Valuation"] +
        qual_score * w["Quality"] +
        growth_score * w["Growth"] +
        moat_policy_score * w["MoatPolicy"]
    )
    
    # 6. 懲罰與加成係數 (最終調整)
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
# AI 洞察 (Gemini)
# =========================
def get_ai_market_insight(symbol, sector, current_weights):
    st.info("💡 偵錯訊息：開始嘗試獲取股票新聞和呼叫 Gemini API...") # 偵錯訊息
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news[:5]
        news_text = "\n".join([f"- {n['title']}" for n in news])
        
        prompt = f"""
        你是一位資深美股分析師。請針對 {symbol} ({sector}產業) 的最新新聞進行 2026 投資評級分析：
        {news_text}
        
        請根據新聞內容，判斷對該公司的利好/利空影響，並建議是否需要微調以下權重（總和需為 1.0）：
        {list(current_weights.keys())}
        
        請嚴格以 JSON 格式回覆：
        {{
            "sentiment": "利好" | "利空" | "中性",
            "summary": "簡短總結",
            "suggested_weights": {{ "Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float }},
            "reason": "理由"
        }}
        """
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        
        # 嘗試解析 JSON
        return json.loads(clean_json)
    except Exception as e:
        # 如果失敗，將錯誤印出來
        st.error(f"❌ Gemini 分析失敗：{e}")
        print(f"DEBUG ERROR: get_ai_market_insight failed for {symbol}. Error: {e}")
        return None

# =========================
# UI 佈局
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

if "weights" not in st.session_state:
    st.session_state.weights = {s: SECTOR_CONFIG[s]["weights"].copy() for s in SECTORS.keys()}

# --- 【新增】手動評分持久化邏輯 ---

# 1. 初始化用於儲存所有股票手動評分的核心狀態
if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = {}

# 2. 確保當前選定股票的評分已初始化（預設 50）
current_stock = selected_stock
if current_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[current_stock] = {"Policy": 50, "Moat": 50}

# 3. 定義回調函數，在滑塊變動時，更新 session_state.manual_scores 中的值
def update_policy_score():
    # 使用 slider 的 key 來存取變動後的值，並更新到持久化 storage 中
    st.session_state.manual_scores[current_stock]["Policy"] = st.session_state[f"{current_stock}_p"]

def update_moat_score():
    st.session_state.manual_scores[current_stock]["Moat"] = st.session_state[f"{current_stock}_m"]
    
# 4. 從 session state 中讀取當前股票的持久化值，作為滑塊的初始值
policy_default = st.session_state.manual_scores[current_stock]["Policy"]
moat_default = st.session_state.manual_scores[current_stock]["Moat"]

# 手動評分
st.sidebar.subheader("✏️ 手動評分 (20%)")
# 滑塊使用持久化的值作為初始值 (value)，並在變動時觸發回調函數
m_policy = st.sidebar.slider(
    "政策受益度", 
    0, 
    100, 
    value=policy_default, 
    key=f"{current_stock}_p", 
    on_change=update_policy_score
)
m_moat = st.sidebar.slider(
    "護城河粘性", 
    0, 
    100, 
    value=moat_default, 
    key=f"{current_stock}_m", 
    on_change=update_moat_score
)
# --- 【結束】手動評分持久化邏輯 ---

if st.sidebar.button("🤖 啟動 AI 實時新聞分析"):
    # --- 【偵錯點 1：立即確認按鈕觸發】 ---
    st.success("✅ 按鈕已觸發：正在進入 AI 分析流程。")
    # ------------------------------------
    
    with st.spinner("Gemini 正在分析 2026 投資影響..."):
        insight = get_ai_market_insight(selected_stock, selected_sector, st.session_state.weights[selected_sector])
        
        # --- 【偵錯點 2：分析結果確認】 ---
        if insight is None:
            st.error("❌ 偵錯訊息：AI 分析程序返回空值。請檢查上方是否有錯誤訊息或控制台輸出。")
        # ------------------------------------
            
        if insight:
            st.session_state.last_insight = insight
            st.session_state.weights[selected_sector] = insight["suggested_weights"]

# 顯示 AI 洞察
if "last_insight" in st.session_state:
    ins = st.session_state.last_insight
    st.info(f"### AI 2026 投資洞察 ({ins['sentiment']})\n**總結**: {ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

# 獲取數據並計算
info = get_stock_data(selected_stock)
if info:
    # 模擬產業平均數據 (實際應從多股平均獲取)
    sector_avg_data = {"avg_fwd_pe": 25} 
    
    # 評分計算使用從滑塊取得的當前值 (m_policy, m_moat)
    scores = calculate_2026_score(info, selected_sector, {"Policy": m_policy, "Moat": m_moat}, sector_avg_data)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", scores["Total"])
    col2.metric("投資評級", get_tier(scores["Total"]))
    col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    
    st.subheader(f"📊 {selected_sector} 評分維度 (焦點：{SECTOR_CONFIG[selected_sector]['focus']})")
    
    # 顯示維度細節
    detail_data = pd.DataFrame({
        "維度": ["前瞻估值 (Valuation)", "獲利質量 (Quality)", "成長動能 (Growth)", "政策與護城河 (MoatPolicy)"],
        "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
        "權重": [st.session_state.weights[selected_sector][k] for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
    })
    st.table(detail_data)
    
    if scores["Adjustment"] != 0:
        st.warning(f"⚠️ 觸發懲罰/加成機制：總分已調整 {scores['Adjustment']} 分")

    # 產業橫向比較
    with st.expander(f"🏭 查看 {selected_sector} 產業橫向排序"):
        results = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            if s_info:
                # 橫向比較時，預設手動評分為 50/50，不使用當前股票的持久化值
                s_scores = calculate_2026_score(s_info, selected_sector, {"Policy": 50, "Moat": 50}, sector_avg_data)
                results.append({
                    "股票": s,
                    "綜合分數": s_scores["Total"],
                    "評級": get_tier(s_scores["Total"]),
                    "Fwd PE": s_info.get("forwardPE"),
                    "FCF": s_info.get("freeCashflow")
                })
        st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False))
else:
    st.error("無法獲取股票數據")

