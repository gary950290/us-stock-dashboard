import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json
import os

# =========================
# 1. 數據持久化邏輯 (新增)
# =========================
CONFIG_FILE = "invest_config_2026.json"

def save_config():
    """將目前的權重與手動評分存入 JSON 檔案"""
    config_data = {
        "weights": st.session_state.weights,
        "manual_scores": st.session_state.manual_scores
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f)

def load_config():
    """從 JSON 檔案載入設定"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return None
    return None

# =========================
# 初始化 Gemini API
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    # 使用 2.0 Flash 確保速度與穩定性
    model = genai.GenerativeModel('gemini-2.0-flash-exp') 
except Exception as e:
    st.error("❌ 找不到 GEMINI_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 設定與 CSS 注入
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

st.markdown("""
<style>
    .stApp { overflow-y: auto !important; max-height: 100vh; }
    div[data-testid^="stVerticalBlock"] { overflow-y: auto !important; }
</style>
""", unsafe_allow_html=True)

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

SECTOR_CONFIG = {
    "Mag7": {"weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "AI 變現效率與現金流"},
    "資安": {"weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20}, "focus": "毛利率與平台定價權"},
    "能源": {"weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35}, "focus": "FCF 與政策補貼"},
    "半導體": {"weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15}, "focus": "前瞻盈餘與製程領先"},
    "NeoCloud": {"weights": {"Valuation": 0.10, "Quality": 0.15, "Growth": 0.60, "MoatPolicy": 0.15}, "focus": "未來規模與成長寬容度"}
}

# =========================
# 初始化 Session State (修改：優先讀取存檔)
# =========================
saved_data = load_config()

if "weights" not in st.session_state:
    if saved_data and "weights" in saved_data:
        st.session_state.weights = saved_data["weights"]
    else:
        st.session_state.weights = {s: SECTOR_CONFIG[s]["weights"].copy() for s in SECTORS.keys()}

if "manual_scores" not in st.session_state:
    if saved_data and "manual_scores" in saved_data:
        st.session_state.manual_scores = saved_data["manual_scores"]
    else:
        st.session_state.manual_scores = {}

# =========================
# 核心邏輯 (計算引擎保持不變，維持你的穩定性)
# =========================
@st.cache_data(ttl=300)
def get_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info
    except: return None

def get_tier(score):
    if score >= 80: return "Tier 1 (強烈優先配置) 🚀"
    elif score >= 60: return "Tier 2 (穩健配置) ⚖️"
    else: return "Tier 3 (觀察或減碼) ⚠️"

def calculate_2026_score(info, sector, manual_scores, sector_avg_data):
    # (此處保留你原始的計算邏輯代碼，不作修改以確保正確性)
    symbol = info.get("symbol")
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50)) if fwd_pe else 50
    
    roe = info.get("returnOnEquity", 0)
    fcf = info.get("freeCashflow", 0)
    gross_margin = info.get("grossMargins", 0)
    op_margin = info.get("operatingMargins", 0)
    
    qual_score = 50
    if sector == "Mag7": qual_score = max(0, min(100, roe * 400))
    elif sector == "資安": qual_score = max(0, min(100, gross_margin * 100)) + (20 if gross_margin > 0.75 else 0)
    elif sector == "能源": qual_score = 100 if fcf > 0 else 0
    elif sector == "半導體": qual_score = max(0, min(100, op_margin * 300))
    
    rev_growth = info.get("revenueGrowth", 0)
    growth_score = max(0, min(100, rev_growth * 200))
    
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score) / 2
    
    w = st.session_state.weights[sector] # 使用當前 session 中的權重
    total_score = (val_score * w["Valuation"] + qual_score * w["Quality"] + 
                   growth_score * w["Growth"] + moat_policy_score * w["MoatPolicy"])
    
    adj = -10 if (sector in ["能源", "NeoCloud"] and fcf < 0) else 0
    total_score = max(0, min(100, total_score + adj))
    
    return {"Total": round(total_score, 2), "Valuation": round(val_score, 2), 
            "Quality": round(qual_score, 2), "Growth": round(growth_score, 2), 
            "MoatPolicy": round(moat_policy_score, 2), "Adjustment": adj}

# =========================
# AI 分析增強 (新增：一鍵全產業分析)
# =========================
def analyze_sector_ai(sector, status):
    """一鍵分析該產業內所有代表性股票並決定最終權重"""
    symbols = SECTORS[sector][:3] # 取前三名代表性股票節省 Token
    status.write(f"🔍 正在抓取 {sector} 產業數據：{', '.join(symbols)}...")
    
    context_news = ""
    for s in symbols:
        t = yf.Ticker(s)
        n_list = t.news[:2]
        context_news += f"\n[{s} 新聞]: " + " | ".join([n['title'] for n in n_list if 'title' in n])

    prompt = f"""
    你是一位資深分析師。請針對 {sector} 產業目前的趨勢進行分析。
    最新資訊：{context_news}
    請評估 2026 年該產業的環境，並提供一組新的權重建議。
    請嚴格以 JSON 格式回覆：
    {{
        "sentiment": "利好/利空/中性",
        "summary": "產業總結",
        "suggested_weights": {{ "Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float }},
        "reason": "調整理由"
    }}
    *注意：權重總和必須為 1.0*
    """
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        result = json.loads(clean_json)
        return result
    except Exception as e:
        status.error(f"分析 {sector} 失敗: {e}")
        return None

# =========================
# UI 佈局
# =========================
st.sidebar.header("⚙️ 2026 評比設定")
selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 手動評分初始化與保存
if selected_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[selected_stock] = {"Policy": 50, "Moat": 50}

# 滑塊更新回調
def on_slider_change():
    st.session_state.manual_scores[selected_stock]["Policy"] = st.session_state[f"p_{selected_stock}"]
    st.session_state.manual_scores[selected_stock]["Moat"] = st.session_state[f"m_{selected_stock}"]
    save_config() # 每次滑動自動保存

st.sidebar.subheader(f"✏️ {selected_stock} 自定義評分")
m_policy = st.sidebar.slider("政策受益度", 0, 100, 
                           value=st.session_state.manual_scores[selected_stock]["Policy"],
                           key=f"p_{selected_stock}", on_change=on_slider_change)
m_moat = st.sidebar.slider("護城河粘性", 0, 100, 
                         value=st.session_state.manual_scores[selected_stock]["Moat"],
                         key=f"m_{selected_stock}", on_change=on_slider_change)

# --- 一鍵全產業 AI 分析按鈕 ---
if st.sidebar.button(f"🌐 一鍵優化 {selected_sector} 權重"):
    with st.status(f"正在對 {selected_sector} 進行深度產業掃描...", expanded=True) as status:
        result = analyze_sector_ai(selected_sector, status)
        if result:
            st.session_state.weights[selected_sector] = result["suggested_weights"]
            st.session_state[f"last_insight_{selected_sector}"] = result
            save_config() # 儲存 AI 調整後的權重
            status.update(label="✅ 產業權重優化完成！", state="complete")

# 顯示該產業最新的 AI 洞察
insight_key = f"last_insight_{selected_sector}"
if insight_key in st.session_state:
    ins = st.session_state[insight_key]
    st.success(f"**AI 產業趨勢 ({ins['sentiment']})**: {ins['summary']}")
    with st.expander("查看權重調整理由"):
        st.write(ins['reason'])

# =========================
# 主要數據展示
# =========================
info = get_stock_data(selected_stock)
if info:
    sector_avg_data = {"avg_fwd_pe": 25}
    scores = calculate_2026_score(info, selected_sector, st.session_state.manual_scores[selected_stock], sector_avg_data)

    col1, col2, col3 = st.columns(3)
    col1.metric("🎯 綜合評分", scores["Total"])
    col2.metric("投資評級", get_tier(scores["Total"]))
    col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))

    # 表格整理：詳細評分與當前權重 (符合你的 user preference)
    st.subheader(f"📊 {selected_stock} 詳細評估表")
    detail_df = pd.DataFrame({
        "評估維度": ["前瞻估值", "獲利質量", "成長動能", "政策與護城河"],
        "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
        "目前應用權重": [f"{st.session_state.weights[selected_sector][k]*100:.0f}%" for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
    })
    st.table(detail_df)

    # 產業橫向比較
    with st.expander(f"🏭 {selected_sector} 產業同行業橫向排序 (自動更新)"):
        results = []
        for s in SECTORS[selected_sector]:
            s_info = get_stock_data(s)
            if s_info:
                # 獲取該股的手動評分（若無則 50）
                m_s = st.session_state.manual_scores.get(s, {"Policy": 50, "Moat": 50})
                s_scores = calculate_2026_score(s_info, selected_sector, m_s, sector_avg_data)
                results.append({
                    "股票代碼": s,
                    "綜合分數": s_scores["Total"],
                    "評級": get_tier(s_scores["Total"]),
                    "Fwd PE": s_info.get("forwardPE", 0),
                    "市值 (B)": round(s_info.get("marketCap", 0)/1e9, 2)
                })
        st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False), use_container_width=True)
else:
    st.error("數據獲取中或該代碼暫無資料...")

