import streamlit as st
import pandas as pd
import yfinance as yf
import time
import requests
import json
import os
from requests import Session

# =========================
# 0. 數據持久化配置
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
# 1. API 與 Session 配置 (解決 Rate Limit)
# =========================
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 找不到 GOOGLE_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"

def get_custom_session():
    """模擬真實瀏覽器以繞過 Yahoo Finance 的封鎖"""
    session = Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    })
    return session

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
    st.session_state.stock_vault = load_vault()

# =========================
# 3. 工具函數
# =========================
@st.cache_data(ttl=600)
def get_stock_data(symbol):
    """獲取股票數據，加入 Session 偽裝"""
    session = get_custom_session()
    try:
        ticker = yf.Ticker(symbol, session=session)
        info = ticker.info
        if info and "symbol" in info:
            return info
    except Exception as e:
        st.error(f"⚠️ {symbol} 數據獲取失敗: {str(e)}")
    return None

def calculate_score(info, weights, manual):
    if not info: return 0
    fwd_pe = info.get("forwardPE", 25) or 25
    val_score = max(0, min(100, (25 / fwd_pe) * 50))
    roe = info.get("returnOnEquity", 0) or 0
    qual_score = max(0, min(100, roe * 400))
    growth = info.get("revenueGrowth", 0) or 0
    growth_score = max(0, min(100, growth * 200))
    moat_policy_score = (manual.get("Policy", 50) + manual.get("Moat", 50)) / 2

    total = (val_score * weights["Valuation"] + 
             qual_score * weights["Quality"] + 
             growth_score * weights["Growth"] + 
             moat_policy_score * weights["MoatPolicy"])
    return round(total, 2)

def call_gemini_api(prompt):
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7}
        }
        response = requests.post(f"{GEMINI_API_URL}?key={GOOGLE_API_KEY}", json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            json_str = text.split("```json")[1].split("```")[0] if "```json" in text else text
            return json.loads(json_str)
    except:
        return None
    return None

def run_ai_analysis(symbol, sector):
    info = get_stock_data(symbol)
    if not info: return False

    prompt = f"""你是 2026 年專業美股分析師。分析股票 {symbol} ({sector})。
    最新數據: PE={info.get('forwardPE')}, ROE={info.get('returnOnEquity')}, 營收增長={info.get('revenueGrowth')}。
    考慮 2026 年政府政策（如 AI 電力補貼、各國資安法規、晶片法案進度）來調整權重。
    請以繁體中文回答並僅回傳 JSON 格式:
    {{
    "sentiment": "看多/中性/看空",
    "summary": "50字內投資總結",
    "suggested_weights": {{"Valuation": 0.2, "Quality": 0.3, "Growth": 0.3, "MoatPolicy": 0.2}},
    "reason": "為什麼這樣調整權重的細節"
    }}"""
    
    insight = call_gemini_api(prompt)
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
# 4. UI 邏輯與呈現
# =========================
st.title("🏛️ 2026 專業美股投資評比系統")
st.sidebar.header("控制台")

selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

if selected_stock not in st.session_state.stock_vault:
    st.session_state.stock_vault[selected_stock] = {
        "manual": {"Policy": 50, "Moat": 50},
        "weights": DEFAULT_WEIGHTS.copy(),
        "insight": None
    }

# 側邊欄滑塊
st.sidebar.subheader("✏️ 專家手動評分")
current_v = st.session_state.stock_vault[selected_stock]
p_val = st.sidebar.slider("2026 政策受益度", 0, 100, current_v["manual"]["Policy"])
m_val = st.sidebar.slider("護城河/技術領先度", 0, 100, current_v["manual"]["Moat"])
st.session_state.stock_vault[selected_stock]["manual"] = {"Policy": p_val, "Moat": m_val}

if st.sidebar.button("🤖 啟動 Gemini AI 分析"):
    with st.status(f"正在評估 {selected_stock} 的政策風險與估值...") as status:
        if run_ai_analysis(selected_stock, selected_sector):
            status.update(label="分析完成！", state="complete")
            st.rerun()

# 顯示主要數據
info = get_stock_data(selected_stock)
if info:
    s_data = st.session_state.stock_vault[selected_stock]
    total_score = calculate_score(info, s_data["weights"], s_data["manual"])
    
    if s_data.get("insight"):
        ins = s_data["insight"]
        st.success(f"### 🤖 AI 投資洞察: {ins['sentiment']}\n**觀點**: {ins['summary']}\n\n**權重理由**: {ins['reason']}")

    # 數據指標卡
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🎯 綜合評分", total_score)
    c2.metric("前瞻 PE", info.get("forwardPE", "N/A"))
    c3.metric("ROE", f"{info.get('returnOnEquity', 0)*100:.2f}%")
    c4.metric("營收增長", f"{info.get('revenueGrowth', 0)*100:.1f}%")

    # 同行業比較表格 (表格呈現要求)
    st.subheader(f"📊 {selected_sector} 產業同行業橫向比較 (2026 基準)")
    compare_list = []
    with st.spinner("正在對比同業數據..."):
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            if s_info:
                s_v = st.session_state.stock_vault.get(s, {"manual": {"Policy": 50, "Moat": 50}, "weights": DEFAULT_WEIGHTS})
                s_score = calculate_score(s_info, s_v["weights"], s_v["manual"])
                compare_list.append({
                    "股票代號": s,
                    "綜合總分": s_score,
                    "前瞻 PE": s_info.get("forwardPE", "N/A"),
                    "ROE %": round(s_info.get("returnOnEquity", 0)*100, 2),
                    "政策分": s_v["manual"]["Policy"],
                    "護城河": s_v["manual"]["Moat"],
                    "狀態": "✅ AI 已評估" if s_v.get("insight") else "⚪ 預設"
                })
    
    if compare_list:
        df_comp = pd.DataFrame(compare_list).sort_values("綜合總分", ascending=False)
        st.dataframe(df_comp, use_container_width=True, hide_index=True)

    # 2026 政策與估值評估細節
    with st.expander("📝 2026 政府政策與估值同行業詳細評估"):
        st.markdown(f"""
        | 評估維度 | 2026 政策影響 | 同業比較點 |
        | :--- | :--- | :--- |
        | **政策面** | 針對 {selected_sector} 領域，政府進行中的補貼與監管。 | 與同板塊其他公司相比的受益程度。 |
        | **估值面** | 基於當前 PE 與 2026 預期成長率的匹配度。 | 行業平均 PE 基準下的溢價/折價分析。 |
        | **競爭力** | {selected_stock} 在技術門檻與護城河的最新進展。 | 市場份額（Market Share）的增長趨勢。 |
        """)
else:
    st.warning("⚠️ 目前無法從 Yahoo Finance 獲取數據。這通常是 IP 被暫時限制，請等待幾分鐘或在本地運行。")
