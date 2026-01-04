import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
import json
from datetime import datetime

# =========================
# 1. OpenRouter 配置 (2026 最新免費模型)
# =========================
# 優先順序：Gemini 2.5 (速度/數據) > DeepSeek R1 (推理) > Qwen3 (穩定)
OR_MODELS = [
    "google/gemini-2.5-flash-preview-09-2025:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen3-coder:free",
    "mistralai/mistral-nemo:free",
    "openrouter/auto"
]

try:
    OR_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except:
    st.error("❌ 找不到 OPENROUTER_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 2. 產業配置與初始權重
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")

SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

DEFAULT_CONFIG = {
    "Mag7": {"weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "AI 變現"},
    "資安": {"weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "毛利率"},
    "能源": {"weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35}, "focus": "FCF"},
    "半導體": {"weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15}, "focus": "前瞻盈餘"},
    "NeoCloud": {"weights": {"Valuation": 0.10, "Quality": 0.15, "Growth": 0.60, "MoatPolicy": 0.15}, "focus": "未來規模"}
}

# 數據持久化核心：儲存格式 { ticker: { manual: {}, weights: {}, insight: {} } }
if "stock_vault" not in st.session_state:
    st.session_state.stock_vault = {}

# =========================
# 3. 核心工具函數
# =========================

@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info
    except: return None

def call_openrouter(prompt, status):
    """具備自動切換模型的 OpenRouter API 呼叫"""
    headers = {
        "Authorization": f"Bearer {OR_API_KEY}",
        "HTTP-Referer": "http://localhost:8501",
        "Content-Type": "application/json"
    }
    for model in OR_MODELS:
        try:
            status.write(f"🤖 嘗試模型: {model}...")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, data=json.dumps(payload), timeout=25)
            if res.status_code == 200:
                return json.loads(res.json()['choices'][0]['message']['content'])
        except: continue
    return None

def run_ai_analysis(symbol, sector, status):
    """執行單一股票 AI 分析並寫入持久化存儲"""
    info = get_stock_data(symbol)
    if not info: return False
    
    # 獲取該股目前的權重（若無則用預設）
    current_w = st.session_state.stock_vault.get(symbol, {}).get("weights", DEFAULT_CONFIG[sector]["weights"])
    
    prompt = f"""
    分析 {symbol} ({sector} 產業) 的 2026 投資價值。
    目前市場數據: PE={info.get('forwardPE')}, ROE={info.get('returnOnEquity')}, 營收成長={info.get('revenueGrowth')}
    請基於產業趨勢微調權重 (總和 1.0)。
    回傳 JSON: {{ "sentiment": "利好/利空/中性", "summary": "字內", "suggested_weights": {{"Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float}}, "reason": "原因" }}
    """
    insight = call_openrouter(prompt, status)
    if insight:
        if symbol not in st.session_state.stock_vault:
            st.session_state.stock_vault[symbol] = {"manual": {"Policy": 50, "Moat": 50}}
        st.session_state.stock_vault[symbol]["weights"] = insight["suggested_weights"]
        st.session_state.stock_vault[symbol]["insight"] = insight
        return True
    return False

# =========================
# 4. UI 邏輯
# =========================
st.title("🏛️ 2026 專業美股投資評比系統")

selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 初始化當前股票在 Vault 中的位置
if selected_stock not in st.session_state.stock_vault:
    st.session_state.stock_vault[selected_stock] = {
        "manual": {"Policy": 50, "Moat": 50},
        "weights": DEFAULT_CONFIG[selected_sector]["weights"].copy(),
        "insight": None
    }

# --- 手動評分持久化 (使用回調確保即時儲存) ---
def sync_vault():
    st.session_state.stock_vault[selected_stock]["manual"]["Policy"] = st.session_state[f"{selected_stock}_p"]
    st.session_state.stock_vault[selected_stock]["manual"]["Moat"] = st.session_state[f"{selected_stock}_m"]

st.sidebar.subheader("✏️ 2026 手動評分")
vault_m = st.session_state.stock_vault[selected_stock]["manual"]
st.sidebar.slider("政策受益度", 0, 100, value=vault_m["Policy"], key=f"{selected_stock}_p", on_change=sync_vault)
st.sidebar.slider("護城河粘性", 0, 100, value=vault_m["Moat"], key=f"{selected_stock}_m", on_change=sync_vault)

# --- AI 按鈕 ---
col_b1, col_b2 = st.sidebar.columns(2)
if col_b1.button("🤖 單股 AI 分析"):
    with st.status(f"分析 {selected_stock}...", expanded=False) as status:
        if run_ai_analysis(selected_stock, selected_sector, status):
            status.update(label="✅ 完成", state="complete")
            st.rerun()

if col_b2.button("🚀 一鍵分析全產業"):
    with st.status(f"處理 {selected_sector} 產業...", expanded=True) as status:
        for s in SECTORS[selected_sector]:
            status.write(f"正在分析 {s}...")
            run_ai_analysis(s, selected_sector, status)
            time.sleep(0.5) # 避開 Rate Limit
        status.update(label="✅ 全產業優化完成", state="complete")
        st.rerun()

# =========================
# 5. 數據呈現與評分引擎
# =========================
info = get_stock_data(selected_stock)
if info:
    # 提取持久化數據
    s_data = st.session_state.stock_vault[selected_stock]
    w = s_data["weights"]
    m = s_data["manual"]
    ins = s_data["insight"]

    if ins:
        st.info(f"### AI 洞察: {ins['sentiment']}\n{ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

    # 計算分數邏輯 (保持原有優化邏輯)
    fwd_pe = info.get("forwardPE", 25)
    val_score = max(0, min(100, (25 / fwd_pe) * 50))
    qual_score = max(0, min(100, info.get("returnOnEquity", 0) * 400))
    growth_score = max(0, min(100, info.get("revenueGrowth", 0) * 200))
    moat_policy_score = (m["Policy"] + m["Moat"]) / 2

    total_score = (val_score * w["Valuation"] + 
                   qual_score * w["Quality"] + 
                   growth_score * w["Growth"] + 
                   moat_policy_score * w["MoatPolicy"])

    # 儀表板顯示
    c1, c2, c3 = st.columns(3)
    c1.metric("🎯 綜合評分", round(total_score, 2))
    c2.metric("前瞻 PE", fwd_pe)
    c3.metric("狀態", "AI 已優化" if ins else "預設模式")

    # 產業比較表
    with st.expander("🏭 查看產業橫向排序 (包含已儲存的手動分數)"):
        compare_data = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            s_vault = st.session_state.stock_vault.get(s, {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_CONFIG[selected_sector]["weights"]})
            if s_info:
                # 簡易估算總分用於排序
                s_total = (50 * s_vault["weights"]["Valuation"] + 50 * s_vault["weights"]["Quality"] + 50 * s_vault["weights"]["Growth"] + 
                          ((s_vault["manual"]["Policy"] + s_vault["manual"]["Moat"])/2) * s_vault["weights"]["MoatPolicy"])
                compare_data.append({
                    "股票": s, "目前分數預估": round(s_total, 1), 
                    "政策分數": s_vault["manual"]["Policy"], "護城河": s_vault["manual"]["Moat"],
                    "權重模式": "AI" if st.session_state.stock_vault.get(s, {}).get("insight") else "預設"
                })
        st.dataframe(pd.DataFrame(compare_data).sort_values("目前分數預估", ascending=False))
else:
    st.error("無法獲取股票數據，請檢查 Ticker 是否正確。")

