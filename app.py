import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import json
import os
import requests

# =========================
# 基本設定
# =========================
MAX_RETRIES = 3
STATE_FILE = "user_state.json"

st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

# =========================
# OpenRouter 設定
# =========================
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except:
    st.error("❌ 找不到 OPENROUTER_API_KEY")
    st.stop()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "deepseek/deepseek-r1:free"

# =========================
# 狀態檔工具
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"weights": {}, "manual_scores": {}}

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(
            {
                "weights": st.session_state.weights,
                "manual_scores": st.session_state.manual_scores
            },
            f,
            indent=2
        )

# =========================
# 產業池與配置
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","NEE","ENPH","VST","SMR"],
    "NeoCloud": ["NBIS","IREN","APLD"]
}

SECTOR_CONFIG = {
    "Mag7": {"weights": {"Valuation":0.25,"Quality":0.25,"Growth":0.30,"MoatPolicy":0.20}},
    "資安": {"weights": {"Valuation":0.20,"Quality":0.30,"Growth":0.30,"MoatPolicy":0.20}},
    "能源": {"weights": {"Valuation":0.15,"Quality":0.35,"Growth":0.15,"MoatPolicy":0.35}},
    "半導體": {"weights": {"Valuation":0.30,"Quality":0.25,"Growth":0.30,"MoatPolicy":0.15}},
    "NeoCloud": {"weights": {"Valuation":0.10,"Quality":0.15,"Growth":0.60,"MoatPolicy":0.15}}
}

# =========================
# Session 初始化（含持久化）
# =========================
persisted = load_state()

if "weights" not in st.session_state:
    st.session_state.weights = persisted.get("weights", {})
    for s in SECTORS:
        if s not in st.session_state.weights:
            st.session_state.weights[s] = SECTOR_CONFIG[s]["weights"].copy()

if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = persisted.get("manual_scores", {})

# =========================
# YFinance 工具
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
# 評分函數（保持原邏輯）
# =========================
def calculate_2026_score(info, sector, manual_scores, sector_avg_data):
    symbol = info.get("symbol")
    
    # Valuation
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = 50
    if fwd_pe:
        val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
        if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9:
            val_score = min(100, val_score * 1.2)
            
    # Quality
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
    
    # Growth
    rev_growth = info.get("revenueGrowth", 0)
    growth_score = max(0, min(100, rev_growth * 200))
    if sector == "Mag7" and rev_growth > 0.2: growth_score *= 1.2
    if sector == "NeoCloud" and rev_growth > 0.4: growth_score = 100
    
    # MoatPolicy
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score)/2
    
    # 綜合
    w = SECTOR_CONFIG[sector]["weights"]
    total_score = (
        val_score*w["Valuation"] +
        qual_score*w["Quality"] +
        growth_score*w["Growth"] +
        moat_policy_score*w["MoatPolicy"]
    )
    
    # 懲罰 / 加成
    final_adjustment = 0
    if sector == "資安" and gross_margin > 0.75: final_adjustment +=5
    if (sector=="能源" or sector=="NeoCloud") and fcf <0: final_adjustment -=10
    
    total_score = max(0, min(100, total_score + final_adjustment))
    
    return {
        "Total": round(total_score,2),
        "Valuation": round(val_score,2),
        "Quality": round(qual_score,2),
        "Growth": round(growth_score,2),
        "MoatPolicy": round(moat_policy_score,2),
        "Adjustment": final_adjustment
    }

# =========================
# OpenRouter AI 呼叫（安全版）
# =========================
def call_openrouter(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "US Stock Dashboard"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            st.error(f"❌ OpenRouter API 失敗 ({r.status_code})")
            st.code(r.text)
            return None
        data = r.json()
        if "choices" not in data or len(data["choices"])==0:
            st.error("❌ OpenRouter 回傳格式異常（無 choices）")
            st.json(data)
            return None
        content = data["choices"][0]["message"]["content"]
        clean = content.replace("```json","").replace("```","").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            st.error("❌ AI 回傳內容不是合法 JSON")
            st.code(clean)
            return None
    except requests.exceptions.RequestException as e:
        st.error("❌ 無法連線 OpenRouter")
        st.code(str(e))
        return None

# =========================
# Sidebar 選股
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 手動評分（持久化）
if selected_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[selected_stock] = {"Policy":50,"Moat":50}

policy = st.sidebar.slider(
    "政策受益度",
    0,100,
    st.session_state.manual_scores[selected_stock]["Policy"]
)
moat = st.sidebar.slider(
    "護城河粘性",
    0,100,
    st.session_state.manual_scores[selected_stock]["Moat"]
)
st.session_state.manual_scores[selected_stock] = {"Policy":policy,"Moat":moat}
save_state()

# =========================
# 單股 AI 分析
# =========================
if st.sidebar.button("🤖 AI 分析單一股票（調整權重）"):
    prompt = f"""
    請針對 {selected_stock}（{selected_sector}）給 2026 投資視角，
    並建議 Valuation / Quality / Growth / MoatPolicy 權重（總和=1），
    僅輸出 JSON。
    """
    insight = call_openrouter(prompt)
    if insight and "suggested_weights" in insight:
        st.session_state.weights[selected_sector] = insight["suggested_weights"]
        save_state()
        st.success("✅ 權重已更新並永久保存")
    else:
        st.warning("⚠️ AI 未回傳有效權重，未更新")

# =========================
# 全產業 AI 分析
# =========================
if st.sidebar.button("🏭 AI 分析整個產業（全股票）"):
    with st.status("AI 分析整個產業中...", expanded=True):
        prompt = f"""
        你是美股基金經理，請針對 {selected_sector} 產業 2026 前景，
        給出最適合該產業的 Valuation / Quality / Growth / MoatPolicy 權重（總和=1）
        僅輸出 JSON。
        """
        insight = call_openrouter(prompt)
        if insight and "suggested_weights" in insight:
            st.session_state.weights[selected_sector] = insight["suggested_weights"]
            save_state()
            st.success("✅ 產業權重已更新並保存")
        else:
            st.warning("⚠️ AI 未回傳有效權重，未更新")

# =========================
# 顯示目前權重
# =========================
st.subheader(f"📌 {selected_sector} 當前權重（已持久化）")
st.json(st.session_state.weights[selected_sector])

# =========================
# 顯示個股數據及評分
# =========================
info = get_stock_data(selected_stock)
if info:
    sector_avg_data = {"avg_fwd_pe":25}
    scores = calculate_2026_score(info, selected_sector, {"Policy":policy,"Moat":moat}, sector_avg_data)
    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", scores["Total"])
    col2.metric("投資評級", get_tier(scores["Total"]))
    col3.metric("前瞻 PE", info.get("forwardPE","N/A"))
    
    st.subheader(f"📊 {selected_sector} 評分維度")
    detail_data = pd.DataFrame({
        "維度":["Valuation","Quality","Growth","MoatPolicy"],
        "得分":[scores["Valuation"],scores["Quality"],scores["Growth"],scores["MoatPolicy"]],
        "權重":[st.session_state.weights[selected_sector][k] for k in ["Valuation","Quality","Growth","MoatPolicy"]]
    })
    st.dataframe(detail_data)
    
else:
    st.error("❌ 無法獲取股票數據")
