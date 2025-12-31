import streamlit as st

st.title("📈 我的第一個美股分析工具")

symbol = st.text_input("輸入股票代碼", "NVDA")

st.write("你輸入的是：", symbol)
