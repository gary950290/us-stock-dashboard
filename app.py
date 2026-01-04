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
# 確保在 Streamlit Cloud 的 Secrets 中設定了 GEMINI_API_KEY
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
st.set_page_config(page_title="AI 產業美股分析儀表板 (Gemini 版)", layout="wide")
st.title("📊 AI 產業美股分析儀表板")
st.caption("Powered by Google Gemini & yfinance")

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
# 護城河資料
# ==========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.92,"network":0.75},
}
MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 產業專屬權重配置 (預設)
# =========================
DEFAULT_SECTOR_WEIGHTS = {
    "Mag7": {"PE":0.28,"ROE":0.22,"Policy":0.18,"Moat":0.18,"Growth":0.14},
    "資安": {"PE":0.25,"ROE":0.22,"Policy":0.23,"Moat":0.13,"Growth":0.17},
    "半導體": {"PE":0.28,"ROE":0.25,"Policy":0.18,"Moat":0.13,"Growth":0.16},
    "能源": {"PE":0.2,"ROE":0.18,"Policy":0.32,"Moat":0.13,"Growth":0.17},
    "NeoCloud": {"PE":0.23,"ROE":0.22,"Policy":0.18,"Moat":0.08,"Growth":0.29}
}

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info
    except:
        return None

def calculate_moat_score(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score = sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score, 2)

def get_score_color(score):
    if score >= 80: return "🟢"
    elif score >= 60: return "🟡"
    elif score >= 40: return "🟠"
    else: return "🔴"

# =========================
# AI 實時監控模組 (Gemini 版)
# =========================
def get_ai_insight_gemini(symbol, sector):
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news[:5]
        news_text = "\n".join([f"- {n['title']}" for n in news])
        
        prompt = f"""
        你是一位資深美股分析師。請分析公司 {symbol} ({sector}產業) 的最新新聞：
        {news_text}
        
        請判斷：
        1. 利好/利空情緒。
        2. 對該產業權重的建議調整（PE, ROE, Policy, Moat, Growth，總和必須等於 1.0）。
        3. 具體理由。
        
        請嚴格以 JSON 格式回覆，不要包含任何 Markdown 標籤或額外文字：
        {{
            "sentiment": "利好/利空/中性",
            "summary": "一句話總結新聞影響",
            "weights": {{"PE": 0.x, "ROE": 0.x, "Policy": 0.x, "Moat": 0.x, "Growth": 0.x}},
            "reason": "調整權重的具體理由"
        }}
        """
        
        response = model.generate_content(prompt)
        # 清理可能存在的 Markdown 標籤
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        st.warning(f"AI 分析失敗: {str(e)}")
        return None

# =========================
# 核心評分邏輯
# =========================
def compute_scores(info, sector, weights, manual_overrides=None):
    pe = info.get("trailingPE")
    roe = info.get("returnOnEquity")
    
    # PE 評分 (簡單映射)
    pe_score = max(0, min(100, 100 - (pe / 0.5))) if pe else 50
    # ROE 評分 (簡單映射)
    roe_score = max(0, min(100, roe * 400)) if roe else 50
    
    policy_score = manual_overrides.get("Policy", 50) if manual_overrides else 50
    moat_score = calculate_moat_score(info.get("symbol", ""))
    growth_score = manual_overrides.get("Growth", 50) if manual_overrides else 50
    
    total = (
        pe_score * weights["PE"] +
        roe_score * weights["ROE"] +
        policy_score * weights["Policy"] +
        moat_score * weights["Moat"] +
        growth_score * weights["Growth"]
    )
    
    return {
        "Total": round(total, 2),
        "PE": round(pe_score, 2),
        "ROE": round(roe_score, 2),
        "Policy": policy_score,
        "Moat": moat_score,
        "Growth": growth_score
    }

# =========================
# UI 佈局
# =========================
st.sidebar.header("⚙️ 控制面板")
mode = st.sidebar.radio("模式", ["單股深度分析", "產業橫向比較"])

if "weights" not in st.session_state:
    st.session_state.weights = DEFAULT_SECTOR_WEIGHTS.copy()

if mode == "單股深度分析":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    symbol = st.sidebar.selectbox("選擇股票", SECTORS[sector])
    
    if st.sidebar.button("🤖 Gemini 實時分析新聞"):
        with st.spinner("Gemini 正在掃描新聞並調整權重..."):
            insight = get_ai_insight_gemini(symbol, sector)
            if insight:
                st.session_state.last_insight = insight
                st.session_state.weights[sector] = insight["weights"]
                st.success("權重已根據 Gemini 建議更新！")

    if "last_insight" in st.session_state:
        ins = st.session_state.last_insight
        st.info(f"### AI 洞察 ({ins['sentiment']})\n**總結**: {ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

    info = get_stock_data(symbol)
    if info:
        scores = compute_scores(info, sector, st.session_state.weights[sector])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🎯 綜合分數", f"{get_score_color(scores['Total'])} {scores['Total']}")
        col2.metric("股價", f"${info.get('currentPrice', 'N/A')}")
        col3.metric("PE (Ttm)", f"{info.get('trailingPE', 'N/A')}")
        
        st.subheader("📊 評分維度與權重")
        chart_data = pd.DataFrame({
            "維度": ["PE", "ROE", "政策", "護城河", "成長"],
            "得分": [scores["PE"], scores["ROE"], scores["Policy"], scores["Moat"], scores["Growth"]],
            "當前權重": [st.session_state.weights[sector][k] for k in ["PE", "ROE", "Policy", "Moat", "Growth"]]
        })
        st.table(chart_data)
    else:
        st.error("無法獲取股票數據，請檢查代碼是否正確或稍後再試。")

else: # 產業橫向比較
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業橫向評分")
    
    results = []
    progress_bar = st.progress(0)
    stocks = SECTORS[sector]
    
    for idx, s in enumerate(stocks):
        info = get_stock_data(s)
        if info:
            scores = compute_scores(info, sector, st.session_state.weights[sector])
            results.append({
                "股票": s,
                "綜合分數": scores["Total"],
                "評級": get_score_color(scores["Total"]),
                "PE評分": scores["PE"],
                "ROE評分": scores["ROE"],
                "政策評分": scores["Policy"],
                "護城河評分": scores["Moat"],
                "成長評分": scores["Growth"]
            })
        progress_bar.progress((idx + 1) / len(stocks))
        time.sleep(0.2) # 避免 API 頻率限制
    
    if results:
        df = pd.DataFrame(results).sort_values("綜合分數", ascending=False)
        st.dataframe(df, use_container_width=True)
    else:
        st.error("無法獲取產業數據。")
