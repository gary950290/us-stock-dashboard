import streamlit as st
import requests
import json
import time
from datetime import datetime
import yfinance as yf
import pandas as pd

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="美股投資分析系統（OpenRouter）",
    layout="wide"
)

st.title("📊 美股投資分析系統（OpenRouter / DeepSeek）")

# =========================
# 常數設定
# =========================
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_PRIMARY = "deepseek/deepseek-r1:free"
MODEL_BACKUP = "mistralai/mistral-7b-instruct"
MAX_RETRIES = 3
TIMEOUT = 30

# =========================
# API Key
# =========================
if "OPENROUTER_API_KEY" not in st.secrets:
    st.error("❌ 未設定 OPENROUTER_API_KEY（請放入 .streamlit/secrets.toml）")
    st.stop()

OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]

# =========================
# OpenRouter 呼叫函式（含 fallback）
# =========================
def call_openrouter(prompt, model):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是資深美股投資分析師，請用結構化方式回答"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    response = requests.post(
        OPENROUTER_API_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def llm_analyze(prompt):
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            return call_openrouter(prompt, MODEL_PRIMARY)
        except Exception as e:
            last_error = e
            time.sleep(1)

    # fallback model
    try:
        return call_openrouter(prompt, MODEL_BACKUP)
    except Exception as e:
        st.error("❌ LLM 呼叫失敗")
        st.exception(e)
        raise last_error


# =========================
# 股票資料抓取
# =========================
def fetch_stock_basic(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    return {
        "公司名稱": info.get("longName"),
        "產業": info.get("industry"),
        "市值": info.get("marketCap"),
        "PE": info.get("trailingPE"),
        "ROE": info.get("returnOnEquity"),
        "毛利率": info.get("grossMargins"),
        "營業利益率": info.get("operatingMargins"),
    }


# =========================
# UI
# =========================
st.sidebar.header("⚙️ 分析設定")

ticker = st.sidebar.text_input(
    "輸入美股代號（例如：AAPL、NVDA、MSFT）",
    value="AAPL"
)

analyze_btn = st.sidebar.button("🚀 開始分析")

# =========================
# 主流程
# =========================
if analyze_btn:
    with st.spinner("📡 抓取股票資料中..."):
        try:
            stock_data = fetch_stock_basic(ticker)
        except Exception as e:
            st.error("❌ 股票資料抓取失敗")
            st.exception(e)
            st.stop()

    st.subheader("📌 基本面資料")
    st.json(stock_data)

    prompt = f"""
請針對以下公司進行中長期投資分析（1~3 年）：

公司基本資料：
{json.dumps(stock_data, ensure_ascii=False, indent=2)}

請輸出以下結構（JSON）：
{{
  "投資結論": "...",
  "成長動能": ["...", "..."],
  "主要風險": ["...", "..."],
  "估值觀點": "...",
  "是否適合中長期投資": "是 / 否 / 中立"
}}
"""

    with st.spinner("🤖 LLM 投資分析中（DeepSeek）..."):
        result_text = llm_analyze(prompt)

    st.subheader("🧠 AI 投資分析結果")

    # 嘗試解析 JSON
    try:
        result_json = json.loads(result_text)
        st.json(result_json)
    except:
        st.warning("⚠️ 無法解析為 JSON，顯示原始文字")
        st.write(result_text)

    st.caption(f"分析時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# =========================
# Footer
# =========================
st.markdown("---")
st.caption("Powered by OpenRouter + DeepSeek (free tier)")
