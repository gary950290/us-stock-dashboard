import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import json
import requests

# 設定重試次數

MAX_RETRIES = 3

# OpenRouter 免費模型列表 (按優先順序)

FREE_MODELS = [
“meta-llama/llama-3.1-8b-instruct:free”,
“mistralai/mistral-7b-instruct:free”,
“openchat/openchat-7b:free”
]

# =========================

# 持久化數據管理

# =========================

def save_persistent_data():
“”“將關鍵數據保存到 session_state 的持久化結構中”””
persistent_data = {
“manual_scores”: st.session_state.get(“manual_scores”, {}),
“weights”: st.session_state.get(“weights”, {}),
“last_insights”: st.session_state.get(“last_insights”, {}),
“last_updated”: datetime.now().isoformat()
}
st.session_state.persistent_data = persistent_data
return persistent_data

def load_persistent_data():
“”“從 session_state 載入持久化數據”””
if “persistent_data” in st.session_state:
data = st.session_state.persistent_data
st.session_state.manual_scores = data.get(“manual_scores”, {})
st.session_state.weights = data.get(“weights”, {})
st.session_state.last_insights = data.get(“last_insights”, {})
return True
return False

# =========================

# 初始化 OpenRouter API

# =========================

def init_openrouter():
“”“初始化 OpenRouter API”””
try:
api_key = st.secrets.get(“OPENROUTER_API_KEY”, “”)
if not api_key:
st.error(“❌ 找不到 OPENROUTER_API_KEY。請在 Streamlit Secrets 中設定。”)
st.info(“💡 前往 https://openrouter.ai/keys 免費註冊並取得 API Key”)
st.stop()
return api_key
except Exception as e:
st.error(f”❌ API 初始化失敗：{e}”)
st.stop()

# =========================

# 設定與 CSS 注入

# =========================

st.set_page_config(page_title=“2026 專業美股投資評比系統”, layout=“wide”)
st.title(“🏛️ 2026 專業美股投資評比系統”)
st.caption(“基於 FCF 安全性、前瞻估值與產業專屬邏輯的量化分析儀表板”)

st.markdown(
“””
<style>
.stApp {
overflow-y: auto !important;
max-height: 100vh;
}
div[data-testid^=“stVerticalBlock”] {
overflow-y: auto !important;
}
</style>
“””,
unsafe_allow_html=True
)

# =========================

# 產業股票池

# =========================

SECTORS = {
“Mag7”: [“AAPL”,“MSFT”,“GOOGL”,“AMZN”,“META”,“NVDA”,“TSLA”],
“資安”: [“CRWD”,“PANW”,“ZS”,“OKTA”,“FTNT”,“S”],
“半導體”: [“NVDA”,“AMD”,“INTC”,“TSM”,“AVGO”],
“能源”: [“TSLA”,“CEG”,“FLNC”,“TE”,“NEE”,“ENPH”,“EOSE”,“VST”,“PLUG”,“OKLO”,“SMR”,“BE”,“GEV”],
“NeoCloud”: [“NBIS”,“IREN”,“CRWV”,“APLD”]
}

# =========================

# 核心權重配置 (2026 邏輯)

# =========================

SECTOR_CONFIG = {
“Mag7”: {
“weights”: {“Valuation”: 0.25, “Quality”: 0.25, “Growth”: 0.30, “MoatPolicy”: 0.20},
“focus”: “AI 變現效率與現金流”
},
“資安”: {
“weights”: {“Valuation”: 0.20, “Quality”: 0.30, “Growth”: 0.30, “MoatPolicy”: 0.20},
“focus”: “毛利率與平台定價權”
},
“能源”: {
“weights”: {“Valuation”: 0.15, “Quality”: 0.35, “Growth”: 0.15, “MoatPolicy”: 0.35},
“focus”: “FCF 與政策補貼”
},
“半導體”: {
“weights”: {“Valuation”: 0.30, “Quality”: 0.25, “Growth”: 0.30, “MoatPolicy”: 0.15},
“focus”: “前瞻盈餘與製程領先”
},
“NeoCloud”: {
“weights”: {“Valuation”: 0.10, “Quality”: 0.15, “Growth”: 0.60, “MoatPolicy”: 0.15},
“focus”: “未來規模與成長寬容度”
}
}

# =========================

# 載入持久化數據

# =========================

if not load_persistent_data():
# 首次載入，初始化所有必要的 session_state
if “weights” not in st.session_state:
st.session_state.weights = {s: SECTOR_CONFIG[s][“weights”].copy() for s in SECTORS.keys()}
if “manual_scores” not in st.session_state:
st.session_state.manual_scores = {}
if “last_insights” not in st.session_state:
st.session_state.last_insights = {}

# =========================

# 工具函數

# =========================

@st.cache_data(ttl=300)
def get_stock_data(symbol):
try:
ticker = yf.Ticker(symbol)
return ticker.info
except:
return None

def get_tier(score):
if score >= 80: return “Tier 1 (強烈優先配置) 🚀”
elif score >= 60: return “Tier 2 (穩健配置) ⚖️”
else: return “Tier 3 (觀察或減碼) ⚠️”

# =========================

# 評分引擎 (2026 專業邏輯)

# =========================

def calculate_2026_score(info, sector, manual_scores, sector_avg_data):
symbol = info.get(“symbol”)

```
# 1. 前瞻估值 (Valuation)
fwd_pe = info.get("forwardPE")
avg_fwd_pe = sector_avg_data.get("avg_fwd_pe", 25)
val_score = 50
if fwd_pe:
    val_score = max(0, min(100, (avg_fwd_pe / fwd_pe) * 50))
    if sector == "Mag7" and fwd_pe < avg_fwd_pe * 0.9:
        val_score = min(100, val_score * 1.2)

# 2. 獲利質量 (Quality)
roe = info.get("returnOnEquity", 0)
fcf = info.get("freeCashflow", 0)
gross_margin = info.get("grossMargins", 0)
op_margin = info.get("operatingMargins", 0)

qual_score = 50
if sector == "Mag7":
    qual_score = max(0, min(100, roe * 400))
elif sector == "資安":
    qual_score = max(0, min(100, gross_margin * 100))
    if gross_margin > 0.75: qual_score += 20
elif sector == "能源":
    qual_score = 100 if fcf > 0 else 50
    if fcf < 0: qual_score -= 50
elif sector == "半導體":
    qual_score = max(0, min(100, op_margin * 300))
elif sector == "NeoCloud":
    qual_score = 50
    
# 3. 成長動能 (Growth)
rev_growth = info.get("revenueGrowth", 0)
growth_score = max(0, min(100, rev_growth * 200))

if sector == "Mag7" and rev_growth > 0.2: growth_score *= 1.2
if sector == "NeoCloud" and rev_growth > 0.4: growth_score = 100

# 4. 政策與護城河 (MoatPolicy)
policy_score = manual_scores.get("Policy", 50)
moat_score = manual_scores.get("Moat", 50)
moat_policy_score = (policy_score + moat_score) / 2

# 5. 綜合計算
w = st.session_state.weights.get(sector, SECTOR_CONFIG[sector]["weights"])
total_score = (
    val_score * w["Valuation"] +
    qual_score * w["Quality"] +
    growth_score * w["Growth"] +
    moat_policy_score * w["MoatPolicy"]
)

# 6. 懲罰與加成係數
final_adjustment = 0
if sector == "資安" and gross_margin > 0.75: final_adjustment += 5
if (sector == "能源" or sector == "NeoCloud") and fcf < 0: final_adjustment -= 10

total_score = max(0, min(100, total_score + final_adjustment))

return {
    "Total": round(total_score, 2),
    "Valuation": round(val_score, 2),
    "Quality": round(qual_score, 2),
    "Growth": round(growth_score, 2),
    "MoatPolicy": round(moat_policy_score, 2),
    "Adjustment": final_adjustment
}
```

# =========================

# AI 洞察 (OpenRouter)

# =========================

def call_openrouter_with_retry(prompt, status, api_key, max_retries=MAX_RETRIES):
“”“使用多模型輪詢機制呼叫 OpenRouter API”””
delay = 2

```
for model in FREE_MODELS:
    status.write(f"🤖 嘗試使用模型：{model}")
    
    for attempt in range(max_retries):
        try:
            status.write(f"   ⏳ 第 {attempt + 1} 次嘗試...")
            
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                # 清理並解析 JSON
                clean_json = content.replace('```json', '').replace('```', '').strip()
                insight = json.loads(clean_json)
                
                # 驗證必要欄位
                required_fields = ["sentiment", "summary", "suggested_weights", "reason"]
                if all(field in insight for field in required_fields):
                    status.write(f"   ✅ 成功使用模型：{model}")
                    return insight
                else:
                    raise ValueError("回應缺少必要欄位")
            
            elif response.status_code == 429:
                status.warning(f"   ⚠️ 模型 {model} 達到速率限制，嘗試下一個模型...")
                break  # 跳到下一個模型
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            if attempt < max_retries - 1:
                status.warning(f"   ⚠️ 嘗試失敗，{delay} 秒後重試...")
                time.sleep(delay)
                delay *= 2
            else:
                status.warning(f"   ❌ 模型 {model} 失敗，嘗試下一個模型...")
                break  # 跳到下一個模型

status.error("❌ 所有模型都已嘗試，分析失敗")
return None
```

def get_ai_market_insight(symbol, sector, current_weights, status, api_key):
“”“準備提示詞並呼叫 API”””
try:
ticker = yf.Ticker(symbol)
news = ticker.news[:5]

```
    safe_news_titles = [f"- {n['title']}" for n in news if isinstance(n, dict) and 'title' in n]
    
    if safe_news_titles:
        news_text = "\n".join(safe_news_titles)
    else:
        news_text = f"找不到最新新聞。請基於 {symbol} 的產業趨勢進行分析。"
    
    prompt = f"""你是資深美股分析師。針對 {symbol} ({sector}產業) 進行 2026 投資評級分析：
```

最新新聞：
{news_text}

當前權重：{current_weights}

請判斷利好/利空並建議權重調整（總和需為 1.0）。

嚴格以 JSON 格式回覆：
{{
“sentiment”: “利好|利空|中性”,
“summary”: “簡短總結”,
“suggested_weights”: {{“Valuation”: float, “Quality”: float, “Growth”: float, “MoatPolicy”: float}},
“reason”: “調整理由”
}}”””

```
    insight = call_openrouter_with_retry(prompt, status, api_key)
    return insight
    
except Exception as e:
    status.error(f"❌ 數據獲取失敗：{e}")
    return None
```

def batch_analyze_sector(sector, api_key, progress_bar, status_text):
“”“批量分析整個產業”””
stocks = SECTORS[sector]
results = {}

```
for idx, symbol in enumerate(stocks):
    progress = (idx + 1) / len(stocks)
    progress_bar.progress(progress)
    status_text.text(f"正在分析 {symbol} ({idx + 1}/{len(stocks)})...")
    
    with st.status(f"分析 {symbol}...", expanded=False) as status:
        # 確保該股票有初始評分
        if symbol not in st.session_state.manual_scores:
            st.session_state.manual_scores[symbol] = {"Policy": 50, "Moat": 50}
        
        current_weights = st.session_state.weights.get(sector, SECTOR_CONFIG[sector]["weights"])
        insight = get_ai_market_insight(symbol, sector, current_weights, status, api_key)
        
        if insight:
            # 儲存該股票的 AI 洞察
            if symbol not in st.session_state.last_insights:
                st.session_state.last_insights[symbol] = {}
            st.session_state.last_insights[symbol] = insight
            
            # 更新該產業的權重（使用最新分析的股票權重）
            st.session_state.weights[sector] = insight["suggested_weights"]
            results[symbol] = insight
            status.update(label=f"✅ {symbol} 分析完成", state="complete")
        else:
            status.update(label=f"❌ {symbol} 分析失敗", state="error")
        
        time.sleep(1)  # 避免速率限制

# 儲存持久化數據
save_persistent_data()
return results
```

# =========================

# UI 佈局

# =========================

# 初始化 API

api_key = init_openrouter()

st.sidebar.header(“⚙️ 2026 評比設定”)

# 顯示數據狀態

if “persistent_data” in st.session_state:
last_updated = st.session_state.persistent_data.get(“last_updated”, “未知”)
st.sidebar.success(f”✅ 已載入持久化數據\n上次更新：{last_updated[:19]}”)

selected_sector = st.sidebar.selectbox(“選擇產業”, list(SECTORS.keys()))
selected_stock = st.sidebar.selectbox(“選擇股票”, SECTORS[selected_sector])

# 手動評分持久化

current_stock = selected_stock
if current_stock not in st.session_state.manual_scores:
st.session_state.manual_scores[current_stock] = {“Policy”: 50, “Moat”: 50}

def update_policy_score():
st.session_state.manual_scores[current_stock][“Policy”] = st.session_state[f”{current_stock}_p”]
save_persistent_data()

def update_moat_score():
st.session_state.manual_scores[current_stock][“Moat”] = st.session_state[f”{current_stock}_m”]
save_persistent_data()

policy_default = st.session_state.manual_scores[current_stock][“Policy”]
moat_default = st.session_state.manual_scores[current_stock][“Moat”]

st.sidebar.subheader(“✏️ 手動評分”)
m_policy = st.sidebar.slider(
“政策受益度”,
0, 100,
value=policy_default,
key=f”{current_stock}_p”,
on_change=update_policy_score
)
m_moat = st.sidebar.slider(
“護城河粘性”,
0, 100,
value=moat_default,
key=f”{current_stock}_m”,
on_change=update_moat_score
)

# AI 分析按鈕

col_a, col_b = st.sidebar.columns(2)

with col_a:
if st.button(“🤖 分析此股票”, use_container_width=True):
with st.status(“🤖 正在執行 AI 分析…”, expanded=True) as status:
insight = get_ai_market_insight(
selected_stock,
selected_sector,
st.session_state.weights[selected_sector],
status,
api_key
)

```
        if insight:
            # 儲存該股票的洞察
            if selected_stock not in st.session_state.last_insights:
                st.session_state.last_insights[selected_stock] = {}
            st.session_state.last_insights[selected_stock] = insight
            st.session_state.weights[selected_sector] = insight["suggested_weights"]
            save_persistent_data()
            status.update(label="✅ 分析完成！", state="complete", expanded=False)
            st.rerun()
```

with col_b:
if st.button(“🏭 分析整個產業”, use_container_width=True):
st.sidebar.info(“開始批量分析…”)
progress_bar = st.sidebar.progress(0)
status_text = st.sidebar.empty()

```
    results = batch_analyze_sector(selected_sector, api_key, progress_bar, status_text)
    
    progress_bar.empty()
    status_text.empty()
    st.sidebar.success(f"✅ 完成 {len(results)}/{len(SECTORS[selected_sector])} 股票分析")
    st.rerun()
```

# 顯示當前股票的 AI 洞察

if selected_stock in st.session_state.last_insights:
ins = st.session_state.last_insights[selected_stock]
st.info(f”### 🤖 AI 投資洞察 ({ins[‘sentiment’]})\n**總結**: {ins[‘summary’]}\n\n**權重調整理由**: {ins[‘reason’]}”)

# 顯示當前產業權重

st.sidebar.subheader(“⚖️ 當前產業權重”)
current_weights = st.session_state.weights[selected_sector]
for dim, weight in current_weights.items():
st.sidebar.text(f”{dim}: {weight:.2f}”)

# 重置按鈕

if st.sidebar.button(“🔄 重置產業權重”, use_container_width=True):
st.session_state.weights[selected_sector] = SECTOR_CONFIG[selected_sector][“weights”].copy()
save_persistent_data()
st.sidebar.success(“✅ 已重置為預設權重”)
st.rerun()

# 獲取數據並計算

info = get_stock_data(selected_stock)
if info:
sector_avg_data = {“avg_fwd_pe”: 25}
scores = calculate_2026_score(
info,
selected_sector,
{“Policy”: m_policy, “Moat”: m_moat},
sector_avg_data
)

```
col1, col2, col3 = st.columns(3)
col1.metric("🎯 綜合評分", scores["Total"])
col2.metric("投資評級", get_tier(scores["Total"]))
col3.metric("前瞻 PE", info.get("forwardPE", "N/A"))

st.subheader(f"📊 {selected_sector} 評分維度 (焦點：{SECTOR_CONFIG[selected_sector]['focus']})")

detail_data = pd.DataFrame({
    "維度": ["前瞻估值", "獲利質量", "成長動能", "政策與護城河"],
    "得分": [scores["Valuation"], scores["Quality"], scores["Growth"], scores["MoatPolicy"]],
    "權重": [current_weights[k] for k in ["Valuation", "Quality", "Growth", "MoatPolicy"]]
})
st.dataframe(detail_data, use_container_width=True)

if scores["Adjustment"] != 0:
    st.warning(f"⚠️ 觸發調整機制：總分已調整 {scores['Adjustment']} 分")

# 產業橫向比較
with st.expander(f"🏭 查看 {selected_sector} 產業橫向排序"):
    results = []
    for s in SECTORS[selected_sector]:
        s_info = get_stock_data(s)
        if s_info:
            s_manual = st.session_state.manual_scores.get(s, {"Policy": 50, "Moat": 50})
            s_scores = calculate_2026_score(s_info, selected_sector, s_manual, sector_avg_data)
            
            # 顯示是否有 AI 洞察
            has_insight = "✅" if s in st.session_state.last_insights else "⚪"
            
            results.append({
                "AI": has_insight,
                "股票": s,
                "綜合分數": s_scores["Total"],
                "評級": get_tier(s_scores["Total"]),
                "Fwd PE": s_info.get("forwardPE"),
                "FCF": s_info.get("freeCashflow"),
                "政策分數": s_manual["Policy"],
                "護城河分數": s_manual["Moat"]
            })
    st.dataframe(pd.DataFrame(results).sort_values("綜合分數", ascending=False), use_container_width=True)
```

else:
st.error(“無法獲取股票數據”)

# 在頁面底部顯示所有已分析股票的摘要

with st.expander(“📋 查看所有 AI 分析記錄”):
if st.session_state.last_insights:
for stock, insight in st.session_state.last_insights.items():
st.markdown(f”**{stock}** ({insight[‘sentiment’]}): {insight[‘summary’]}”)
else:
st.info(“尚未進行任何 AI 分析”)
