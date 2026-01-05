import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
import json
import os

# =========================
# 0. 數據持久化配置
# =========================
VAULT_FILE = "investment_vault_2026.json"

def save_vault():
    """將當前 session_state 數據寫入 JSON 檔案"""
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.stock_vault, f, ensure_ascii=False, indent=4)

def load_vault():
    """從 JSON 檔案讀取數據"""
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

# =========================
# 1. Google Gemini API 配置
# =========================
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 找不到 GOOGLE_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"

# API 限流設定 (Gemini 免費版)
MAX_REQUESTS_PER_MINUTE = 15 
REQUEST_INTERVAL = 60 / MAX_REQUESTS_PER_MINUTE 

if "api_requests" not in st.session_state:
    st.session_state.api_requests = []

# =========================
# 2. 核心配置與初始化
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")

SECTORS = {
    "Mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "資安": ["CRWD", "PANW", "ZS", "OKTA", "FTNT", "S"],
    "半導體": ["NVDA", "AMD", "INTC", "TSM", "AVGO"],
    "能源/核能": ["TSLA", "CEG", "FLNC", "VST", "OKLO", "SMR", "BE", "GEV"],
    "NeoCloud": ["NBIS", "IREN", "CRWV", "APLD"]
}

DEFAULT_WEIGHTS = {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}

if "stock_vault" not in st.session_state:
    saved_data = load_vault()
    st.session_state.stock_vault = saved_data if saved_data else {}

def calculate_score(info, weights, manual):
    if not info: return 0
    # 估值分 (以 PE 25 為中位數)
    fwd_pe = info.get("forwardPE", 25) or 25
    val_score = max(0, min(100, (25 / fwd_pe) * 50))
    # 質量分 (ROE 基準)
    roe = info.get("returnOnEquity", 0) or 0
    qual_score = max(0, min(100, roe * 400))
    # 成長分 (營收增長基準)
    growth = info.get("revenueGrowth", 0) or 0
    growth_score = max(0, min(100, growth * 200))
    # 政策與護城河 (手動輸入)
    moat_policy_score = (manual.get("Policy", 50) + manual.get("Moat", 50)) / 2

    total = (val_score * weights["Valuation"] + 
             qual_score * weights["Quality"] + 
             growth_score * weights["Growth"] + 
             moat_policy_score * weights["MoatPolicy"])
    return round(total, 2)

# =========================
# 3. 工具函數 (API 與 數據抓取)
# =========================
@st.cache_data(ttl=300)
def get_stock_data(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if info and "symbol" in info:
                return info
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                st.warning(f"⚠️ {symbol}: 抓取失敗 - {str(e)[:50]}")
            time.sleep(1)
    return None

def call_gemini_api(prompt, status):
    # API 限流檢查
    current_time = time.time()
    st.session_state.api_requests = [t for t in st.session_state.api_requests if current_time - t < 60]
    
    if len(st.session_state.api_requests) >= MAX_REQUESTS_PER_MINUTE:
        time.sleep(REQUEST_INTERVAL)

    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}
        }
        response = requests.post(f"{GEMINI_API_URL}?key={GOOGLE_API_KEY}", 
                                 headers={"Content-Type": "application/json"}, 
                                 json=payload, timeout=30)
        st.session_state.api_requests.append(time.time())
        
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            # 提取 JSON 內容
            json_str = text.split("```json")[1].split("```")[0] if "```json" in text else text
            return json.loads(json_str)
    except Exception as e:
        status.write(f"❌ API 錯誤: {str(e)[:50]}")
    return None

def run_ai_analysis(symbol, sector, status):
    info = get_stock_data(symbol)
    if not info: return False

    prompt = f"""你是專業美股分析師。分析股票 {symbol} ({sector})。
    數據: PE={info.get('forwardPE')}, ROE={info.get('returnOnEquity')}, Growth={info.get('revenueGrowth')}。
    請根據 2026 年政府政策（如 AI 電力需求、晶片法案 2.0、資安規範）調整權重。
    回傳 JSON 格式:
    {{
    "sentiment": "看多/中性/看空",
    "summary": "50字內總結",
    "suggested_weights": {{"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}},
    "reason": "100字內理由"
    }}"""
    
    insight = call_gemini_api(prompt, status)
    if insight:
        st.session_state.stock_vault[symbol] = {
            "manual": st.session_state.stock_vault.get(symbol, {}).get("manual", {"Policy": 50, "Moat": 50}),
            "weights": insight["suggested_weights"],
            "insight": insight
        }
        save_vault()
        return True
    return False

# =========================
# 4. UI 呈現
# =========================
st.title("🏛️ 2026 專業美股投資評比系統")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 初始化 session 數據
if selected_stock not in st.session_state.stock_vault:
    st.session_state.stock_vault[selected_stock] = {
        "manual": {"Policy": 50, "Moat": 50},
        "weights": DEFAULT_WEIGHTS.copy(),
        "insight": None
    }

# 手動評分側邊欄
st.sidebar.subheader("✏️ 手動評分")
v_m = st.session_state.stock_vault[selected_stock]["manual"]
p_val = st.sidebar.slider("政策受益度", 0, 100, v_m["Policy"], key=f"{selected_stock}_p")
m_val = st.sidebar.slider("護城河粘性", 0, 100, v_m["Moat"], key=f"{selected_stock}_m")
st.session_state.stock_vault[selected_stock]["manual"] = {"Policy": p_val, "Moat": m_val}

if st.sidebar.button("🤖 AI 深度分析單股"):
    with st.status(f"分析 {selected_stock}...") as status:
        if run_ai_analysis(selected_stock, selected_sector, status):
            st.rerun()

# 主界面顯示
info = get_stock_data(selected_stock)
if info:
    s_data = st.session_state.stock_vault[selected_stock]
    score = calculate_score(info, s_data["weights"], s_data["manual"])
    
    if s_data.get("insight"):
        ins = s_data["insight"]
        st.info(f"### 🤖 AI 洞察 ({ins['sentiment']})\n{ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", score)
    col2.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    col3.metric("營收增長", f"{info.get('revenueGrowth', 0)*100:.1f}%")

    # 產業橫向比較表格
    st.subheader(f"🏭 {selected_sector} 產業橫向排序")
    compare_data = []
    for s in SECTORS[selected_sector]:
        s_info = get_stock_data(s)
        if s_info:
            s_v = st.session_state.stock_vault.get(s, {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_WEIGHTS})
            s_score = calculate_score(s_info, s_v["weights"], s_v["manual"])
            compare_data.append({
                "股票": s, "評分": s_score, "PE": s_info.get("forwardPE", "N/A"),
                "ROE": f"{s_info.get('returnOnEquity', 0)*100:.1f}%",
                "政策分": s_v["manual"]["Policy"], "狀態": "✅ AI" if s_v.get("insight") else "預設"
            })
    
    df = pd.DataFrame(compare_data).sort_values("評分", ascending=False)
    st.table(df)

else:
    st.error("數據抓取失敗，請重試或更換代碼。")
