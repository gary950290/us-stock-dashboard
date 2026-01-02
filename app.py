import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import google.generativeai as genai

# =========================
# 0. 設定與 API 配置
# =========================
st.set_page_config(page_title="2026 美股 AI 戰情室", layout="wide")

# 從 Streamlit Secrets 安全讀取 API Key
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        HAS_AI = True
    else:
        st.warning("⚠️ 未在 Secrets 中偵測到 GEMINI_API_KEY，AI 功能將無法使用。")
        HAS_AI = False
except Exception as e:
    st.error(f"API 配置錯誤: {e}")
    HAS_AI = False

# =========================
# 1. 產業股票池與 2026 評分權重
# =========================
SECTORS = {
    "能源/基建": ["CEG", "VST", "GEV", "NEE", "OKLO", "SMR", "TERA"],
    "半導體/AI": ["NVDA", "TSM", "AMD", "AVGO", "ARM", "ASML"],
    "巨頭 (Mag7)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
    "資安/軟體": ["CRWD", "PANW", "PLTR", "SNOW", "ZS"]
}

# 2026 投資風格權重配置
STYLE_WEIGHTS = {
    "能源/基建": {
        "平衡型": {"Policy": 0.4, "Capex_Intensity": 0.3, "FCF": 0.3},
        "成長型": {"Policy": 0.3, "Capex_Intensity": 0.5, "FCF": 0.2}
    },
    "半導體/AI": {
        "平衡型": {"ROE": 0.4, "PE_Relative": 0.3, "Growth": 0.3},
        "成長型": {"ROE": 0.3, "PE_Relative": 0.2, "Growth": 0.5}
    }
}

# =========================
# 2. 數據抓取引擎
# =========================
@st.cache_data(ttl=600)
def fetch_stock_data(symbol):
    """抓取股價與 2026 關鍵財務指標"""
    try:
        tk = yf.Ticker(symbol)
        info = tk.info
        cf = tk.cashflow
        
        # 計算資本支出 (Capex)
        capex = 0
        if not cf.empty:
            for label in ['Capital Expenditure', 'Capital Expenditures']:
                if label in cf.index:
                    capex = abs(cf.loc[label].iloc[0])
                    break
        
        return {
            "Ticker": symbol,
            "Price": info.get("currentPrice"),
            "Change": info.get("regularMarketChangePercent"),
            "PE": info.get("trailingPE"),
            "ROE": info.get("returnOnEquity"),
            "MarketCap": info.get("marketCap"),
            "RevenueGrowth": info.get("revenueGrowth"),
            "FCF": info.get("freeCashflow"),
            "Capex": capex,
            "DebtToEquity": info.get("debtToEquity")
        }
    except:
        return None

def format_num(n):
    if n is None: return "N/A"
    if n >= 1e12: return f"{n/1e12:.2f}T"
    if n >= 1e9: return f"{n/1e9:.2f}B"
    if n >= 1e6: return f"{n/1e6:.2f}M"
    return f"{n:.2f}"

# =========================
# 3. 核心評分邏輯 (2026 特化)
# =========================
def calculate_2026_score(data, sector, style):
    score = 50.0  # 基礎分
    
    if sector == "能源/基建":
        # 能源股看重資本支出強度 (未來電力供應能力)
        if data["MarketCap"] and data["Capex"]:
            intensity = (data["Capex"] / data["MarketCap"]) * 100
            score += min(intensity * 5, 30) # 最高加 30 分
        if data["FCF"] and data["FCF"] > 0: score += 10
            
    elif sector == "半導體/AI":
        # 半導體看重 ROE 與 營收成長
        if data["ROE"]: score += min(data["ROE"] * 100, 25)
        if data["RevenueGrowth"]: score += min(data["RevenueGrowth"] * 100, 20)
        
    return round(min(score, 100), 1)

# =========================
# 4. 介面呈現
# =========================
st.title("🚀 2026 美股 AI 智能戰情室")
st.markdown("---")

# 側邊欄配置
st.sidebar.header("📊 投資配置")
selected_sector = st.sidebar.selectbox("選擇觀測產業", list(SECTORS.keys()))
invest_style = st.sidebar.radio("投資偏好", ["平衡型", "成長型"])

# 主畫面：產業掃描
if st.button(f"🔍 執行 {selected_sector} 深度掃描"):
    with st.spinner("正在調取 2026 最新財報數據與政策指標..."):
        results = []
        progress_bar = st.progress(0)
        stocks = SECTORS[selected_sector]
        
        for idx, sym in enumerate(stocks):
            data = fetch_stock_data(sym)
            if data:
                data["綜合評分"] = calculate_2026_score(data, selected_sector, invest_style)
                results.append(data)
            progress_bar.progress((idx + 1) / len(stocks))
            
        if results:
            df = pd.DataFrame(results)
            df = df.sort_values("綜合評分", ascending=False)
            
            # 建立可視化圖表
            st.subheader(f"🏆 {selected_sector} 戰力排行")
            
            # 顯示主要數據表格
            display_df = df.copy()
            display_df["市值"] = display_df["MarketCap"].apply(format_num)
            display_df["自由現金流"] = display_df["FCF"].apply(format_num)
            
            cols = ["Ticker", "綜合評分", "Price", "Change", "市值", "PE", "ROE", "自由現金流"]
            st.dataframe(display_df[cols], use_container_width=True)

            # AI 深度分析
            if HAS_AI:
                st.markdown("---")
                st.subheader("🤖 AI 產業宏觀研判 (Gemini 2.0 Flash)")
                
                # 整理數據給 AI
                ai_data_summary = df[["Ticker", "綜合評分", "PE", "RevenueGrowth"]].to_string()
                
                prompt = f"""
                你是一位 2026 年的頂級量化交易員。
                請根據以下 {selected_sector} 產業數據進行分析：
                {ai_data_summary}
                
                請提供：
                1. 根據目前 2026 年政府政策（如能源補貼或 AI 關稅），誰最具優勢？
                2. 針對綜合評分最高的股票，給予買入建議或風險警告。
                3. 同行業比較中，誰的估值明顯被低估？
                請以繁體中文回答，並使用表格整理。
                """
                
                with st.chat_message("assistant"):
                    model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    response = model.generate_content(prompt)
                    st.markdown(response.text)

# 底部資訊
st.markdown("---")
st.caption(f"最後更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 數據來源: Yahoo Finance & Google Gemini AI")
