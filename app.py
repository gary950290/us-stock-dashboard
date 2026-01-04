import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai
import json

# 設定重試次數
MAX_RETRIES = 3 

# =========================
# 初始化 Gemini API
# =========================
try:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    # 使用環境支援的模型
    model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
except Exception as e:
    st.error("❌ 找不到 GEMINI_API_KEY。請在 Streamlit Secrets 中設定。")
    st.stop()

# =========================
# 設定與 CSS 注入
# =========================
st.set_page_config(page_title="2026 專業美股投資評比系統", layout="wide")
st.title("🏛️ 2026 專業美股投資評比系統")
st.caption("基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板")

# 强制 CSS 注入：解決 iFrame/嵌入式環境中的滾動條問題
st.markdown(
    """
    <style>
    /* 針對主要的 Streamlit App 容器，強制啟用垂直滾動 */
    .stApp {
        overflow-y: auto !important;
        max-height: 100vh;
    }
    /* 確保所有垂直區塊也能正確處理溢出 */
    div[data-testid^="stVerticalBlock"] {
        overflow-y: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

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

# =========================
# 核心權重配置 (2026 邏輯)
# =========================
SECTOR_CONFIG = {
    "Mag7": {
        "weights": {"Valuation": 0.25, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.20},
        "focus": "AI 變現效率與現金流"
    },
    "資安": {
        "weights": {"Valuation": 0.20, "Quality": 0.30, "Growth": 0.30, "MoatPolicy": 0.20},
        "focus": "毛利率與平台定價權"
    },
    "能源": {
        "weights": {"Valuation": 0.15, "Quality": 0.35, "Growth": 0.15, "MoatPolicy": 0.35},
        "focus": "FCF 與政策補貼"
    },
    "半導體": {
        "weights": {"Valuation": 0.30, "Quality": 0.25, "Growth": 0.30, "MoatPolicy": 0.15},
        "focus": "前瞻盈餘與製程領先"
    },
    "NeoCloud": {
        "weights": {"Valuation": 0.10, "Quality": 0.15, "Growth": 0.60, "MoatPolicy": 0.15},
        "focus": "未來規模與成長寬容度"
    }
}

# =========================
# 持久化儲存函數
# =========================
def save_to_storage(key, data):
    """將數據保存到 Streamlit 持久化儲存"""
    try:
        st.session_state[f"persistent_{key}"] = json.dumps(data)
    except Exception as e:
        st.warning(f"儲存 {key} 失敗: {e}")

def load_from_storage(key, default=None):
    """從 Streamlit 持久化儲存讀取數據"""
    try:
        stored_key = f"persistent_{key}"
        if stored_key in st.session_state:
            return json.loads(st.session_state[stored_key])
    except Exception as e:
        st.warning(f"讀取 {key} 失敗: {e}")
    return default

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def get_stock_data(symbol, retry_count=3):
    """獲取股票數據，包含重試機制和詳細錯誤處理"""
    for attempt in range(retry_count):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 檢查是否獲取到有效數據
            if info and len(info) > 5:  # 確保獲取到足夠的數據
                return info
            else:
                if attempt < retry_count - 1:
                    time.sleep(1)  # 等待後重試
                    continue
                else:
                    print(f"WARNING: {symbol} 返回數據不完整")
                    return None
                    
        except Exception as e:
            print(f"ERROR getting data for {symbol} (attempt {attempt + 1}): {e}")
            if attempt < retry_count - 1:
                time.sleep(1)
            else:
                return None
    return None

def get_tier(score):
    if score >= 80: return "Tier 1 (強烈優先配置) 🚀"
    elif score >= 60: return "Tier 2 (穩健配置) ⚖️"
    else: return "Tier 3 (觀察或減碼) ⚠️"

# =========================
# 評分引擎 (2026 專業邏輯)
# =========================
def calculate_2026_score(info, sector, manual_scores, sector_avg_data, stock_weights):
    """計算股票評分，增加數據驗證"""
    if not info:
        return None
        
    symbol = info.get("symbol", "UNKNOWN")
    
    # 1. 前瞻估值 (Valuation)
    fwd_pe = info.get("forwardPE")
    avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
    val_score = 50
    if fwd_pe and fwd_pe > 0:
        # 標準化：個股 Fwd PE / 產業平均
        val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
        if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9: # 低於均值 10% 以上
            val_score = min(100, val_score * 1.2)
    
    # 2. 獲利質量 (Quality)
    roe = info.get("returnOnEquity", 0) or 0
    fcf = info.get("freeCashflow", 0) or 0
    gross_margin = info.get("grossMargins", 0) or 0
    op_margin = info.get("operatingMargins", 0) or 0
    
    qual_score = 50
    if sector == "Mag7":
        qual_score = max(0, min(100, roe * 400))
    elif sector == "資安":
        qual_score = max(0, min(100, gross_margin * 100))
        if gross_margin > 0.75: qual_score += 20 # 75% 毛利溢價
    elif sector == "能源":
        qual_score = 100 if fcf > 0 else 50
        if fcf < 0: qual_score -= 50 # FCF 為負硬性扣減
    elif sector == "半導體":
        qual_score = max(0, min(100, op_margin * 300))
    elif sector == "NeoCloud":
        qual_score = 50 # 關注 Burn Rate，預設中性
        
    # 3. 成長動能 (Growth)
    rev_growth = info.get("revenueGrowth", 0) or 0
    growth_score = max(0, min(100, rev_growth * 200))
    
    if sector == "Mag7" and rev_growth > 0.2: growth_score *= 1.2
    if sector == "NeoCloud" and rev_growth > 0.4: growth_score = 100
    
    # 4. 政策與護城河 (MoatPolicy)
    policy_score = manual_scores.get("Policy", 50)
    moat_score = manual_scores.get("Moat", 50)
    moat_policy_score = (policy_score + moat_score) / 2
    
    # 5. 綜合計算 - 使用傳入的個股權重
    w = stock_weights
    total_score = (
        val_score * w["Valuation"] +
        qual_score * w["Quality"] +
        growth_score * w["Growth"] +
        moat_policy_score * w["MoatPolicy"]
    )
    
    # 6. 懲罰與加成係數 (最終調整)
    final_adjustment = 0
    if sector == "資安" and gross_margin > 0.75: final_adjustment += 5
    if (sector == "能源" or sector == "NeoCloud") and fcf < 0: final_adjustment -= 10
    
    total_score = max(0, min(100, total_score + final_adjustment))
    
    return {
        "Total": round(total_score, 2),
        "Valuation": round(val_score, 2),
        "Quality": round(qual_score, 2),
        "Growth": round(growth_score, 2),
        "MoatPolicy": round(moat_policy_score, 2),
        "Adjustment": final_adjustment
    }

# =========================
# AI 洞察 (Gemini)
# =========================

def call_gemini_with_retry(prompt, status, max_retries=MAX_RETRIES):
    """實作指數退避重試機制，確保 API 呼叫的穩定性。"""
    delay = 2  # 初始延遲 (秒)
    for attempt in range(max_retries):
        try:
            # 顯示重試狀態，更新 status 容器內的文字
            status.write(f"🤖 嘗試呼叫 Gemini API (第 {attempt + 1} 次嘗試)...")
            
            # 執行 API 呼叫
            response = model.generate_content(prompt)
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            
            # 檢查是否為空內容
            if not clean_json:
                raise ValueError("API 返回空響應或無效內容，無法解析 JSON。")

            # 嘗試解析 JSON
            insight = json.loads(clean_json)
            # 成功則立即返回
            status.write("✅ Gemini API 呼叫成功並解析 JSON。")
            return insight

        except Exception as e:
            if attempt < max_retries - 1:
                # 如果不是最後一次嘗試，等待並重試
                status.warning(f"⚠️ 呼叫失敗，將在 {delay} 秒後重試。錯誤類型: {type(e).__name__}")
                time.sleep(delay)
                delay *= 2  # 指數退避
            else:
                # 最後一次嘗試失敗，顯示最終錯誤
                status.error(f"❌ Gemini 分析失敗：連續重試 {max_retries} 次後仍失敗。錯誤類型: {type(e).__name__} - {e}")
                print(f"DEBUG ERROR: call_gemini_with_retry failed after {max_retries} attempts. Error: {e}")
                return None
    return None

def get_ai_market_insight(symbol, sector, current_weights, status):
    """準備提示詞並呼叫帶有重試機制的 API 函數。"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news[:5]
        
        # 安全地提取新聞標題
        safe_news_titles = [f"- {n['title']}" for n in news if isinstance(n, dict) and 'title' in n]
        
        if safe_news_titles:
            news_text = "\n".join(safe_news_titles)
        else:
            news_text = f"找不到最新新聞或新聞格式有誤。請基於 {symbol} 過去一週的行業趨勢進行一般性分析。"
        
        prompt = f"""
        你是一位資深美股分析師。請針對 {symbol} ({sector}產業) 的最新新聞進行 2026 投資評級分析：
        {news_text}
        
        請根據新聞內容，判斷對該公司的利好/利空影響，並建議是否需要微調以下權重（總和需為 1.0）：
        {list(current_weights.keys())}
        
        請嚴格以 JSON 格式回覆：
        {{
            "sentiment": "利好" | "利空" | "中性",
            "summary": "簡短總結",
            "suggested_weights": {{ "Valuation": float, "Quality": float, "Growth": float, "MoatPolicy": float }},
            "reason": "理由"
        }}
        """
        # 傳遞 status 物件給 call_gemini_with_retry
        insight = call_gemini_with_retry(prompt, status)
        return insight
        
    except Exception as e:
        # 處理 yfinance 或其他非 API 呼叫的錯誤
        status.error(f"❌ 數據獲取或準備分析失敗：{e}")
        print(f"DEBUG ERROR: get_ai_market_insight failed for {symbol}. Error: {e}")
        return None

# =========================
# 批次 AI 分析函數
# =========================
def batch_analyze_sector(sector, progress_container):
    """批次分析整個產業的所有股票"""
    stocks = SECTORS[sector]
    total = len(stocks)
    results = {}
    
    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()
    
    for idx, stock in enumerate(stocks):
        status_text.write(f"🔍 正在分析 {stock} ({idx + 1}/{total})...")
        
        # 先檢查是否能獲取股票數據
        stock_info = get_stock_data(stock)
        if not stock_info:
            status_text.warning(f"⚠️ {stock} 數據獲取失敗，跳過分析")
            results[stock] = {"error": "無法獲取股票數據"}
            progress_bar.progress((idx + 1) / total)
            continue
        
        with st.status(f"分析 {stock}", expanded=False) as status:
            insight = get_ai_market_insight(
                stock,
                sector,
                st.session_state.weights[stock],
                status
            )
            
            if insight:
                results[stock] = {
                    "insight": insight,
                    "weights": insight["suggested_weights"],
                    "timestamp": datetime.now().isoformat()
                }
                # 更新權重和標記
                st.session_state.weights[stock] = insight["suggested_weights"]
                st.session_state.stock_insights[stock] = insight
                st.session_state.ai_adjusted[stock] = True
                
                # 持久化儲存
                save_to_storage("weights", st.session_state.weights)
                save_to_storage("stock_insights", st.session_state.stock_insights)
                save_to_storage("ai_adjusted", st.session_state.ai_adjusted)
                
                status.update(label=f"✅ {stock} 分析完成", state="complete")
            else:
                results[stock] = {"error": "分析失敗"}
                status.update(label=f"❌ {stock} 分析失敗", state="error")
            
            # 為避免 API 限流，每次分析後稍作延遲
            time.sleep(1)
        
        progress_bar.progress((idx + 1) / total)
    
    status_text.write(f"✅ {sector} 產業批次分析完成！")
    return results

# =========================
# 初始化持久化數據
# =========================

# 初始化按個股儲存的權重（優先從持久化儲存讀取）
if "weights" not in st.session_state:
    loaded_weights = load_from_storage("weights")
    if loaded_weights:
        st.session_state.weights = loaded_weights
    else:
        st.session_state.weights = {}
        for sector, stocks in SECTORS.items():
            for stock in stocks:
                st.session_state.weights[stock] = SECTOR_CONFIG[sector]["weights"].copy()

# 初始化按個股儲存的 AI 洞察
if "stock_insights" not in st.session_state:
    loaded_insights = load_from_storage("stock_insights")
    if loaded_insights:
        st.session_state.stock_insights = loaded_insights
    else:
        st.session_state.stock_insights = {}

# 初始化 AI 調整標記
if "ai_adjusted" not in st.session_state:
    loaded_adjusted = load_from_storage("ai_adjusted")
    if loaded_adjusted:
        st.session_state.ai_adjusted = loaded_adjusted
    else:
        st.session_state.ai_adjusted = {}
        for sector, stocks in SECTORS.items():
            for stock in stocks:
                st.session_state.ai_adjusted[stock] = False

# 初始化手動評分（持久化儲存）
if "manual_scores" not in st.session_state:
    loaded_manual = load_from_storage("manual_scores")
    if loaded_manual:
        st.session_state.manual_scores = loaded_manual
    else:
        st.session_state.manual_scores = {}

# =========================
# UI 佈局
# =========================
st.sidebar.header("⚙️ 2026 評比設定")

# 新增批次分析按鈕
st.sidebar.subheader("🚀 批次 AI 分析")
batch_sector = st.sidebar.selectbox("選擇要批次分析的產業", list(SECTORS.keys()), key="batch_sector")

if st.sidebar.button("🔥 一鍵分析整個產業", type="primary"):
    progress_container = st.sidebar.container()
    with st.spinner(f"正在批次分析 {batch_sector} 產業..."):
        results = batch_analyze_sector(batch_sector, progress_container)
    
    # 統計成功和失敗的數量
    success_count = sum(1 for r in results.values() if "error" not in r)
    fail_count = len(results) - success_count
    
    st.sidebar.success(f"✅ {batch_sector} 產業分析完成！成功: {success_count}, 失敗: {fail_count}")

st.sidebar.divider()

selected_sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox("選擇股票", SECTORS[selected_sector])

# 確保當前選定股票的評分已初始化（預設 50）
current_stock = selected_stock
if current_stock not in st.session_state.manual_scores:
    st.session_state.manual_scores[current_stock] = {"Policy": 50, "Moat": 50}

# 定義回調函數（包含持久化）
def update_policy_score():
    st.session_state.manual_scores[current_stock]["Policy"] = st.session_state[f"{current_stock}_p"]
    save_to_storage("manual_scores", st.session_state.manual_scores)

def update_moat_score():
    st.session_state.manual_scores[current_stock]["Moat"] = st.session_state[f"{current_stock}_m"]
    save_to_storage("manual_scores", st.session_state.manual_scores)
    
# 從 session state 中讀取當前股票的持久化值
policy_default = st.session_state.manual_scores[current_stock]["Policy"]
moat_default = st.session_state.manual_scores[current_stock]["Moat"]

# 手動評分
st.sidebar.subheader("✏️ 手動評分 (20%)")
m_policy = st.sidebar.slider(
    "政策受益度", 
    0, 
    100, 
    value=policy_default, 
    key=f"{current_stock}_p", 
    on_change=update_policy_score
)
m_moat = st.sidebar.slider(
    "護城河粘性", 
    0, 
    100, 
    value=moat_default, 
    key=f"{current_stock}_m", 
    on_change=update_moat_score
)

# 單股 AI 分析按鈕
if st.sidebar.button("🤖 分析當前股票"):
    with st.status("🤖 正在執行 AI 投資分析...", expanded=True) as status:
        insight = get_ai_market_insight(
            selected_stock, 
            selected_sector, 
            st.session_state.weights[selected_stock],
            status
        )
        
        if insight:
            st.session_state.stock_insights[selected_stock] = insight
            st.session_state.weights[selected_stock] = insight["suggested_weights"]
            st.session_state.ai_adjusted[selected_stock] = True
            
            # 持久化儲存
            save_to_storage("weights", st.session_state.weights)
            save_to_storage("stock_insights", st.session_state.stock_insights)
            save_to_storage("ai_adjusted", st.session_state.ai_adjusted)
            
            status.update(label="✅ 分析完成！評級與權重已更新。", state="complete", expanded=False)
        else:
            status.update(label="❌ 分析失敗：請檢查上面的錯誤訊息。", state="error")

# 新增：清除數據按鈕
st.sidebar.divider()
if st.sidebar.button("🗑️ 清除所有 AI 分析記錄", type="secondary"):
    # 重置 AI 相關數據
    for sector, stocks in SECTORS.items():
        for stock in stocks:
            st.session_state.weights[stock] = SECTOR_CONFIG[sector]["weights"].copy()
            st.session_state.ai_adjusted[stock] = False
    st.session_state.stock_insights = {}
    
    # 持久化儲存
    save_to_storage("weights", st.session_state.weights)
    save_to_storage("stock_insights", st.session_state.stock_insights)
    save_to_storage("ai_adjusted", st.session_state.ai_adjusted)
    
    st.sidebar.success("✅ 已清除所有 AI 分析記錄（手動評分保留）")
    st.rerun()

# 顯示當前股票的 AI 洞察
if selected_stock in st.session_state.stock_insights:
    ins = st.session_state.stock_insights[selected_stock]
    st.info(f"### 🤖 AI 2026 投資洞察 - {selected_stock} ({ins['sentiment']})\n**總結**: {ins['summary']}\n\n**權重調整理由**: {ins['reason']}")

# 獲取數據並計算
with st.spinner(f"正在載入 {selected_stock} 數據..."):
    info = get_stock_data(selected_stock)

if info:
    sector_avg_data = {"avg_fwd_pe": 25} 
    
    scores = calculate_2026_score(
        info, 
        selected_sector, 
        {"Policy": m_policy, "Moat": m_moat}, 
        sector_avg_data,
        st.session_state.weights[selected_stock]
    )
    
    if scores:  # 確保評分計算成功
        col1, col2, col3 = st.columns(3)
        col1.metric("🎯 綜合評分", scores["Total"])
        col2.metric("投資評級", get_tier(scores["Total"]))
        col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))
        
        st.subheader(f"📊 {selected_sector} 評分維度 (焦點：{SECTOR_CONFIG[selected_sector]['focus']})")
        
        detail_data = pd.DataFrame({
            "維度": ["前瞻估值 (Valuation)", "獲利質量 (Quality)", "成長動能 (Growth)", "政策與護城河 (MoatPolicy)"],
            "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
            "權重": [st.session_state.weights[selected_stock][k] for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
        })
        st.dataframe(detail_data) 
        
        if scores["Adjustment"] != 0:
            st.warning(f"⚠️ 觸發懲罰/加成機制：總分已調整 {scores['Adjustment']} 分")

        # 產業橫向比較
        with st.expander(f"🏭 查看 {selected_sector} 產業橫向排序"):
            results = []
            failed_stocks = []
            
            for s in SECTORS[selected_sector]:
                s_info = get_stock_data(s)
                if s_info:
                    # 獲取該股票的手動評分（如果沒有則使用預設值 50）
                    s_manual = st.session_state.manual_scores.get(s, {"Policy": 50, "Moat": 50})
                    
                    s_scores = calculate_2026_score(
                        s_info, 
                        selected_sector, 
                        s_manual,
                        sector_avg_data,
                        st.session_state.weights[s]
                    )
                    
                    if s_scores:  # 確保評分計算成功
                        is_ai_adjusted = st.session_state.ai_adjusted.get(s, False)
                        
                        results.append({
                            "股票": s,
                            "綜合分數": s_scores["Total"],
                            "評級": get_tier(s_scores["Total"]),
                            "Fwd PE": s_info.get("forwardPE", "N/A"),
                            "FCF": s_info.get("freeCashflow", "N/A"),
                            "AI 調整": "✅" if is_ai_adjusted else "❌",
                            "政策評分": s_manual["Policy"],
                            "護城河評分": s_manual["Moat"]
                        })
                else:
                    failed_stocks.append(s)
            
            if results:
                st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False))
            
            if failed_stocks:
                st.warning(f"⚠️ 以下股票數據獲取失敗：{', '.join(failed_stocks)}")
    else:
        st.error(f"❌ 無法計算 {selected_stock} 的評分，數據可能不完整")
else:
    st.error(f"❌ 無法獲取 {selected_stock} 的股票數據。請檢查：\n1. 股票代碼是否正確\n2. 網路連線是否正常\n3. 稍後再試")
    st.info("💡 提示：某些股票（特別是小型股或新上市公司）可能在 Yahoo Finance 上的數據不完整")
