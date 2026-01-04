import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
import json
import os  # 新增：用於判斷檔案是否存在

# =========================
# 0. 數據持久化配置 (新增)
# =========================
VAULT_FILE = "investment_vault_2026.json"

def save_vault():
    """將當前 session_state 數據寫入 JSON 檔案"""
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.stock_vault, f, ensure_ascii=False, indent=4)

def load_vault():
    """從 JSON 檔案讀取數據，若檔案不存在則回傳空字典"""
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

# =========================
# 1. OpenRouter 配置 (2026 免費模型)
# =========================
OR_MODELS = [
    "google/gemini-2.5-flash-preview-09-2025:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen3-coder:free",
    "openrouter/auto"
]

try:
    OR_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except:
    st.error("❌ 找不到 OPENROUTER_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 2. 核心配置與初始化
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")

SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

DEFAULT_WEIGHTS = {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}

# 【重要：優先從檔案讀取舊有數據，避免重置】
if "stock_vault" not in st.session_state:
    saved_data = load_vault()
    st.session_state.stock_vault = saved_data if saved_data else {}

def calculate_score(info, weights, manual):
    if not info: return 0
    fwd_pe = info.get("forwardPE", 25) or 25
    val_score = max(0, min(100, (25 / fwd_pe) * 50))
    qual_score = max(0, min(100, (info.get("returnOnEquity", 0) or 0) * 400))
    growth_score = max(0, min(100, (info.get("revenueGrowth", 0) or 0) * 200))
    moat_policy_score = (manual.get("Policy", 50) + manual.get("Moat", 50)) / 2
    
    total = (val_score * weights["Valuation"] + 
             qual_score * weights["Quality"] + 
             growth_score * weights["Growth"] + 
             moat_policy_score * weights["MoatPolicy"])
    return round(total, 2)

# =========================
# 3. 工具函數
# =========================

@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info
    except: return None

def call_openrouter(prompt, status):
    headers = {"Authorization": f"Bearer {OR_API_KEY}", "HTTP-Referer": "http://localhost:8501", "Content-Type": "application/json"}
    for model in OR_MODELS:
        try:
            status.write(f"🤖 嘗試模型: {model}...")
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, data=json.dumps(payload), timeout=25)
            if res.status_code == 200:
                return json.loads(res.json()['choices'][0]['message']['content'])
        except: continue
    return None

def run_ai_analysis(symbol, sector, status):
    info = get_stock_data(symbol)
    if not info: return False
    
    if symbol not in st.session_state.stock_vault:
        st.session_state.stock_vault[symbol] = {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_WEIGHTS.copy(), "insight": None}
    
    prompt = f"分析 {symbol} ({sector})。數據: PE={info.get('forwardPE')}, ROE={info.get('returnOnEquity')}。請微調權重(總和1.0)。回傳JSON: {{'sentiment': '...', 'summary': '...', 'suggested_weights': {{'Valuation': f, 'Quality': f, 'Growth': f, 'MoatPolicy': f}}, 'reason': '...'}}"
    
    insight = call_openrouter(prompt, status)
    if insight:
        st.session_state.stock_vault[symbol]["weights"] = insight["suggested_weights"]
        st.session_state.stock_vault[symbol]["insight"] = insight
        save_vault()  # 分析完立即存檔
        return True
    return False

# =========================
# 4. UI 與 持久化邏輯
# =========================
st.title("🏛️ 2026 專業美股投資評比系統")

selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 精準初始化
if selected_stock not in st.session_state.stock_vault:
    st.session_state.stock_vault[selected_stock] = {
        "manual": {"Policy": 50, "Moat": 50},
        "weights": DEFAULT_WEIGHTS.copy(),
        "insight": None
    }

# 手動評分同步並存檔
def sync_vault():
    st.session_state.stock_vault[selected_stock]["manual"]["Policy"] = st.session_state[f"{selected_stock}_p"]
    st.session_state.stock_vault[selected_stock]["manual"]["Moat"] = st.session_state[f"{selected_stock}_m"]
    save_vault()  # 滑動 Slider 後立即存檔

st.sidebar.subheader("✏️ 2026 手動評分")
vault_m = st.session_state.stock_vault[selected_stock]["manual"]
st.sidebar.slider("政策受益度", 0, 100, value=vault_m["Policy"], key=f"{selected_stock}_p", on_change=sync_vault)
st.sidebar.slider("護城河粘性", 0, 100, value=vault_m["Moat"], key=f"{selected_stock}_m", on_change=sync_vault)

col_b1, col_b2 = st.sidebar.columns(2)
if col_b1.button("🤖 單股 AI 分析"):
    with st.status(f"分析 {selected_stock}...", expanded=False) as status:
        if run_ai_analysis(selected_stock, selected_sector, status):
            status.update(label="✅ 分析完成", state="complete")
            st.rerun()

if col_b2.button("🚀 一鍵分析全產業"):
    with st.status(f"處理 {selected_sector}...", expanded=True) as status:
        for s in SECTORS[selected_sector]:
            status.write(f"正在處理 {s}...")
            run_ai_analysis(s, selected_sector, status)
            time.sleep(0.5)
        status.update(label="✅ 全產業優化完成", state="complete")
        st.rerun()

# =========================
# 5. 結果呈現
# =========================
info = get_stock_data(selected_stock)
if info:
    s_data = st.session_state.stock_vault[selected_stock]
    total_score = calculate_score(info, s_data["weights"], s_data["manual"])

    if s_data["insight"]:
        ins = s_data["insight"]
        st.info(f"### AI 洞察 ({ins['sentiment']}): {ins['summary']}\n**權重調整理由**: {ins['reason']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("🎯 綜合評分", total_score)
    c2.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    c3.metric("狀態", "AI 已優化" if s_data["insight"] else "預設模式")

    with st.expander("🏭 查看產業橫向排序 (包含已存檔數據)"):
        compare_list = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            s_v = st.session_state.stock_vault.get(s, {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_WEIGHTS.copy()})
            if s_info:
                s_total = calculate_score(s_info, s_v["weights"], s_v["manual"])
                compare_list.append({
                    "股票": s, "綜合分數": s_total, 
                    "前瞻PE": s_info.get("forwardPE"),
                    "政策得分": s_v["manual"]["Policy"], "護城河": s_v["manual"]["Moat"],
                    "權重狀態": "AI 優化" if "insight" in s_v and s_v["insight"] else "預設"
                })
        if compare_list:
            st.dataframe(pd.DataFrame(compare_list).sort_values("綜合分數", ascending=False), use_container_width=True)

---
### 更新說明：
1.  **檔案存儲**：新增 `investment_vault_2026.json` 作為本地資料庫。只要這個檔案在，您的設定就不會丟失。
2.  **自動讀取**：程式啟動時會檢查檔案，如果有舊數據就直接載入到 `st.session_state.stock_vault`。
3.  **即時儲存**：在 AI 分析完成時、以及您滑動「政策」或「護城河」Slider 時，都會立刻調用 `save_vault()`。

請問您需要我針對 2026 年特定的政府補貼政策（如能源晶片法案後續）為您預設一些產業初始分數嗎？
