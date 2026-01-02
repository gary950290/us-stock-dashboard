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

# ⚠️⚠️⚠️ 請在此處填入你的 Gemini API Key ⚠️⚠️⚠️
GEMINI_API_KEY = "在此填入你的API_KEY"  
# 若未填入 Key，AI 功能將無法使用，但其他功能正常

if GEMINI_API_KEY != "在此填入你的API_KEY":
    genai.configure(api_key=GEMINI_API_KEY)

# =========================
# 1. 產業股票池與權重配置 (2026 修正版)
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["CEG","VST","GEV","NEE","ENPH","FLNC","PLUG","OKLO","SMR","TE"],
    "NeoCloud": ["NBIS","IREN","APLD","CORZ"]
}

# 護城河資料
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.92,"network":0.75},
    "CEG":{"retention":0.75,"switching":0.7,"patent":0.65,"network":0.6},
    "VST":{"retention":0.77,"switching":0.72,"patent":0.68,"network":0.62},
}
MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# 2026 產業權重邏輯
SECTOR_WEIGHTS = {
    "Mag7": {
        "穩健型": {"PE": 0.15, "Forward_PE": 0.2, "ROE": 0.25, "Moat": 0.2, "Growth": 0.2},
        "成長型": {"PE": 0.1, "Forward_PE": 0.25, "ROE": 0.2, "Moat": 0.15, "Growth": 0.3},
        "平衡型": {"PE": 0.15, "Forward_PE": 0.2, "ROE": 0.25, "Moat": 0.2, "Growth": 0.2}
    },
    "資安": {
        "穩健型": {"Margin": 0.3, "Growth": 0.2, "Policy": 0.3, "Moat": 0.2},
        "成長型": {"Margin": 0.25, "Growth": 0.4, "Policy": 0.2, "Moat": 0.15},
        "平衡型": {"Margin": 0.3, "Growth": 0.3, "Policy": 0.2, "Moat": 0.2}
    },
    "半導體": {
        "穩健型": {"PE": 0.2, "Debt": 0.3, "ROE": 0.2, "Policy": 0.2, "Moat": 0.1},
        "成長型": {"PE": 0.1, "Debt": 0.2, "ROE": 0.3, "Policy": 0.25, "Moat": 0.15},
        "平衡型": {"PE": 0.15, "Debt": 0.3, "ROE": 0.25, "Policy": 0.2, "Moat": 0.1}
    },
    "能源": {
        "穩健型": {"Policy": 0.4, "Capex_Intensity": 0.2, "Growth": 0.1, "FCF": 0.3},
        "成長型": {"Policy": 0.3, "Capex_Intensity": 0.4, "Growth": 0.2, "FCF": 0.1},
        "平衡型": {"Policy": 0.35, "Capex_Intensity": 0.25, "Growth": 0.20, "FCF": 0.20}
    },
    "NeoCloud": {
        "穩健型": {"Growth": 0.3, "Cash": 0.4, "Policy": 0.2, "Moat": 0.1},
        "成長型": {"Growth": 0.5, "Cash": 0.2, "Policy": 0.2, "Moat": 0.1},
        "平衡型": {"Growth": 0.4, "Cash": 0.3, "Policy": 0.2, "Moat": 0.1}
    }
}

# =========================
# 2. 核心功能函數
# =========================
@st.cache_data(ttl=300)
def get_price_safe(symbol, retry=3, delay=1):
    for attempt in range(retry):
        try:
            info = yf.Ticker(symbol).info
            return info.get("currentPrice"), info.get("regularMarketChangePercent")
        except:
            time.sleep(delay)
    return None, None

@st.cache_data(ttl=300)
def get_fundamentals_safe(symbol, retry=3, delay=1):
    """安全獲取數據，包含 2026 關鍵指標 (Capex)"""
    for attempt in range(retry):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 抓取資本支出 (Capex)
            cashflow = ticker.cashflow
            capex = 0
            if not cashflow.empty:
                if 'Capital Expenditure' in cashflow.index:
                    capex = abs(cashflow.loc['Capital Expenditure'].iloc[0])
                elif 'Capital Expenditures' in cashflow.index:
                    capex = abs(cashflow.loc['Capital Expenditures'].iloc[0])

            data = {
                "股價": info.get("currentPrice"),
                "PE": info.get("trailingPE"),
                "Forward PE": info.get("forwardPE"),
                "ROE": info.get("returnOnEquity"),
                "負債比": info.get("debtToEquity"),
                "毛利率": info.get("grossMargins"),
                "市值": info.get("marketCap"),
                "FCF": info.get("freeCashflow"),
                "營收成長": info.get("revenueGrowth"),
                "Capex": capex,
                "現金儲備": info.get("totalCash")
            }
            return pd.DataFrame(data.items(), columns=["指標", "數值"])
        except:
            time.sleep(delay)
    return pd.DataFrame()

def format_large_numbers(value):
    if isinstance(value, (int, float)) and value is not None:
        if value >= 1e9: return f"{value/1e9:.2f} B"
        elif value >= 1e6: return f"{value/1e6:.2f} M"
        else: return f"{value:.2f}"
    return value

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score = sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score, 2)

def get_score_color(score):
    if score >= 80: return "🟢"
    elif score >= 60: return "🟡"
    elif score >= 40: return "🟠"
    else: return "🔴"

def compute_sector_specific_scores(row, sector, manual_scores=None, sector_avg_pe=None, sector_avg_roe=None, style="平衡型"):
    """
    2026 核心評分引擎
    """
    symbol = row["股票"]
    
    # 使用 .get 安全提取數據
    pe = row.get("PE")
    f_pe = row.get("Forward PE")
    roe = row.get("ROE")
    growth = row.get("營收成長")
    margin = row.get("毛利率")
    debt = row.get("負債比")
    capex = row.get("Capex")
    mkt_cap = row.get("市值")
    fcf = row.get("FCF")
    cash = row.get("現金儲備")

    # 初始化分數
    scores = {k: 50 for k in ["PE", "Forward_PE", "ROE", "Debt", "Margin", "Growth", "Capex_Intensity", "FCF", "Cash", "Policy", "Moat"]}

    # --- 產業特化邏輯 ---
    if sector == "能源":
        if growth: scores["Growth"] = max(0, min(100, growth * 200 + 30))
        if capex and mkt_cap and mkt_cap > 0: 
            scores["Capex_Intensity"] = max(0, min(100, (capex / mkt_cap) * 500))
        if fcf is not None: scores["FCF"] = 80 if fcf > 0 else 30

    elif sector == "半導體":
        if debt is not None: scores["Debt"] = max(0, min(100, 100 - (debt / 2)))
        if roe and sector_avg_roe: scores["ROE"] = max(0, min(100, (roe / sector_avg_roe) * 50))
        if pe and sector_avg_pe: scores["PE"] = max(0, min(100, (sector_avg_pe / pe) * 50))

    elif sector == "資安":
        if margin: scores["Margin"] = max(0, min(100, margin * 100))
        if growth: scores["Growth"] = max(0, min(100, growth * 100 + 20))

    elif sector == "Mag7":
        if f_pe and pe and pe > 0: scores["Forward_PE"] = 80 if f_pe < pe else 40
        if roe: scores["ROE"] = max(0, min(100, roe * 200))
        if pe and sector_avg_pe: scores["PE"] = max(0, min(100, (sector_avg_pe / pe) * 50))

    elif sector == "NeoCloud":
        if growth: scores["Growth"] = max(0, min(100, growth * 100))
        if cash and mkt_cap and mkt_cap > 0: scores["Cash"] = max(0, min(100, (cash / mkt_cap) * 500))

    # --- 手動分數覆蓋 ---
    if manual_scores and symbol in manual_scores:
        scores["Policy"] = manual_scores[symbol].get("Policy_score", 50)
        scores["Moat"] = manual_scores[symbol].get("Moat_score", calculate_moat(symbol))
        # 若需要也可覆蓋 Growth
        if "Growth_score" in manual_scores[symbol]:
             # 這裡簡單處理：若手動有值則參考，否則用自動計算
             pass 

    # --- 加權計算 ---
    w = SECTOR_WEIGHTS.get(sector, SECTOR_WEIGHTS["Mag7"]).get(style, SECTOR_WEIGHTS["Mag7"]["平衡型"])
    
    total_score = 0
    total_weight = 0
    for key, weight in w.items():
        if key in scores:
            total_score += scores[key] * weight
            total_weight += weight
            
    if total_weight > 0:
        total_score = total_score / total_weight

    # 回傳 Tuple 以配合主程式 (PE, ROE, Policy, Moat, Growth, Total)
    # 注意：即便能源股不看 PE，為了格式一致仍回傳 PE 分數
    return (round(scores["PE"], 2), 
            round(scores["ROE"], 2), 
            round(scores["Policy"], 2), 
            round(scores["Moat"], 2), 
            round(scores["Growth"], 2), 
            round(total_score, 2))

# =========================
# 3. AI 分析功能
# =========================
def get_ai_analysis(sector, df, news_input):
    if GEMINI_API_KEY == "AIzaSyCsnKsNglTQNf8Ohym7gm7zE2mdx_KXlGQ":
        return "⚠️ 請先在代碼上方設定您的 Gemini API Key"
        
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    data_str = df.to_string(index=False)
    
    prompt = f"""
    你是一位專精於 2026 年美股的資深分析師。
    【產業】：{sector}
    【財務數據】：\n{data_str}
    【今日新聞】：{news_input if news_input else "無特定新聞"}
    
    請執行：
    1. 根據新聞與 2026 趨勢 (如能源基建、AI 需求)，分析哪些指標最重要。
    2. 為每檔股票給出簡短評語 (1-2句話)，指出亮點或風險。
    3. 給出針對該產業的整體投資氣氛評分 (0-100)。
    請用繁體中文回答，並以條列式呈現。
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 連線錯誤: {str(e)}"

# =========================
# 4. 主程式介面
# =========================
st.title("📊 2026 美股戰情室 (AI + 數據驅動)")

# 側邊欄
st.sidebar.header("⚙️ 設定面板")
mode = st.sidebar.selectbox("模式選擇", ["產業全覽比較", "單一股票深度分析"])
style = st.sidebar.selectbox("投資風格", ["穩健型", "成長型", "平衡型"], index=2)

# 初始化 Session State
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state: st.session_state[f"{symbol}_policy"] = 50
        if f"{symbol}_moat" not in st.session_state: st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)

# --- 模式 A: 單一股票 ---
if mode == "單一股票深度分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "VST")
    
    # 判斷產業
    sector_found = "Mag7" # 預設
    for s, stocks in SECTORS.items():
        if symbol in stocks:
            sector_found = s
            break
            
    st.subheader(f"📌 {symbol} ({sector_found}) 深度分析")
    
    # 抓取數據
    price, change = get_price_safe(symbol)
    if price: st.metric("即時股價", f"${price:.2f}", f"{change:.2f}%")
    
    funds_df = get_fundamentals_safe(symbol)
    if not funds_df.empty:
        # 格式化顯示
        display_df = funds_df.copy()
        for col in ["FCF", "市值", "股價", "Capex", "現金儲備"]:
            mask = display_df["指標"] == col
            if mask.any():
                val = display_df.loc[mask, "數值"].values[0]
                display_df.loc[mask, "數值"] = format_large_numbers(val)
        st.table(display_df)
        
        # 準備評分 Row
        row_data = {"股票": symbol}
        for _, r in funds_df.iterrows(): row_data[r["指標"]] = r["數值"]
        
        # 手動調整區
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            p_score = st.number_input("政策分數 (Policy)", 0, 100, key=f"{symbol}_policy")
        with c2:
            m_score = st.number_input("護城河分數 (Moat)", 0, 100, key=f"{symbol}_moat")
            
        # 計算分數
        scores = compute_sector_specific_scores(
            row_data, sector_found, 
            manual_scores={symbol: {"Policy_score": p_score, "Moat_score": m_score}}, 
            style=style
        )
        
        st.markdown("### 🏆 評分結果")
        c1, c2, c3 = st.columns(3)
        c1.metric("綜合評分", f"{get_score_color(scores[5])} {scores[5]}")
        c2.metric("政策強度", f"{scores[2]}")
        c3.metric("成長動能", f"{scores[4]}")
        
        # AI 區塊
        st.markdown("---")
        st.subheader("🤖 AI 投資顧問")
        news = st.text_area("貼入今日新聞 (如：美國宣布核能補貼...)", height=100)
        if st.button("啟動 AI 分析"):
            with st.spinner("AI 正在分析財報與新聞..."):
                report = get_ai_analysis(sector_found, funds_df, news)
                st.markdown(report)

# --- 模式 B: 產業全覽 ---
elif mode == "產業全覽比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()), index=3) # 預設能源
    st.subheader(f"🏭 {sector} 產業戰力巡航")
    
    # 顯示該產業權重
    with st.expander("查看此產業評分權重"):
        st.write(SECTOR_WEIGHTS[sector][style])

    if st.button("🚀 開始掃描全產業"):
        progress = st.progress(0)
        rows = []
        
        # 1. 計算平均值用 (簡化版：先假設無)
        sector_avg_pe, sector_avg_roe = 25, 0.15 
        
        # 2. 逐一掃描
        for i, sym in enumerate(SECTORS[sector]):
            df = get_fundamentals_safe(sym)
            if not df.empty:
                row = {"股票": sym}
                for _, r in df.iterrows(): row[r["指標"]] = r["數值"]
                
                # 讀取 Session State 的手動分
                manual = {sym: {
                    "Policy_score": st.session_state[f"{sym}_policy"],
                    "Moat_score": st.session_state[f"{sym}_moat"]
                }}
                
                # 計算
                res = compute_sector_specific_scores(row, sector, manual, sector_avg_pe, sector_avg_roe, style)
                
                # 整理結果
                row["綜合分數"] = res[5]
                row["評級"] = get_score_color(res[5])
                row["政策分"] = res[2]
                row["成長分"] = res[4]
                row["基建/債務分"] = res[1] # 暫代欄位
                
                # 格式化
                for k in ["市值", "FCF", "Capex"]:
                    if k in row: row[k] = format_large_numbers(row[k])
                
                rows.append(row)
            progress.progress((i+1)/len(SECTORS[sector]))
            
        # 3. 顯示表格
        if rows:
            res_df = pd.DataFrame(rows)
            res_df = res_df.sort_values("綜合分數", ascending=False)
            
            # 精簡欄位
            main_cols = ["評級", "股票", "綜合分數", "政策分", "成長分", "市值", "PE", "Capex"]
            # 過濾存在的欄位
            show_cols = [c for c in main_cols if c in res_df.columns]
            
            st.dataframe(res_df[show_cols], use_container_width=True, height=500)
            
            # AI 總評
            st.markdown("---")
            st.subheader(f"🤖 {sector} 產業 AI 總評")
            news_sector = st.text_area("貼入產業新聞摘要：", key="sector_news")
            if st.button("分析全產業趨勢"):
                with st.spinner("AI 正在綜合研判..."):
                    report = get_ai_analysis(sector, res_df[show_cols], news_sector)
                    st.markdown(report)
