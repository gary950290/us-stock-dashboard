import streamlit as st
import pandas as pd
import yfinance as yf
import time
import random
from datetime import datetime
import google.generativeai as genai
import json
import os

# =========================
# 1. 核心設定與持久化邏輯
# =========================
CONFIG_FILE = "invest_config_2026_pro.json"

def save_config():
    config_data = {
        "weights": st.session_state.weights,
        "manual_scores": st.session_state.manual_scores,
        "last_analysis_time": st.session_state.get("last_analysis_time", 0)
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except: return None
    return None

# 初始化 Gemini
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    # 堅持使用 2.0 Flash 實驗版，具備 2026 最新推理能力
    model = genai.GenerativeModel('gemini-2.0-flash-exp') 
except Exception as e:
    st.error("❌ GEMINI_API_KEY 設定錯誤，請檢查 Streamlit Secrets。")
    st.stop()

# =========================
# 2. UI 佈局與 CSS
# =========================
st.set_page_config(page_title="2026 專業投資評比 Pro", layout="wide")

st.markdown("""
<style>
    .reportview-container .main .block-container { padding-top: 1rem; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    .policy-box { border-left: 5px solid #ff4b4b; padding-left: 15px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

st.title("🏛️ 2026 專業美股投資評比系統 (Pro)")
st.caption("同步 2026 美國 AI Action Plan 與 2nm 晶片政策邏輯")

# =========================
# 3. 產業定義與初始數據
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "半導體": ["NVDA","AMD","TSM","AVGO","INTC","ARM"],
    "能源/基礎設施": ["VST","CEG","OKLO","SMR","NEE","GEV"],
    "資安": ["CRWD","PANW","FTNT","ZS"]
}

SECTOR_CONFIG = {
    "Mag7": {"weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "AI 變現與 Agentic AI 佈局"},
    "半導體": {"weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15}, "focus": "2nm 產能與先進封裝補貼"},
    "能源/基礎設施": {"weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35}, "focus": "潔淨能源補貼 (Genesis Mission)"},
    "資安": {"weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "數據主權與合規平台權"}
}

# 初始化 Session State
saved_data = load_config()
if "weights" not in st.session_state:
    st.session_state.weights = saved_data["weights"] if saved_data else {s: SECTOR_CONFIG[s]["weights"].copy() for s in SECTORS.keys()}
if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = saved_data["manual_scores"] if saved_data else {}

# =========================
# 4. 核心工具函數
# =========================
@st.cache_data(ttl=600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        news = ticker.news
        return info, news
    except: return None, []

def call_gemini_with_pacing(prompt, status):
    """具備強制冷卻機制的 API 呼叫"""
    # 2.0-flash-exp 建議間隔至少 15 秒以支持較大新聞量
    wait_time = 18 
    with st.empty():
        for i in range(wait_time, 0, -1):
            status.write(f"⏳ 為確保分析深度，進行冷卻中... 剩餘 {i} 秒")
            time.sleep(1)
    
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        if "429" in str(e):
            status.error("❌ 配額已滿 (429)，請等待 1 分鐘或更換 API Key。")
        else:
            status.error(f"❌ AI 分析出錯: {e}")
        return None

# =========================
# 5. UI 互動區
# =========================
st.sidebar.header("⚙️ 評比配置")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 確保個股數據存在
if selected_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[selected_stock] = {"Policy": 50, "Moat": 50}

# 手動評分滑塊 (含持久化)
st.sidebar.subheader(f"✏️ {selected_stock} 2026 評分")
m_policy = st.sidebar.slider("政策受益度 (2026 New)", 0, 100, 
                             value=st.session_state.manual_scores[selected_stock]["Policy"],
                             key=f"p_{selected_stock}")
m_moat = st.sidebar.slider("技術護城河粘性", 0, 100, 
                           value=st.session_state.manual_scores[selected_stock]["Moat"],
                           key=f"m_{selected_stock}")

if m_policy != st.session_state.manual_scores[selected_stock]["Policy"] or \
   m_moat != st.session_state.manual_scores[selected_stock]["Moat"]:
    st.session_state.manual_scores[selected_stock] = {"Policy": m_policy, "Moat": m_moat}
    save_config()

# AI 分析按鈕
if st.sidebar.button("🤖 啟動 2026 深度新聞分析 (8則)"):
    with st.status(f"正在對 {selected_stock} 進行深度評估...", expanded=True) as status:
        info, news = get_stock_data(selected_stock)
        
        # --- 修正後的安全提取邏輯 ---
        if news:
            news_titles = []
            for n in news[:8]:
                if isinstance(n, dict) and 'title' in n:
                    news_titles.append(f"- {n['title']}")
                elif isinstance(n, dict) and 'summary' in n: # 備案：如果沒有標題但有摘要
                    news_titles.append(f"- [摘要] {n['summary'][:50]}...")
            
            if not news_titles:
                news_titles = ["無法取得有效新聞標題"]
        else:
            news_titles = ["目前無最新相關新聞"]
            
        news_context = "\n".join(news_titles)
        # ------------------------

        prompt = f"""
        你是資深美股分析師。請針對 {selected_stock} 的最新動態與 2026 年美國政策環境進行分析。
        最新動態：
        {news_context}
        
        請判斷對其 2026 估值的影響，並建議調整權重：{list(st.session_state.weights[selected_sector].keys())}
        嚴格以 JSON 格式回覆：
        {{
            "sentiment": "利好" | "利空" | "中性",
            "summary": "一句話總結",
            "suggested_weights": {{ "Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float }},
            "reason": "考慮 2026 政策的詳細理由"
        }}
        """
        result = call_gemini_with_pacing(prompt, status)
        if result:
            st.session_state.weights[selected_sector] = result["suggested_weights"]
            st.session_state[f"last_insight_{selected_stock}"] = result
            save_config()
            status.update(label="✅ 分析完成！權重已依據 2026 趨勢優化。", state="complete")

# =========================
# 6. 數據展示區
# =========================
info, _ = get_stock_data(selected_stock)
if info:
    # 核心計算邏輯 (維持原始穩定邏輯)
    fwd_pe = info.get("forwardPE", 25)
    roe = info.get("returnOnEquity", 0)
    fcf = info.get("freeCashflow", 0)
    rev_growth = info.get("revenueGrowth", 0)
    
    # 維度得分計算
    v_score = max(0, min(100, (25 / fwd_pe) * 50))
    q_score = max(0, min(100, roe * 400)) if selected_sector == "Mag7" else 60
    g_score = max(0, min(100, rev_growth * 200))
    mp_score = (m_policy + m_moat) / 2
    
    w = st.session_state.weights[selected_sector]
    total_score = (v_score * w["Valuation"] + q_score * w["Quality"] + 
                   g_score * w["Growth"] + mp_score * w["MoatPolicy"])
    
    # 頂部指標
    c1, c2, c3 = st.columns(3)
    c1.metric("🎯 2026 綜合評分", f"{total_score:.2f}")
    c2.metric("投資評級", "Tier 1 🚀" if total_score > 75 else "Tier 2 ⚖️")
    c3.metric("前瞻 PE", f"{fwd_pe:.1f}x")

    # 政策與 AI 洞察
    if f"last_insight_{selected_stock}" in st.session_state:
        ins = st.session_state[f"last_insight_{selected_stock}"]
        st.info(f"**AI 深度洞察 ({ins['sentiment']})**: {ins['summary']}")
        with st.expander("查看 2026 權重調整理由"):
            st.write(ins['reason'])

    # 橫向比較表 (整理成表格)
    st.subheader(f"📊 {selected_sector} 產業橫向估值對比 (2026)")
    comparison_data = []
    for s in SECTORS[selected_sector]:
        s_info, _ = get_stock_data(s)
        if s_info:
            s_fwd_pe = s_info.get("forwardPE", 0)
            s_fcf = s_info.get("freeCashflow", 0)
            # 獲取存檔中的手動評分，無則 50
            s_manual = st.session_state.manual_scores.get(s, {"Policy": 50, "Moat": 50})
            comparison_data.append({
                "股票": s,
                "前瞻 PE": f"{s_fwd_pe:.1f}",
                "FCF (B)": f"{s_fcf/1e9:.1f}",
                "政策受益度": s_manual["Policy"],
                "技術護城河": s_manual["Moat"]
            })
    st.table(pd.DataFrame(comparison_data))

    # 2026 政策環境說明
    st.markdown("### 🏛️ 2026 政府政策監控點")
    st.markdown(f"""
    <div class="policy-box">
        <strong>當前產業焦點：{SECTOR_CONFIG[selected_sector]['focus']}</strong><br>
        1. <strong>Genesis Mission</strong>：數據中心能源接入優先權。<br>
        2. <strong>晶片法案 2.0</strong>：針對 2nm 製程落地的稅收抵免。<br>
        3. <strong>Agentic AI 合規性</strong>：自主代理人的法律責任界定影響軟體股溢價。
    </div>
    """, unsafe_allow_html=True)

else:
    st.warning("數據載入中，請稍候...")

# 結尾提示
st.markdown("---")
st.caption(f"數據最後更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
