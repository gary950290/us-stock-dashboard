import streamlit as st
from modules.price_fundamental import get_price, get_fundamentals

st.title("📊 美股分析儀表板")

symbol = st.text_input("輸入股票代碼", "NVDA")
mode = st.selectbox("選擇分析模式", ["股價", "估值"])

if mode == "股價":
    data = get_price(symbol)
    st.metric("股價", data["price"], f'{data["change"]:.2f}%')

if mode == "估值":
    st.table(get_fundamentals(symbol))
