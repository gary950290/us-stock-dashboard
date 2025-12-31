import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="美股分析儀表板（專業版）",
    layout="wide"
)

st.title("📊 美股分析儀表板（專業細緻化版）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "資安": ["CRWD", "PANW", "ZS", "OKTA", "S"],
    "半導體": ["NVDA", "AMD", "INTC", "TSM", "AVGO"]
}

# =========================
# 護城河評分
# =========================
MOAT = {
    "AAPL": 1, "MSFT": 1, "GOOGL": 1, "AMZN": 1, "META": 1,
    "NVDA": 1, "TSLA": 0.5,
    "CRWD": 1, "PANW": 1, "ZS": 0.5, "OKTA": 0.5, "S": 0.5,
    "AMD": 0.5, "INTC": 0.3, "TSM": 1, "AVGO": 1
}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox(
    "選擇模式",
    ["產業共同比較", "單一股票分析"],
    index=0
)
# 投資風格調整權重
style = st.sidebar.selectbox(
    "投資風格",
    ["穩健型", "成長型", "平衡型"],
    index=2
)
WEIGHTS = {
    "穩健型": {"PE": 0.4, "ROE":0.3, "Policy":0.1, "Moat":0.2, "Growth":0.0},
    "成長型": {"PE":0.2, "ROE":0.2, "Policy":0.2, "Moat":0.1, "Growth":0.3},
    "平衡型": {"PE":0.3, "ROE":0.2, "Policy":0.2, "Moat":0.2, "Growth":0.1}
}

# =========================
# 工具函數
# =========================
def get_price(symbol):
    info = yf.Ticker(symbol).info
    return info.get("currentPrice"), info.get("regularMarketChangePercent")

def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow"),
        "Revenue_5Y_CAGR": info.get("revenueGrowth")  # 近年營收增長率
    }
    # 小數點兩位
    for k in data:
        if isinstance(data[k], float):
            data[k] = round(data[k], 4)
    return pd.DataFrame(data.items(), columns=["指標","數值"])

def format_large_numbers(value):
    if isinstance(value, (int, float)) and value is not None:
        if value >= 1e9:
            return f"{value/1e9:.2f} B"
        elif value >= 1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def format_df(df, decimals=2):
    display_df = df.copy()
    float_cols = display_df.select_dtypes(include=["float", "float64"]).columns
    display_df[float_cols] = display_df[float_cols].round(decimals)
    return display_df

# =========================
# 細緻化評分函數
# =========================
def compute_scores(row, sector):
    # 估值分數（PE）
    PE_lower, PE_upper = 15, 50
    PE = row.get("PE")
    if PE and PE_upper != PE_lower:
        PE_score = max(0, min(100, (PE_upper - PE)/(PE_upper - PE_lower)*100))
    else:
        PE_score = 50

    # ROE分數
    ROE = row.get("ROE")
    ROE_score = min(max(ROE/0.3*100, 0), 100) if ROE else 50

    # 政策分數
    Policy_score = 100 if sector in ["Mag7","資安","半導體"] else 50

    # 護城河分數
    moat_score = MOAT.get(row["股票"],0.3)*100

    # 成長分數（Revenue CAGR）
    growth = row.get("Revenue_5Y_CAGR")
    Growth_score = min(max(growth/0.3*100,0),100) if growth else 50

    # 加權總分
    w = WEIGHTS[style]
    Total_score = round(
        PE_score*w["PE"] + ROE_score*w["ROE"] + Policy_score*w["Policy"] +
        moat_score*w["Moat"] + Growth_score*w["Growth"],2
    )
    return PE_score, ROE_score, Policy_score, moat_score, Growth_score, Total_score

# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼","NVDA")
    st.subheader(f"📌 {symbol} 分析")
    price, change = get_price(symbol)
    if price:
        st.metric("即時股價", f"${price:.2f}", f"{change:.2f}%")
    funds_df = get_fundamentals(symbol)
    # FCF / 市值轉單位
    for col in ["FCF","市值"]:
        if col in funds_df["指標"].values:
            funds_df.loc[funds_df["指標"]==col,"數值"] = \
                funds_df.loc[funds_df["指標"]==col,"數值"].apply(format_large_numbers)
    st.table(funds_df)

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector = st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
    st.subheader(f"🏭 {sector} 產業比較")
    rows=[]
    for symbol in SECTORS[sector]:
        try:
            df = get_fundamentals(symbol)
            row={"股票":symbol}
            for _, r in df.iterrows():
                row[r["指標"]] = r["數值"]
            PE_s, ROE_s, Policy_s, Moat_s, Growth_s, Total_s = compute_scores(row,sector)
            row["PE_score"]=round(PE_s,2)
            row["ROE_score"]=round(ROE_s,2)
            row["Policy_score"]=round(Policy_s,2)
            row["Moat_score"]=round(Moat_s,2)
            row["Growth_score"]=round(Growth_s,2)
            row["綜合分數"]=round(Total_s,2)
            # FCF / 市值單位轉換
            for col in ["FCF","市值"]:
                if col in row:
                    row[col] = format_large_numbers(row[col])
            rows.append(row)
        except:
            pass
    if rows:
        result_df=pd.DataFrame(rows)
        result_df=format_df(result_df)
        result_df=result_df.sort_values("綜合分數",ascending=False)
        st.dataframe(result_df,use_container_width=True)

# =========================
# 評分公式說明
# =========================
with st.expander("📘 評分依據與公式"):
    st.markdown("""
    **各因子計算方式**：
    - **PE_score (估值)**：PE 越低越好，行業合理區間 15~50，線性映射到 0~100
    - **ROE_score (盈利能力)**：ROE 越高越好，30% ROE 為滿分，線性映射 0~100
    - **Policy_score (政策)**：熱門產業 Mag7/資安/半導體 =100，其他=50
    - **Moat_score (護城河)**：根據品牌、專利、平台優勢 0~1，乘 100
    - **Growth_score (成長潛力)**：近五年營收 CAGR / 30%，線性映射 0~100
    - **綜合分數** = 各因子乘以投資風格權重後加總
    """)
