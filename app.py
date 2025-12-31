import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="美股分析儀表板",
    layout="wide"
)

st.title("📊 美股分析儀表板（穩定版）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "資安": ["CRWD", "PANW", "ZS", "OKTA", "S"],
    "半導體": ["NVDA", "AMD", "INTC", "TSM", "AVGO"]
}

# =========================
# 函數：股價
# =========================
def get_price(symbol):
    info = yf.Ticker(symbol).info
    return info.get("currentPrice"), info.get("regularMarketChangePercent")

# =========================
# 函數：估值
# =========================
def get_fundamentals(symbol):
    info = yf.Ticker(symbol).info
    data = {
        "股價": info.get("currentPrice"),
        "PE": info.get("trailingPE"),
        "Forward PE": info.get("forwardPE"),
        "EPS": info.get("trailingEps"),
        "ROE": info.get("returnOnEquity"),
        "市值": info.get("marketCap"),
        "FCF": info.get("freeCashflow")
    }
    return pd.DataFrame(data.items(), columns=["指標", "數值"])

# =========================
# 函數：綜合評分
# =========================
def total_score(pe, roe, policy, moat):
    score = 0

    if pe and pe < 30:
        score += 40
    if roe and roe > 0.15:
        score += 20

    score += policy * 20
    score += moat * 20

    return score

# =========================
# 側邊欄
# =========================
st.sidebar.header("⚙️ 分析設定")

mode = st.sidebar.selectbox(
    "選擇模式",
    ["單一股票分析", "產業共同比較"]
)

# =========================
# 單一股票分析
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "NVDA")

    st.subheader(f"📌 {symbol} 分析")

    price, change = get_price(symbol)

    if price:
        st.metric("即時股價", f"${price}", f"{change:.2f}%")
    else:
        st.warning("無法取得股價")

    st.markdown("### 📐 估值指標")
    st.table(get_fundamentals(symbol))

# =========================
# 產業比較
# =========================
elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))
    st.subheader(f"🏭 {sector} 產業比較")

    rows = []

    MOAT = {
        "AAPL": 1, "MSFT": 1, "GOOGL": 1, "AMZN": 1, "META": 1,
        "NVDA": 1, "TSLA": 0.5,
        "CRWD": 1, "PANW": 1, "ZS": 0.5, "OKTA": 0.5, "S": 0.5,
        "AMD": 0.5, "INTC": 0.3, "TSM": 1, "AVGO": 1
    }

    for symbol in SECTORS[sector]:
        try:
            df = get_fundamentals(symbol)
            row = {"股票": symbol}

            for _, r in df.iterrows():
                row[r["指標"]] = r["數值"]

            policy_score = 1 if sector in ["Mag7", "資安", "半導體"] else 0
            moat_score = MOAT.get(symbol, 0.3)

            score = total_score(
                pe=row.get("PE"),
                roe=row.get("ROE"),
                policy=policy_score,
                moat=moat_score
            )

            row["政策分數"] = policy_score
            row["護城河分數"] = moat_score
            row["綜合評分"] = score

            rows.append(row)

        except:
            pass

    if rows:
        result_df = pd.DataFrame(rows).sort_values("綜合評分", ascending=False)
        st.dataframe(result_df, use_container_width=True)

# =========================
# 說明
# =========================
with st.expander("📘 評分邏輯說明"):
    st.markdown("""
    **綜合評分包含：**
    - 估值合理性（PE / ROE）
    - 產業與政策趨勢
    - 平台與專業護城河（Switching Cost / Network Effect）

    👉 權重可依你的投資偏好調整
    """)
