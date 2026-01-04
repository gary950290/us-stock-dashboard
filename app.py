import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json
import os
import threading

# =========================
# 基本設定
# =========================
MAX_RETRIES = 3
PERSIST_DIR = "data"
MANUAL_SCORES_FILE = f"{PERSIST_DIR}/manual_scores.json"
WEIGHTS_FILE = f"{PERSIST_DIR}/sector_weights.json"
INSIGHTS_FILE = f"{PERSIST_DIR}/last_insights.json"

# =========================
# Gemini API 初始化
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
except Exception:
    st.error("❌ 找不到 GEMINI_API_KEY，請於 Streamlit Secrets 設定")
    st.stop()

# =========================
# App UI 設定
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

st.markdown("""
<style>
.stApp { overflow-y:auto; max-height:100vh; }
</style>
""", unsafe_allow_html=True)

# =========================
# 工具：JSON 持久化
# =========================
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return default

def save_all(manual_scores, sector_weights, last_insights):
    os.makedirs(PERSIST_DIR, exist_ok=True)
    def _save():
        with open(MANUAL_SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(manual_scores, f, ensure_ascii=False, indent=2)
        with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(sector_weights, f, ensure_ascii=False, indent=2)
        with open(INSIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(last_insights, f, ensure_ascii=False, indent=2)
    threading.Thread(target=_save, daemon=True).start()

# =========================
# 載入 Persisted 狀態
# =========================
persist_manual = load_json(MANUAL_SCORES_FILE, {})
persist_weights = load_json(WEIGHTS_FILE, {})
persist_insights = load_json(INSIGHTS_FILE, {})

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","NEE","ENPH","VST","OKLO","SMR"],
    "NeoCloud": ["NBIS","IREN","APLD"]
}

SECTOR_CONFIG = {
    "Mag7": {"weights":{"Valuation":0.25,"Quality":0.25,"Growth":0.30,"MoatPolicy":0.20},"focus":"AI 變現"},
    "資安": {"weights":{"Valuation":0.20,"Quality":0.30,"Growth":0.30,"MoatPolicy":0.20},"focus":"毛利率"},
    "半導體":{"weights":{"Valuation":0.30,"Quality":0.25,"Growth":0.30,"MoatPolicy":0.15},"focus":"製程"},
    "能源":{"weights":{"Valuation":0.15,"Quality":0.35,"Growth":0.15,"MoatPolicy":0.35},"focus":"FCF"},
    "NeoCloud":{"weights":{"Valuation":0.10,"Quality":0.15,"Growth":0.60,"MoatPolicy":0.15},"focus":"成長"}
}

# =========================
# Session State 初始化
# =========================
if "weights" not in st.session_state:
    st.session_state.weights = {
        s: persist_weights.get(s, SECTOR_CONFIG[s]["weights"])
        for s in SECTORS
    }

if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = persist_manual

if "last_insight" not in st.session_state:
    st.session_state.last_insight = persist_insights

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        return yf.Ticker(symbol).info
    except:
        return None

def get_tier(score):
    if score >= 80: return "Tier 1 🚀"
    elif score >= 60: return "Tier 2 ⚖️"
    else: return "Tier 3 ⚠️"

# =========================
# 評分邏輯（未變動）
# =========================
def calculate_2026_score(info, sector, manual, sector_avg):
    fwd_pe = info.get("forwardPE")
    avg_pe = sector_avg.get("avg_fwd_pe",25)
    val = 50 if not fwd_pe else max(0,min(100,(avg_pe/fwd_pe)*50))

    rev = info.get("revenueGrowth",0)
    growth = max(0,min(100,rev*200))

    roe = info.get("returnOnEquity",0)
    qual = max(0,min(100,roe*400))

    moat_policy = (manual["Policy"]+manual["Moat"])/2
    w = st.session_state.weights[sector]

    total = val*w["Valuation"] + qual*w["Quality"] + growth*w["Growth"] + moat_policy*w["MoatPolicy"]
    return round(total,2), val, qual, growth, moat_policy

# =========================
# Gemini AI
# =========================
def call_gemini(prompt, status):
    delay = 2
    for i in range(MAX_RETRIES):
        try:
            status.write(f"🤖 Gemini 呼叫 {i+1}")
            r = model.generate_content(prompt)
            return json.loads(r.text.replace("```json","").replace("```",""))
        except Exception as e:
            if i < MAX_RETRIES-1:
                time.sleep(delay)
                delay*=2
            else:
                status.error("❌ Gemini 失敗")
                return None

def ai_analyze(symbol, sector, status):
    news = yf.Ticker(symbol).news[:5]
    titles = "\n".join([f"- {n['title']}" for n in news if 'title'in n])
    prompt=f"""
你是資深美股分析師，分析 {symbol} ({sector})
{titles}
回傳 JSON：
{{
"sentiment":"利好|利空|中性",
"summary":"",
"suggested_weights":{{"Valuation":0.25,"Quality":0.25,"Growth":0.25,"MoatPolicy":0.25}},
"reason":""
}}
"""
    return call_gemini(prompt,status)

# =========================
# Sidebar UI
# =========================
st.sidebar.header("⚙️ 設定")
sector = st.sidebar.selectbox("產業", list(SECTORS))
stock = st.sidebar.selectbox("股票", SECTORS[sector])

if stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[stock]={"Policy":50,"Moat":50}

def update_manual():
    save_all(st.session_state.manual_scores, st.session_state.weights, st.session_state.last_insight)

policy = st.sidebar.slider("政策分數",0,100,st.session_state.manual_scores[stock]["Policy"],on_change=update_manual)
moat = st.sidebar.slider("護城河分數",0,100,st.session_state.manual_scores[stock]["Moat"],on_change=update_manual)
st.session_state.manual_scores[stock]={"Policy":policy,"Moat":moat}

# =========================
# AI 單股
# =========================
if st.sidebar.button("🤖 AI 分析單股"):
    with st.status("AI 分析中...",expanded=True) as status:
        res = ai_analyze(stock,sector,status)
        if res:
            st.session_state.last_insight[stock]=res
            st.session_state.weights[sector]=res["suggested_weights"]
            save_all(st.session_state.manual_scores,st.session_state.weights,st.session_state.last_insight)
            status.update(label="✅ 完成",state="complete")

# =========================
# AI 全產業
# =========================
if st.sidebar.button("🔁 一鍵分析整個產業"):
    with st.status("分析整個產業...",expanded=True) as status:
        for s in SECTORS[sector]:
            r = ai_analyze(s,sector,status)
            if r:
                st.session_state.last_insight[s]=r
                st.session_state.weights[sector]=r["suggested_weights"]
                time.sleep(1.2)
        save_all(st.session_state.manual_scores,st.session_state.weights,st.session_state.last_insight)
        status.update(label="✅ 產業分析完成",state="complete")

# =========================
# 主畫面
# =========================
info = get_stock_data(stock)
if info:
    total,val,qual,growth,moat_policy = calculate_2026_score(
        info,sector,st.session_state.manual_scores[stock],{"avg_fwd_pe":25}
    )
    c1,c2,c3=st.columns(3)
    c1.metric("總分",total)
    c2.metric("評級",get_tier(total))
    c3.metric("Fwd PE",info.get("forwardPE","N/A"))

    st.dataframe(pd.DataFrame({
        "維度":["Valuation","Quality","Growth","MoatPolicy"],
        "得分":[val,qual,growth,moat_policy],
        "權重":[st.session_state.weights[sector][k] for k in ["Valuation","Quality","Growth","MoatPolicy"]]
    }))

    if stock in st.session_state.last_insight:
        ins = st.session_state.last_insight[stock]
        st.info(f"### AI 洞察（{ins['sentiment']}）\n{ins['summary']}\n\n理由：{ins['reason']}")
else:
    st.error("❌ 無法取得股票資料")
