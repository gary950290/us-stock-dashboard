import streamlit as st
import yfinance as yf
import time
import random
import pandas as pd

# =========================
# 工具函數：具備重試與延遲機制的抓取
# =========================

@st.cache_data(ttl=300)
def get_stock_data_safe(symbol):
    """
    核心抓取函數：整合重試、延遲與錯誤處理
    """
    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(0.5, 0.8))
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 檢查是否獲取到有效數據
            if info and len(info) > 1:
                return info
            
            st.warning(f"⚠️ {symbol} 獲取數據為空，嘗試第 {attempt + 1} 次重試...")
            
        except Exception as e:
            error_msg = str(e)
            if "Rate limited" in error_msg or "429" in error_msg:
                wait_time = base_delay * (attempt + 1)
                st.warning(f"🛑 {symbol} 被限流，等待 {wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                st.error(f"❌ {symbol} 發生錯誤: {error_msg[:100]}")
                break
                
    return None

# =========================
# 批量處理邏輯：含進度條與同行比較
# =========================

def batch_process_sector(sector_stocks):
    """
    批量獲取產業數據，加入進度條顯示
    """
    all_data = []
    failed_stocks = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(sector_stocks)

    for idx, symbol in enumerate(sector_stocks):
        status_text.text(f"🔍 正在獲取 {symbol} 數據 ({idx+1}/{total})...")
        
        info = get_stock_data_safe(symbol)
        
        if info:
            all_data.append(info)
        else:
            failed_stocks.append(symbol)
            
        progress_bar.progress((idx + 1) / total)

    status_text.empty()
    progress_bar.empty()

    if failed_stocks:
        st.sidebar.warning(f"⚠️ 以下股票抓取失敗: {', '.join(failed_stocks)}")
        
    return all_data

# =========================
# UI 呈現範例：同行業比較表格
# =========================

def display_sector_comparison(selected_sector, sector_stocks):
    st.subheader(f"📊 {selected_sector} 產業橫向評估表")

    raw_data = batch_process_sector(sector_stocks)

    if raw_data:
        summary_list = []
        for info in raw_data:
            summary_list.append({
                "公司名稱": info.get("shortName", info.get("longName", "N/A")),
                "代號": info.get("symbol", "N/A"),
                "前瞻 PE": round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A",
                "ROE %": f"{info.get('returnOnEquity', 0)*100:.2f}%" if info.get('returnOnEquity') else "N/A",
                "營進增長 %": f"{info.get('revenueGrowth', 0)*100:.2f}%" if info.get('revenueGrowth') else "N/A",
                "市值 (B)": f"${info.get('marketCap', 0)/1e9:.2f}B" if info.get('marketCap') else "N/A"
            })
            
        df = pd.DataFrame(summary_list)
        
        try:
            df_sorted = df[df["前瞻 PE"] != "N/A"].sort_values("前瞻 PE", ascending=True)
            df_na = df[df["前瞻 PE"] == "N/A"]
            df = pd.concat([df_sorted, df_na])
        except:
            pass
            
        st.dataframe(df, use_container_width=True)
    else:
        st.error("無法載入產業數據，請檢查網絡或稍後再試。")

# =========================
# 主程式入口
# =========================

def main():
    st.set_page_config(page_title="股票產業分析", page_icon="📈", layout="wide")
    st.title("📈 股票產業分析工具")

    sectors = {
        "科技股": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
        "金融股": ["JPM", "BAC", "WFC", "GS", "C"],
        "能源股": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "醫療股": ["JNJ", "UNH", "PFE", "ABBV", "TMO"]
    }

    st.sidebar.header("⚙️ 設定")
    selected_sector = st.sidebar.selectbox(
        "選擇產業",
        list(sectors.keys()),
        index=0
    )

    st.sidebar.info(f"將分析 {len(sectors[selected_sector])} 支股票")

    if st.sidebar.button("🚀 開始分析", type="primary"):
        with st.spinner("正在載入數據..."):
            display_sector_comparison(selected_sector, sectors[selected_sector])

    with st.expander("📖 使用說明"):
        st.markdown("""
        ### 功能特點
        - ✅ 自動重試機制（最多 3 次）
        - ✅ 智能延遲避免限流
        - ✅ 5 分鐘數據快取
        - ✅ 即時進度顯示
        """)

if __name__ == "__main__":
    main()
