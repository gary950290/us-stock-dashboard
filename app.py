import streamlit as st
import pandas as pd

from modules.price_fundamental import get_price, get_fundamentals
from modules.scoring import total_score

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="美股分析儀表板",
    layout="wide"
)

st.title("📊 美股分析儀表板（股價｜估值｜產業比較｜綜合評分）")

# =========================
# 產業股票池（你可自行新增）
# =========================
SECTORS = {
    "Mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "資安": ["CRWD", "PANW", "ZS", "OKTA", "S"],
    "半導體": ["NVDA", "AMD", "INTC", "TSM", "AVGO"]
}

# =========================
# 側邊欄
# =========================
st.sidebar.header("⚙️ 分析設定")

mode = st.sidebar.selectbox(
    "選擇分析模式",
    ["單一股票分析", "產業共同比較"]
)

# =========================
# 單一股票分析
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("輸入美股代碼", "NVDA")

    st.subheader(f"📌 {symbol} 單一股票分析")

    col1, col2 = st.columns(2)

    # --- 股價 ---
    with col1:
        price_data = get_price(symbol)
        if price_data["price"]:
            st.metric(
                "即時股價",
                f"${price_data['price']}",
                f"{price_data['change']:.2f}%"
            )
        else:
            st.warning("無法取得股價資料")

    # --- 估值 ---
    with col2:
        st.markdown("### 📐 估值指標")
        fundamentals = get_fundamentals(symbol)
        st.table(fundamentals)

# =========================
# 產業共同比較
# =========================
elif mode == "產業共同比較":
    sector = st.sidebar.selectbox("選擇產業", list(SECTORS.keys()))

    st.subheader(f"🏭 {sector} 產業比較")

    rows = []

    for symbol in SECTORS[sector]:
        try:
            df = get_fundamentals(symbol)
            row = {
                "股票": symbol
            }

            for _, r in df.iterrows():
                row[r["指標"]] = r["數值"]

            # =========================
            # 政策分數（先用規則）
            # =========================
            if sector in ["Mag7", "半導體", "資安"]:
                policy_score = 1
            else:
                policy_score = 0

            # =========================
            # 平台 / 專業成本（護城河）
            # 你可手動調整
            # =========================
            MOAT = {
                "AAPL": 1, "MSFT": 1, "GOOGL": 1, "AMZN": 1, "META": 1,
                "NVDA": 1, "TSLA": 0.5,
                "CRWD": 1, "PANW": 1, "ZS": 0.5, "OKTA": 0.5, "S": 0.5,
                "AMD": 0.5, "INTC": 0.3, "TSM": 1, "AVGO": 1
            }

            moat_score = MOAT.get(symbol, 0.3)

            # =========================
            # 綜合評分
            # =========================
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

        except Exception as e:
            st.warning(f"{symbol} 資料取得失敗")

    if rows:
        result_df = pd.DataFrame(rows)
        result_df = result_df.sort_values("綜合評分", ascending=False)

        st.dataframe(result_df, use_container_width=True)

        st.markdown("### 🏆 產業排名（依綜合評分）")
        st.table(
            result_df[["股票", "綜合評分"]]
            .reset_index(drop=True)
        )

# =========================
# 說明區
# =========================
with st.expander("📘 評分邏輯說明"):
    st.markdown("""
    **綜合評分 =**
    - 估值合理性（PE / ROE）
    - 政策與產業趨勢
    - 平台與專業護城河（Switching Cost / Network Effect）

    > 所有權重與規則皆可調整，未來可升級為 AI 模型
    """)
