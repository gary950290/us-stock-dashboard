import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
import json
import os
from datetime import datetime

# =========================
# 0. 數據持久化與配置
# =========================
VAULT_FILE = "investment_vault_2026.json"

def save_vault():
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.stock_vault, f, ensure_ascii=False, indent=4)

def load_vault():
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

# =========================
# 1. API 配置 (針對 2026 Gemini 免費版優化)
# =========================
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 找不到 GOOGLE_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# 2026 推薦使用 flash-lite 獲得更高配額
GEMINI_MODEL = "gemini-2.0-flash-lite-preview-0924" 
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

MAX_REQUESTS_PER_MINUTE = 10  # 2026 免費版趨向嚴格，建議設 10
REQUEST_INTERVAL = 6.5        # 增加冷卻時間

if "api_requests" not in st.session_state:
    st.session_state.api_requests = []

# =========================
# 2. 核心邏輯與初始化
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")

SECTORS = {
    "Mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "資安": ["CRWD", "PANW", "ZS", "OKTA", "FTNT", "S"],
    "半導體": ["NVDA", "AMD", "INTC", "TSM", "AVGO", "ARM", "ASML"],
    "能源/AI電力": ["TSLA", "CEG", "VST", "OKLO", "SMR", "NEE", "GEV"],
    "NeoCloud/比特幣挖礦": ["IREN", "APLD", "WULF", "CIFR", "CORZ"]
}

DEFAULT_WEIGHTS = {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}

if "stock_vault" not in st.session_state:
    st.session_state.stock_vault = load_vault()

def calculate_score(info, weights, manual):
    if not info: return 0
    # 估值分：前瞻 PE 低於 20 則高分
    fwd_pe = info.get("forwardPE", 30) or 30
    val_score = max(0, min(100, (22 / fwd_pe) * 80))
    # 品質分：ROE 優化 (2026 年標準較高)
    roe = info.get("returnOnEquity", 0) or 0
    qual_score = max(0, min(100, roe * 350))
    # 成長分：營收增長
    rev_growth = info.get("revenueGrowth", 0) or 0
    growth_score = max(0, min(100, rev_growth * 250))
    # 手動分：政策與護城河
    moat_policy_score = (manual.get("Policy", 50) + manual.get("Moat", 50)) / 2
    
    total = (val_score * weights["Valuation"] + 
             qual_score * weights["Quality"] + 
             growth_score * weights["Growth"] + 
             moat_policy_score * weights["MoatPolicy"])
    return round(total, 2)

# =========================
# 3. 工具函數
# =========================
@st.cache_data(ttl=3600)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info if info and len(info) > 10 else None
    except:
        return None

def call_gemini_api(prompt, status):
    # 限流機制
    current_time = time.time()
    st.session_state.api_requests = [t for t in st.session_state.api_requests if current_time - t < 60]
    if len(st.session_state.api_requests) >= MAX_REQUESTS_PER_MINUTE:
        status.write("⏳ 接近配額上限，強制冷卻中...")
        time.sleep(10)

    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}
        }
        response = requests.post(f"{GEMINI_API_URL}?key={GOOGLE_API_KEY}", 
                                 headers={"Content-Type": "application/json"}, 
                                 json=payload, timeout=30)
        st.session_state.api_requests.append(time.time())
        
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            # 清理 Markdown 標籤
            json_str = text.replace("```json", "").replace("```", "").strip()
            return json.loads(json_str)
        return None
    except Exception as e:
        status.write(f"❌ API 請求失敗: {str(e)}")
        return None

def run_ai_analysis(symbol, sector, status):
    info = get_stock_data(symbol)
    if not info: return False

    prompt = f"""
    你是 2026 年專業美股策略師。請針對 {symbol} ({sector}) 進行深度評估。
    
    當前數據：
    - 前瞻 PE: {info.get('forwardPE')}
    - ROE: {info.get('returnOnEquity')}
    - 營收增長: {info.get('revenueGrowth')}
    - 市值: {info.get('marketCap')}

    任務：
    1. 針對 2026 年政策環境（如 AI 監管法案、能源補助、地緣政治政策）與同行競爭力，調整權重。
    2. 提供 2026 年的關鍵投資觀點。

    請嚴格回傳 JSON 格式：
    {{
        "sentiment": "看多/中性/看空",
        "summary": "50字內觀點",
        "policy_detail": "2026年具體政策影響分析",
        "peer_comp": "與同行業數據對比簡述",
        "suggested_weights": {{"Valuation": 0.2, "Quality": 0.3, "Growth": 0.3, "MoatPolicy": 0.2}},
        "reason": "權重調整理由"
    }}
    """
    insight = call_gemini_api(prompt, status)
    if insight:
        st.session_state.stock_vault[symbol] = {
            "manual": st.session_state.stock_vault.get(symbol, {}).get("manual", {"Policy": 50, "Moat": 50}),
            "weights": insight["suggested_weights"],
            "insight": insight,
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
        save_vault()
        return True
    return False

# =========================
# 4. UI 介面
# =========================
st.title("🏛️ 2026 專業美股投資評比系統")
st.markdown(f"**當前模型**: `{GEMINI_MODEL}` | **數據狀態**: 2026 即時更新")

# 側邊欄控制
st.sidebar.header("📊 系統控制")
selected_sector = st.sidebar.selectbox("選擇監測產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇分析標的", SECTORS[selected_sector])

if selected_stock not in st.session_state.stock_vault:
    st.session_state.stock_vault[selected_stock] = {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_WEIGHTS.copy(), "insight": None}

# 手動調整與存檔
st.sidebar.subheader("✏️ 專家主觀評分")
def on_manual_change():
    st.session_state.stock_vault[selected_stock]["manual"]["Policy"] = st.session_state[f"{selected_stock}_p"]
    st.session_state.stock_vault[selected_stock]["manual"]["Moat"] = st.session_state[f"{selected_stock}_m"]
    save_vault()

v_manual = st.session_state.stock_vault[selected_stock]["manual"]
st.sidebar.slider("2026 政策受益度", 0, 100, value=v_manual["Policy"], key=f"{selected_stock}_p", on_change=on_manual_change)
st.sidebar.slider("競爭護城河強度", 0, 100, value=v_manual["Moat"], key=f"{selected_stock}_m", on_change=on_manual_change)

# 執行按鈕
col_btn1, col_btn2 = st.sidebar.columns(2)
if col_btn1.button("🤖 AI 單股分析"):
    with st.status(f"正在分析 {selected_stock}...") as s:
        run_ai_analysis(selected_stock, selected_sector, s)
    st.rerun()

if col_btn2.button("🚀 產業一鍵掃描"):
    with st.status(f"批次處理 {selected_sector}...") as s:
        for symbol in SECTORS[selected_sector]:
            s.write(f"正在評估 {symbol}...")
            run_ai_analysis(symbol, selected_sector, s)
            time.sleep(REQUEST_INTERVAL)
    st.rerun()

# 主介面顯示
info = get_stock_data(selected_stock)
if info:
    vault_data = st.session_state.stock_vault[selected_stock]
    score = calculate_score(info, vault_data["weights"], vault_data["manual"])
    
    # 頂部指標
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎯 綜合評分", f"{score} / 100")
    m2.metric("前瞻 PE", f"{info.get('forwardPE', 'N/A')}x")
    m3.metric("ROE", f"{info.get('returnOnEquity', 0)*100:.1f}%")
    m4.metric("營收增長", f"{info.get('revenueGrowth', 0)*100:.1f}%")

    # AI 深度見解
    if vault_data.get("insight"):
        ins = vault_data["insight"]
        with st.container(border=True):
            st.subheader(f"🤖 AI 2026 投資洞察 ({ins['sentiment']})")
            st.write(f"**觀點總結**: {ins['summary']}")
            col_ins1, col_ins2 = st.columns(2)
            with col_ins1:
                st.info(f"**2026 政策與監管**\n\n{ins.get('policy_detail', 'N/A')}")
            with col_ins2:
                st.success(f"**同行業競爭地位**\n\n{ins.get('peer_comp', 'N/A')}")
            st.caption(f"💡 權重調整理由: {ins['reason']}")

    # 產業橫向對比表
    st.divider()
    st.subheader(f"🏭 {selected_sector} 產業橫向排序 (基於 2026 AI 權重)")
    
    compare_data = []
    for s in SECTORS[selected_sector]:
        s_info = get_stock_data(s)
        s_vault = st.session_state.stock_vault.get(s, {"manual":{"Policy":50,"Moat":50}, "weights":DEFAULT_WEIGHTS})
        if s_info:
            s_score = calculate_score(s_info, s_vault["weights"], s_vault["manual"])
            compare_data.append({
                "股票代號": s,
                "綜合分數": s_score,
                "前瞻 PE": f"{s_info.get('forwardPE', 0):.1f}x",
                "2026 政策分": s_vault["manual"]["Policy"],
                "護城河分": s_vault["manual"]["Moat"],
                "AI 狀態": "✅ 已優化" if s_vault.get("insight") else "⚪ 預設",
                "市值 (B)": round(s_info.get("marketCap", 0)/1e9, 1)
            })
    
    if compare_data:
        df_compare = pd.DataFrame(compare_data).sort_values("綜合分數", ascending=False)
        st.table(df_compare) # 使用 table 或 dataframe
else:
    st.error("無法獲取數據，請確認網路連線或稍後再試。")

st.sidebar.divider()
if st.sidebar.button("🗑️ 清除所有快取"):
    st.cache_data.clear()
    st.session_state.stock_vault = {}
    if os.path.exists(VAULT_FILE): os.remove(VAULT_FILE)
    st.rerun()
