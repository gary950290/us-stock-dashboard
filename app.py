import streamlit as st
import pandas as pd
import yfinance as yf
from functools import lru_cache

# =========================
# 頁面設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（含 Forward & PEG 評分）")

# =========================
# 股票產業池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],  # TSLA 移除
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

# =========================
# 護城河資料
# =========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 投資風格權重
# =========================
WEIGHTS = {
    "穩健型":{"PE":0.3,"Forward_PE":0.2,"ROE":0.25,"Policy":0.1,"Moat":0.1,"Growth":0.05},
    "成長型":{"PE":0.1,"Forward_PE":0.3,"ROE":0.15,"Policy":0.1,"Moat":0.05,"Growth":0.3},
    "平衡型":{"PE":0.2,"Forward_PE":0.25,"ROE":0.2,"Policy":0.1,"Moat":0.1,"Growth":0.15}
}

# =========================
# 側邊欄
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式", ["單一股票分析", "產業共同比較"])
style = st.sidebar.selectbox("投資風格", ["穩健型","成長型","平衡型"], index=2)

# =========================
# 快取函數
# =========================
@st.cache_data(ttl=3600)
def get_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info
    except:
        return {}

# =========================
# 工具函數
# =========================
def format_large(value):
    if value is None:
        return "-"
    if isinstance(value,float):
        return round(value,2)
    if value>=1e9:
        return f"{value/1e9:.2f}B"
    elif value>=1e6:
        return f"{value/1e6:.2f}M"
    else:
        return round(value,2)

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol, {"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    return round(sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100,2)

def compute_scores(stock, sector_avg, manual_scores=None):
    PE, Forward_PE, ROE, FCF, NetDebt, EBITDA, PEG = \
        stock.get("PE"), stock.get("Forward_PE"), stock.get("ROE"), stock.get("FCF"), stock.get("NetDebt"), stock.get("EBITDA"), stock.get("PEG")
    
    # PE 動態調整
    PE_score = 50
    if PE and sector_avg.get("PE_avg"):
        PE_score = max(0, min(100, (sector_avg["PE_avg"]/PE)*100))
    
    # Forward PE 動態調整
    Forward_PE_score = 50
    if Forward_PE and sector_avg.get("Forward_PE_avg"):
        Forward_PE_score = max(0, min(100, (sector_avg["Forward_PE_avg"]/Forward_PE)*100))
    
    # ROE 綜合質量校正
    ROE_score = 50
    if ROE is not None:
        ROE_score = min(max(ROE/0.3*100,0),100)
        if FCF is not None and FCF<0:
            ROE_score *= 0.8
        if NetDebt and EBITDA and EBITDA>0 and NetDebt/EBITDA>3:
            ROE_score *= 0.8

    # 手動分數
    Policy_score = 50
    Moat_score = calculate_moat(stock.get("symbol"))
    Growth_score = 50
    if manual_scores and stock.get("symbol") in manual_scores:
        Policy_score = manual_scores[stock.get("symbol")].get("Policy_score", Policy_score)
        Moat_score = manual_scores[stock.get("symbol")].get("Moat_score", Moat_score)
        Growth_score = manual_scores[stock.get("symbol")].get("Growth_score", Growth_score)
    
    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w["PE"] + Forward_PE_score*w["Forward_PE"] + ROE_score*w["ROE"] +
        Policy_score*w["Policy"] + Moat_score*w["Moat"] + Growth_score*w["Growth"],2
    )
    
    return round(PE_score,2), round(Forward_PE_score,2), round(ROE_score,2), round(Policy_score,2), round(Moat_score,2), round(Growth_score,2), Total_score

# =========================
# 初始化 session_state
# =========================
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = 50
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = 50

# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入股票代碼", "AAPL").upper()
    info = get_info(symbol)
    if info:
        price = info.get("currentPrice")
        st.metric("股價", f"${format_large(price)}")
        stock = {
            "symbol": symbol,
            "PE": info.get("trailingPE"),
            "Forward_PE": info.get("forwardPE"),
            "ROE": info.get("returnOnEquity"),
            "FCF": info.get("freeCashflow"),
            "NetDebt": info.get("totalDebt"),
            "EBITDA": info.get("ebitda"),
            "EPS": info.get("trailingEps"),
            "Forward_EPS": info.get("forwardEps"),
            "PEG": info.get("pegRatio"),
        }
        # 手動分數
        manual_policy = st.number_input("政策分數", 0, 100, key=f"{symbol}_policy")
        manual_moat = st.number_input("護城河分數", 0, 100, key=f"{symbol}_moat")
        manual_growth = st.number_input("成長分數", 0, 100, key=f"{symbol}_growth")
        manual_scores = {symbol: {"Policy_score":manual_policy,"Moat_score":manual_moat,"Growth_score":manual_growth}}
        # 計算同業平均
        sector_avg = {"PE_avg": stock["PE"], "Forward_PE_avg": stock["Forward_PE"] if stock["Forward_PE"] else stock["PE"]}
        PE_s, Forward_PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_scores(stock, sector_avg, manual_scores)
        
        st.write("### 基本財務指標")
        st.dataframe(pd.DataFrame([
            ["股票代號", symbol],
            ["股價", format_large(price)],
            ["PE", format_large(stock["PE"])],
            ["Forward PE", format_large(stock["Forward_PE"])],
            ["ROE", format_large(stock["ROE"])],
            ["EPS", format_large(stock["EPS"])],
            ["Forward EPS", format_large(stock["Forward_EPS"])],
            ["PEG", "-" if not stock["PEG"] else round(stock["PEG"],2)]
        ], columns=["指標","數值"]))
        
        st.write("### 分數")
        st.metric("PE_score", PE_s)
        st.metric("Forward_PE_score", Forward_PE_s)
        st.metric("ROE_score", ROE_s)
        st.metric("Policy_score", Policy_s)
        st.metric("Moat_score", Moat_s)
        st.metric("Growth_score", Growth_s)
        st.metric("綜合分數", Total_s)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    stocks_data = []
    manual_scores = {}
    for symbol in SECTORS[sector]:
        info = get_info(symbol)
        if not info:
            continue
        price = info.get("currentPrice")
        stock = {
            "symbol": symbol,
            "股號": symbol,
            "PE": info.get("trailingPE"),
            "Forward_PE": info.get("forwardPE"),
            "ROE": info.get("returnOnEquity"),
            "FCF": info.get("freeCashflow"),
            "NetDebt": info.get("totalDebt"),
            "EBITDA": info.get("ebitda"),
            "EPS": info.get("trailingEps"),
            "Forward_EPS": info.get("forwardEps"),
            "PEG": info.get("pegRatio"),
            "Price": price
        }
        manual_policy = st.sidebar.number_input(f"{symbol} 政策分數", 0, 100, key=f"{symbol}_policy")
        manual_moat = st.sidebar.number_input(f"{symbol} 護城河分數", 0, 100, key=f"{symbol}_moat")
        manual_growth = st.sidebar.number_input(f"{symbol} 成長分數", 0, 100, key=f"{symbol}_growth")
        manual_scores[symbol] = {"Policy_score": manual_policy,"Moat_score": manual_moat,"Growth_score": manual_growth}
        stocks_data.append(stock)
    
    # 計算產業平均
    PE_vals = [s["PE"] for s in stocks_data if s["PE"]]
    Forward_PE_vals = [s["Forward_PE"] for s in stocks_data if s["Forward_PE"]]
    sector_avg = {
        "PE_avg": sum(PE_vals)/len(PE_vals) if PE_vals else None,
        "Forward_PE_avg": sum(Forward_PE_vals)/len(Forward_PE_vals) if Forward_PE_vals else None
    }
    
    # 計算分數
    rows=[]
    for stock in stocks_data:
        PE_s, Forward_PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_scores(stock, sector_avg, manual_scores)
        rows.append({
            "股票代號": stock["symbol"],
            "股價": format_large(stock["Price"]),
            "PE": format_large(stock["PE"]),
            "Forward PE": format_large(stock["Forward_PE"]),
            "ROE": format_large(stock["ROE"]),
            "EPS": format_large(stock["EPS"]),
            "Forward EPS": format_large(stock["Forward_EPS"]),
            "PEG": "-" if not stock["PEG"] else round(stock["PEG"],2),
            "PE_score": PE_s,
            "Forward_PE_score": Forward_PE_s,
            "ROE_score": ROE_s,
            "Policy_score": Policy_s,
            "Moat_score": Moat_s,
            "Growth_score": Growth_s,
            "Total_score": Total_s
        })
    df = pd.DataFrame(rows)
    st.dataframe(df.sort_values("Total_score",ascending=False), use_container_width=True)
