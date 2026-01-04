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
# 初始化狀態
# =========================
persisted = load_state()

# =========================
# 產業池
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
if "weights" not in st.session_state:
    st.session_state.weights = persisted.get("weights", {})
    for s in SECTORS:
        if s not in st.session_state.weights:
            st.session_state.weights[s] = SECTOR_CONFIG[s]["weights"].copy()

if "manual_scores" not in st.session_state:
    st.session_state.manual_scores = persisted.get("manual_scores", {})

# =========================
# OpenRouter 呼叫
# =========================
def call_openrouter(prompt):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)

# =========================
# Sidebar
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# =========================
# 手動評分（持久化）
# =========================
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

st.session_state.manual_scores[selected_stock] = {
    "Policy": policy,
    "Moat": moat
}
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
    st.session_state.weights[selected_sector] = insight["suggested_weights"]
    save_state()
    st.success("✅ 權重已更新並永久保存")

# =========================
# ⭐ 全產業一鍵 AI 權重分析
# =========================
if st.sidebar.button("🏭 AI 分析整個產業（全股票）"):
    with st.status("AI 分析整個產業中...", expanded=True):
        prompt = f"""
        你是美股基金經理，請針對 {selected_sector} 產業 2026 前景，
        給出最適合該產業的 Valuation / Quality / Growth / MoatPolicy 權重（總和=1）
        僅輸出 JSON。
        """
        insight = call_openrouter(prompt)
        st.session_state.weights[selected_sector] = insight["suggested_weights"]
        save_state()
        st.success("✅ 產業權重已更新並保存")

# =========================
# 顯示目前權重
# =========================
st.subheader(f"📌 {selected_sector} 當前權重（已持久化）")
st.json(st.session_state.weights[selected_sector])
