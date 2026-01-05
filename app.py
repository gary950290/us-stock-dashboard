import streamlit as st
import yfinance as yf
import time
import random
import pandas as pd

# =========================
# 工具函數：具備重試與延遲機制的抓取
# =========================

@st.cache_data(ttl=300)  # 優化 4：5分鐘快取，減少重複請求
def get_stock_data_safe(symbol):
    """
    核心抓取函數：整合重試、延遲與錯誤處理
    """
    max_retries = 3  # 優化 1：設定 3 次重試
    base_delay = 2   # 基礎延遲秒數
    
    for attempt in range(max_retries):
        try:
            # 優化 2：加入隨機微小延遲 (0.5-0.8秒)，模擬真人行為避免觸發限流
            time.sleep(random.uniform(0.5, 0.8))
            
            ticker = yf.Ticker(symbol)
            # 觸發 info 獲取
            info = ticker.info
            
            if info and "symbol" in info:
                return info
            
            # 若獲取到空數據，視為觸發限流，進入重試
            st.warning(f"⚠️ {symbol} 獲取數據為空，嘗試第 {attempt + 1} 次重試...")
            
        except Exception as e:
            # 優化 5：完善錯誤處理，辨識特定錯誤
            error_msg = str(e)
            if "Rate limited" in error_msg or "429" in error_msg:
                wait_time = base_delay * (attempt + 1) # 遞增延遲時間
                st.warning(f"🛑 {symbol} 被限流，等待 {wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                st.error(f"❌ {symbol} 發生未知錯誤: {error_msg[:100]}")
                break # 非限流錯誤則停止重試
                
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
    
    # 優化 3：添加進度條顯示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(sector_stocks)
    
    for idx, symbol in enumerate(sector_stocks):
        # 更新進度文字
        status_text.text(f"🔍 正在獲取 {symbol} 數據 ({idx+1}/{total})...")
        
        # 調用安全抓取函數
        info = get_stock_data_safe(symbol)
        
        if info:
            all_data.append(info)
        else:
            failed_stocks.append(symbol)
            
        # 更新進度條
        progress_bar.progress((idx + 1) / total)
    
    # 清除進度顯示
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
            # 提取投資細節與數字
            summary_list.append({
                "公司名稱": info.get("shortName", "N/A"),
                "代號": info.get("symbol"),
                "前瞻 PE": round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else "N/A",
                "ROE %": f"{info.get('returnOnEquity', 0)*100:.2f}%",
                "營收增長 %": f"{info.get('revenueGrowth', 0)*100:.2f}%",
                "市值 (B)": f"${info.get('marketCap', 0)/1e9:.2f}B"
            })
            
        df = pd.DataFrame(summary_list).sort_values("前瞻 PE", ascending=True)
        st.table(df) # 依據您的要求，以表格整理答案
    else:
        st.error("無法載入產業數據，請檢查網絡或稍後再試。")
