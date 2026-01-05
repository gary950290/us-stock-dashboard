import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import json
import os
import time
import random

# =========================
# 1. 基礎配置與 AI 初始化
# =========================
SETTING_FILE = "stock_settings.json"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"  # 請替換為您的 API Key

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# =========================
# 2. 自動存檔與讀取邏輯
# =========================
def load_settings():
    """載入上次儲存的輸入內容"""
    if os.path.exists(SETTING_FILE):
        with open(SETTING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sector": "全球半導體", "symbols": "NVDA, TSM, ASML, AMD, INTC"}

def save_settings(sector, symbols):
    """儲存當前輸入內容"""
    with open(SETTING_FILE, "w", encoding="utf-8") as f:
        json.dump({"sector": sector, "symbols": symbols}, f, ensure_ascii=False)

# =========================
# 3. 數據抓取模組 (帶緩存機制)
# =========================
@st.cache_data(ttl=600)  # 10分鐘內重複抓取會直接調用緩存，加速運行
def get_stock_data_comprehensive(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info or 'marketCap' not in info:
            return None
        return info
    except:
        return None

# =========================
# 4. Gemini 深度分析 (包含政策與估值)
# =========================
def ask_gemini_analysis(df_data, sector_name):
    data_str = df_data.to_string()
    # 這裡依照您的需求，明確要求搜尋 2026 最新政策與估值對比
    prompt = f"""
    你是一位專業的證券分析師。現在時間是 2026 年 1 月。
    請針對以下「{sector_name}」產業的數據進行深度分析：
    
    1. **政策與環境**：搜尋 2025-2026 年相關產業的政府新政策（如：補貼、法規、地緣政治）。
    2. **同行業橫向比較**：根據表格中的 PE, ROE, 營收增長進行排名與對比，指出誰是領頭羊，誰被低估。
    3. **公司估值評估**：詳細分析各公司當前數值的合理性，並提供投資建議。
    4. **風險提示**：列出該產業 2026 年需注意的宏觀風險。

    數據內容：
    {data_str}

    請以「繁體中文」回答，並使用 Markdown 格式呈現清晰的表格與標題。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 分析發生錯誤: {str(e)}"

# =========================
# 5. 主程式頁面
# =========================
def main():
    st.set_page_config(page_title="AI 股票產業分析器", page_icon="📈", layout="wide")
    
    # 初始化設定
    saved_data = load_settings()

    st.title("📈 專業產業分析與 AI 投資決策工具")
    st.markdown("---")

    # --- 側邊欄：輸入與存檔 ---
    st.sidebar.header("⚙️ 設定與儲存")
    sector_input = st.sidebar.text_input("產業名稱", value=saved_data["sector"])
    symbols_input = st.sidebar.text_area("股票代碼 (逗號分隔)", value=saved_data["symbols"])

    # 只要有變動就自動觸發存檔
    if sector_input != saved_data["sector"] or symbols_input != saved_data["symbols"]:
        save_settings(sector_input, symbols_input)
        st.sidebar.success("✅ 設定已自動儲存")

    st.sidebar.info("輸入示例: AAPL, MSFT, GOOGL 或 2330.TW, 2454.TW")

    # --- 主要執行邏輯 ---
    stock_list = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

    if st.sidebar.button("🚀 開始深度評估", type="primary"):
        if not stock_list:
            st.warning("請先輸入股票代碼")
            return

        with st.status("正在抓取全球市場數據...", expanded=True) as status:
            all_data = []
            for sym in stock_list:
                st.write(f"正在獲取 {sym} 的財務指標...")
                data = get_stock_data_comprehensive(sym)
                if data:
                    all_data.append({
                        "公司名稱": data.get("shortName", sym),
                        "代號": sym,
                        "市值(B)": round(data.get("marketCap", 0) / 1e9, 2),
                        "前瞻PE": data.get("forwardPE", "N/A"),
                        "ROE %": f"{data.get('returnOnEquity', 0)*100:.2f}%" if data.get('returnOnEquity') else "N/A",
                        "營收增長%": f"{data.get('revenueGrowth', 0)*100:.2f}%" if data.get('revenueGrowth') else "N/A",
                        "負債比率": data.get("debtToEquity", "N/A"),
                        "股價/淨值比": data.get("priceToBook", "N/A")
                    })
            status.update(label="數據抓取完成！開始 AI 評估...", state="complete", expanded=False)

        if all_data:
            df = pd.DataFrame(all_data)
            
            # 展示數據表格
            st.subheader(f"📊 {sector_input} 產業橫向數據比較 (同行業比較)")
            st.table(df) # 使用 table 或 dataframe 均可，table 展示更直觀

            # 展示分析報告
            st.divider()
            st.subheader("🤖 Gemini AI 深度分析與政策評估")
            with st.spinner("AI 正在分析政府政策與估值細節..."):
                report = ask_gemini_analysis(df, sector_input)
                st.markdown(report)
                
            # 下載功能
            st.download_button("📥 下載此分析報告 (.md)", report, file_name=f"{sector_input}_分析報告.md")
        else:
            st.error("找不到相關股票數據，請確認代碼格式（美股如 AAPL，台股如 2330.TW）")

    with st.expander("💡 專業提示"):
        st.write("""
        1. **自動儲存**：您在左側輸入的內容會自動儲存在本地 `stock_settings.json`。
        2. **同行比較**：AI 會自動根據您輸入的清單進行橫向排名。
        3. **政策敏感**：Gemini 會根據您輸入的產業名稱搜尋最新的政府動態。
        """)

if __name__ == "__main__":
    main()
