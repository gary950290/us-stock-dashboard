import streamlit as st  
import pandas as pd  
import yfinance as yf  
import time  
import requests  
import json  
import os

# =========================

# 0. 數據持久化配置

# =========================

VAULT_FILE = “investment_vault_2026.json”

def save_vault():  
“”“將當前 session_state 數據寫入 JSON 檔案”””  
with open(VAULT_FILE, “w”, encoding=“utf-8”) as f:  
json.dump(st.session_state.stock_vault, f, ensure_ascii=False, indent=4)

def load_vault():  
“”“從 JSON 檔案讀取數據，若檔案不存在則回傳空字典”””  
if os.path.exists(VAULT_FILE):  
try:  
with open(VAULT_FILE, “r”, encoding=“utf-8”) as f:  
return json.load(f)  
except:  
return {}  
return {}

# =========================

# 1. Google Gemini API 配置

# =========================

try:  
GOOGLE_API_KEY = st.secrets[“GOOGLE_API_KEY”]  
except:  
st.error(“❌ 找不到 GOOGLE_API_KEY。請在 Streamlit Secrets 中設定。”)  
st.stop()

GEMINI_API_URL = “https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent”

# API 限流設定

MAX_REQUESTS_PER_MINUTE = 15  # Gemini 免費版限制
REQUEST_INTERVAL = 60 / MAX_REQUESTS_PER_MINUTE  # 每次請求間隔（秒）

# 初始化請求記錄

if “api_requests” not in st.session_state:
st.session_state.api_requests = []

# =========================

# 2. 核心配置與初始化

# =========================

st.set_page_config(page_title=“2026 專業美股投資評比系統”, layout=“wide”)

SECTORS = {  
“Mag7”: [“AAPL”,“MSFT”,“GOOGL”,“AMZN”,“META”,“NVDA”,“TSLA”],  
“資安”: [“CRWD”,“PANW”,“ZS”,“OKTA”,“FTNT”,“S”],  
“半導體”: [“NVDA”,“AMD”,“INTC”,“TSM”,“AVGO”],  
“能源”: [“TSLA”,“CEG”,“FLNC”,“TE”,“NEE”,“ENPH”,“EOSE”,“VST”,“PLUG”,“OKLO”,“SMR”,“BE”,“GEV”],  
“NeoCloud”: [“NBIS”,“IREN”,“CRWV”,“APLD”]  
}

DEFAULT_WEIGHTS = {“Valuation”: 0.25, “Quality”: 0.25, “Growth”: 0.30, “MoatPolicy”: 0.20}

if “stock_vault” not in st.session_state:  
saved_data = load_vault()  
st.session_state.stock_vault = saved_data if saved_data else {}

def calculate_score(info, weights, manual):  
if not info: return 0  
fwd_pe = info.get(“forwardPE”, 25) or 25  
val_score = max(0, min(100, (25 / fwd_pe) * 50))  
qual_score = max(0, min(100, (info.get(“returnOnEquity”, 0) or 0) * 400))  
growth_score = max(0, min(100, (info.get(“revenueGrowth”, 0) or 0) * 200))  
moat_policy_score = (manual.get(“Policy”, 50) + manual.get(“Moat”, 50)) / 2

```
total = (val_score * weights["Valuation"] +   
         qual_score * weights["Quality"] +   
         growth_score * weights["Growth"] +   
         moat_policy_score * weights["MoatPolicy"])  
return round(total, 2)  
```

# =========================

# 3. 工具函數

# =========================

@st.cache_data(ttl=300)  
def get_stock_data(symbol, max_retries=3):  
“”“獲取股票數據，帶重試機制”””
for attempt in range(max_retries):
try:  
ticker = yf.Ticker(symbol)
info = ticker.info

```
        # 驗證數據有效性 - 檢查關鍵字段
        required_fields = ['symbol', 'quoteType']
        if info and any(field in info for field in required_fields):
            # 即使部分數據缺失也返回
            return info
        
        if attempt < max_retries - 1:
            time.sleep(1)
            
    except Exception as e:
        if attempt == max_retries - 1:
            st.warning(f"⚠️ {symbol}: {str(e)[:100]}")
        time.sleep(1)

return None
```

def call_gemini_api(prompt, status, max_retries=3):
“”“調用 Google Gemini API with rate limiting”””

```
# 清理超過1分鐘的舊請求記錄
current_time = time.time()
st.session_state.api_requests = [
    t for t in st.session_state.api_requests 
    if current_time - t < 60
]

# 檢查是否需要等待
if len(st.session_state.api_requests) >= MAX_REQUESTS_PER_MINUTE:
    oldest_request = min(st.session_state.api_requests)
    wait_time = 60 - (current_time - oldest_request)
    if wait_time > 0:
        status.write(f"⏳ API 限流保護：等待 {wait_time:.0f} 秒...")
        time.sleep(wait_time + 1)
        st.session_state.api_requests = []

for attempt in range(max_retries):
    try:
        status.write(f"🤖 調用 Gemini API (嘗試 {attempt+1}/{max_retries})...")
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1024,
            }
        }
        
        response = requests.post(
            f"{GEMINI_API_URL}?key={GOOGLE_API_KEY}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        # 記錄請求時間
        st.session_state.api_requests.append(time.time())
        
        if response.status_code == 200:
            result = response.json()
            
            # 解析 Gemini 回應
            if "candidates" in result and len(result["candidates"]) > 0:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                
                # 嘗試提取 JSON
                if "```json" in text:
                    json_str = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    json_str = text.split("```")[1].split("```")[0].strip()
                else:
                    json_str = text.strip()
                
                # 解析 JSON
                parsed_data = json.loads(json_str)
                status.write(f"✅ API 調用成功！")
                return parsed_data
            else:
                status.write(f"⚠️ API 回應格式異常")
                
        elif response.status_code == 429:
            status.write(f"⚠️ API 配額已達上限，等待 30 秒...")
            time.sleep(30)
        else:
            status.write(f"⚠️ HTTP {response.status_code}: {response.text[:100]}")
            
    except json.JSONDecodeError as e:
        status.write(f"⚠️ JSON 解析失敗: {str(e)[:50]}")
    except requests.Timeout:
        status.write(f"⏱️ 請求超時，重試中...")
    except Exception as e:
        status.write(f"❌ 錯誤: {str(e)[:80]}")
    
    if attempt < max_retries - 1:
        time.sleep(REQUEST_INTERVAL)

return None
```

def run_ai_analysis(symbol, sector, status):  
info = get_stock_data(symbol)  
if not info:
status.write(f”❌ {symbol}: 無法取得股票數據”)
return False

```
if symbol not in st.session_state.stock_vault:  
    st.session_state.stock_vault[symbol] = {
        "manual": {"Policy": 50, "Moat": 50}, 
        "weights": DEFAULT_WEIGHTS.copy(), 
        "insight": None
    }  

prompt = f"""你是專業的美股投資分析師。請分析以下股票並調整評分權重。
```

股票代號: {symbol}
產業: {sector}
財務數據:

- 前瞻本益比 (Forward PE): {info.get(‘forwardPE’, ‘N/A’)}
- 股東權益報酬率 (ROE): {info.get(‘returnOnEquity’, ‘N/A’)}
- 營收增長率 (Revenue Growth): {info.get(‘revenueGrowth’, ‘N/A’)}

任務: 根據該股票的產業特性和財務狀況，調整四個評分維度的權重。
權重說明:

- Valuation (估值): 重視價格合理性
- Quality (質量): 重視公司經營品質
- Growth (成長): 重視未來成長潛力
- MoatPolicy (護城河與政策): 重視競爭優勢和政策影響

要求:

1. 四個權重總和必須等於 1.0
1. 根據股票特性合理調整，例如成長股增加 Growth 權重，價值股增加 Valuation 權重
1. 用繁體中文回答

請以下列 JSON 格式回傳（不要包含其他文字）:
{{
“sentiment”: “看多/中性/看空”,
“summary”: “一句話總結投資觀點（50字內）”,
“suggested_weights”: {{
“Valuation”: 0.25,
“Quality”: 0.25,
“Growth”: 0.30,
“MoatPolicy”: 0.20
}},
“reason”: “說明為何這樣調整權重（100字內）”
}}”””

```
insight = call_gemini_api(prompt, status)  
if insight and "suggested_weights" in insight:  
    weights = insight["suggested_weights"]
    total = sum(weights.values())
    
    # 驗證並標準化權重
    if abs(total - 1.0) > 0.01:
        status.write(f"⚠️ {symbol}: 權重總和 {total:.2f}，自動標準化為 1.0")
        insight["suggested_weights"] = {k: v/total for k, v in weights.items()}
    
    st.session_state.stock_vault[symbol]["weights"] = insight["suggested_weights"]  
    st.session_state.stock_vault[symbol]["insight"] = insight  
    save_vault()
    status.write(f"✅ {symbol}: AI 分析完成並已存檔")
    return True
else:
    status.write(f"❌ {symbol}: AI 分析失敗，保持預設權重")
    return False  
```

# =========================

# 4. UI 邏輯

# =========================

st.title(“🏛️ 2026 專業美股投資評比系統”)
st.caption(“Powered by Google Gemini 2.0 Flash”)

selected_sector = st.sidebar.selectbox(“選擇產業”, list(SECTORS.keys()))  
selected_stock = st.sidebar.selectbox(“選擇股票”, SECTORS[selected_sector])

if selected_stock not in st.session_state.stock_vault:  
st.session_state.stock_vault[selected_stock] = {  
“manual”: {“Policy”: 50, “Moat”: 50},  
“weights”: DEFAULT_WEIGHTS.copy(),  
“insight”: None  
}

def sync_vault():  
st.session_state.stock_vault[selected_stock][“manual”][“Policy”] = st.session_state[f”{selected_stock}_p”]  
st.session_state.stock_vault[selected_stock][“manual”][“Moat”] = st.session_state[f”{selected_stock}_m”]  
save_vault()

st.sidebar.subheader(“✏️ 手動評分”)  
vault_m = st.session_state.stock_vault[selected_stock][“manual”]  
st.sidebar.slider(“政策受益度”, 0, 100, value=vault_m[“Policy”], key=f”{selected_stock}_p”, on_change=sync_vault)  
st.sidebar.slider(“護城河粘性”, 0, 100, value=vault_m[“Moat”], key=f”{selected_stock}_m”, on_change=sync_vault)

# 清除緩存按鈕

if st.sidebar.button(“🔄 清除數據緩存”):
st.cache_data.clear()
st.sidebar.success(“緩存已清除！”)
time.sleep(1)
st.rerun()

col_b1, col_b2 = st.sidebar.columns(2)  
if col_b1.button(“🤖 單股 AI 分析”):  
with st.status(f”分析 {selected_stock}…”, expanded=True) as status:  
if run_ai_analysis(selected_stock, selected_sector, status):  
status.update(label=“✅ 分析完成”, state=“complete”)  
else:
status.update(label=“⚠️ 分析遇到問題”, state=“error”)
time.sleep(1)
st.rerun()

if col_b2.button(“🚀 一鍵分析全產業”):
stocks = SECTORS[selected_sector]
total_stocks = len(stocks)

```
# 計算預估時間
estimated_time = (total_stocks * REQUEST_INTERVAL) / 60

if total_stocks > MAX_REQUESTS_PER_MINUTE:
    st.sidebar.warning(f"⚠️ 該產業有 {total_stocks} 支股票\n\n⏱️ 預估時間: {estimated_time:.1f} 分鐘\n\n💡 由於 Gemini 免費版限制（每分鐘 {MAX_REQUESTS_PER_MINUTE} 次），系統會自動限流")

with st.status(f"處理 {selected_sector} ({total_stocks}支股票)...", expanded=True) as status:
    success_count = 0
    fail_count = 0
    start_time = time.time()
    
    for idx, s in enumerate(stocks, 1):
        elapsed = time.time() - start_time
        remaining = total_stocks - idx
        avg_time = elapsed / idx if idx > 0 else REQUEST_INTERVAL
        eta = remaining * avg_time
        
        status.write(f"📊 [{idx}/{total_stocks}] 處理 {s}... (預估剩餘: {eta/60:.1f} 分鐘)")
        
        if run_ai_analysis(s, selected_sector, status):
            success_count += 1
        else:
            fail_count += 1
        
        # 智能等待：確保不超過速率限制
        if idx < total_stocks:
            status.write(f"⏳ 冷卻中... ({REQUEST_INTERVAL:.1f} 秒)")
            time.sleep(REQUEST_INTERVAL)
    
    total_time = (time.time() - start_time) / 60
    status.update(
        label=f"✅ 完成！成功: {success_count} | 失敗: {fail_count} | 耗時: {total_time:.1f} 分鐘",
        state="complete" if fail_count == 0 else "error"
    )
    time.sleep(2)
    st.rerun()
```

# 批次分析選項

st.sidebar.divider()
st.sidebar.subheader(“📦 批次分析模式”)
batch_size = st.sidebar.selectbox(
“每批次股票數”,
options=[5, 10, MAX_REQUESTS_PER_MINUTE],
index=0,
help=f”建議選 {MAX_REQUESTS_PER_MINUTE} 以下避免超限”
)

if st.sidebar.button(“🔄 分批分析當前產業”):
stocks = SECTORS[selected_sector]
total_stocks = len(stocks)
num_batches = (total_stocks + batch_size - 1) // batch_size

```
st.sidebar.info(f"將分 {num_batches} 批次執行\n每批 {batch_size} 支股票")

with st.status(f"批次處理 {selected_sector}...", expanded=True) as status:
    overall_success = 0
    overall_fail = 0
    
    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_stocks)
        batch_stocks = stocks[start_idx:end_idx]
        
        status.write(f"🔷 批次 {batch_num+1}/{num_batches}: 處理 {len(batch_stocks)} 支股票")
        
        for idx, s in enumerate(batch_stocks, 1):
            status.write(f"  [{idx}/{len(batch_stocks)}] {s}")
            if run_ai_analysis(s, selected_sector, status):
                overall_success += 1
            else:
                overall_fail += 1
            
            if idx < len(batch_stocks):
                time.sleep(REQUEST_INTERVAL)
        
        # 批次間等待
        if batch_num < num_batches - 1:
            status.write(f"⏸️ 批次間冷卻 60 秒...")
            time.sleep(60)
    
    status.update(
        label=f"✅ 全部批次完成！成功: {overall_success} | 失敗: {overall_fail}",
        state="complete" if overall_fail == 0 else "error"
    )
    time.sleep(2)
    st.rerun()
```

# =========================

# 5. 結果呈現

# =========================

# 添加調試模式開關

with st.sidebar.expander(“🔧 調試選項”):
debug_mode = st.checkbox(“顯示詳細錯誤信息”, value=False)
if st.button(“測試 yfinance 連線”):
with st.spinner(“測試中…”):
try:
test_ticker = yf.Ticker(“AAPL”)
test_info = test_ticker.info
if test_info and len(test_info) > 0:
st.success(f”✅ yfinance 正常！獲取到 {len(test_info)} 個字段”)
if debug_mode:
st.json(list(test_info.keys())[:20])
else:
st.error(“❌ yfinance 返回空數據”)
except Exception as e:
st.error(f”❌ 連線失敗: {str(e)}”)

info = get_stock_data(selected_stock)

if not info:
st.error(f”❌ 無法取得 {selected_stock} 的股票數據”)

```
with st.expander("🔍 故障排查建議", expanded=True):
    st.markdown("""
    ### 可能的原因：
    
    1. **網路連線問題**
       - 檢查網路是否正常
       - 嘗試刷新頁面 (F5)
    
    2. **yfinance API 暫時無法訪問**
       - Yahoo Finance 可能暫時維護
       - 稍後 5-10 分鐘再試
    
    3. **Streamlit Cloud 限制**
       - 某些地區可能有防火牆限制
       - 點擊側邊欄「🔄 清除數據緩存」
    
    4. **股票代碼錯誤**
       - 確認 `{selected_stock}` 是正確的美股代碼
    
    ### 快速測試：
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧪 測試 AAPL"):
            test_data = get_stock_data("AAPL")
            if test_data:
                st.success("✅ AAPL 數據正常")
            else:
                st.error("❌ AAPL 也無法獲取")
    
    with col2:
        if st.button("🧪 測試 MSFT"):
            test_data = get_stock_data("MSFT")
            if test_data:
                st.success("✅ MSFT 數據正常")
            else:
                st.error("❌ MSFT 也無法獲取")

st.stop()
```

# 正常顯示數據

s_data = st.session_state.stock_vault[selected_stock]  
total_score = calculate_score(info, s_data[“weights”], s_data[“manual”])

```
if s_data.get("insight"):  
    ins = s_data["insight"]  
    st.info(f"### 🤖 AI 洞察 ({ins.get('sentiment', 'N/A')})\n{ins.get('summary', 'N/A')}\n\n**權重調整理由**: {ins.get('reason', 'N/A')}")  

c1, c2, c3 = st.columns(3)  
c1.metric("🎯 綜合評分", total_score)  
c2.metric("前瞻 PE", info.get("forwardPE") if info.get("forwardPE") else "N/A")  
c3.metric("狀態", "✅ AI 已優化" if s_data.get("insight") else "⚪ 預設模式")

# 顯示更多財務指標
with st.expander("📊 詳細財務數據"):
    col1, col2, col3, col4 = st.columns(4)
    
    market_cap = info.get('marketCap')
    col1.metric("市值", f"${market_cap/1e9:.1f}B" if market_cap else "N/A")
    
    roe = info.get('returnOnEquity')
    col2.metric("ROE", f"{roe*100:.1f}%" if roe else "N/A")
    
    rev_growth = info.get('revenueGrowth')
    col3.metric("營收增長", f"{rev_growth*100:.1f}%" if rev_growth else "N/A")
    
    trailing_pe = info.get("trailingPE")
    col4.metric("本益比", f"{trailing_pe:.1f}" if trailing_pe else "N/A")
    
    # 額外信息
    if debug_mode:
        st.write("**可用數據字段:**")
        st.write(f"總共 {len(info)} 個字段")
        st.code(", ".join(list(info.keys())[:30]))

# 顯示當前權重
with st.expander("⚖️ 查看評分權重"):
    weights_df = pd.DataFrame([
        {
            "維度": k, 
            "權重": f"{v:.1%}", 
            "數值": v,
            "說明": {
                "Valuation": "估值合理性",
                "Quality": "經營品質",
                "Growth": "成長潛力",
                "MoatPolicy": "護城河與政策"
            }[k]
        } 
        for k, v in s_data["weights"].items()
    ])
    st.dataframe(weights_df, use_container_width=True, hide_index=True)

# 產業橫向比較
with st.expander("🏭 產業橫向排序 (含AI權重)", expanded=True):  
    compare_list = []
    progress_bar = st.progress(0)
    progress_text = st.empty()
    failed_stocks = []
    
    for idx, s in enumerate(SECTORS[selected_sector], 1):
        progress = idx / len(SECTORS[selected_sector])
        progress_bar.progress(progress)
        progress_text.text(f"載入中... {s} ({idx}/{len(SECTORS[selected_sector])})")
        
        s_info = get_stock_data(s)  
        s_v = st.session_state.stock_vault.get(s, {
            "manual": {"Policy": 50, "Moat": 50}, 
            "weights": DEFAULT_WEIGHTS.copy(),
            "insight": None
        })  
        
        if s_info:  
            s_total = calculate_score(s_info, s_v["weights"], s_v["manual"])
            weights = s_v["weights"]
            
            compare_list.append({  
                "股票": s, 
                "綜合分數": s_total,   
                "前瞻PE": s_info.get("forwardPE") if s_info.get("forwardPE") else "N/A",  
                "政策": s_v["manual"]["Policy"], 
                "護城河": s_v["manual"]["Moat"],
                "估值%": f"{weights['Valuation']:.0%}",
                "質量%": f"{weights['Quality']:.0%}",
                "成長%": f"{weights['Growth']:.0%}",
                "護城河%": f"{weights['MoatPolicy']:.0%}",
                "狀態": "✅ AI優化" if s_v.get("insight") else "⚪ 預設"  
            })
        else:
            failed_stocks.append(s)
    
    progress_bar.empty()
    progress_text.empty()
    
    if failed_stocks:
        st.warning(f"⚠️ 以下股票數據獲取失敗: {', '.join(failed_stocks)}")
    
    if compare_list:  
        df = pd.DataFrame(compare_list).sort_values("綜合分數", ascending=False)
        
        # 使用顏色標記 AI 優化狀態
        def highlight_rows(row):
            if row["狀態"] == "✅ AI優化":
                return ["background-color: #e8f5e9"] * len(row)
            return [""] * len(row)
        
        st.dataframe(
            df.style.apply(highlight_rows, axis=1),
            use_container_width=True, 
            hide_index=True
        )
        
        # 統計資訊
        ai_count = sum(1 for item in compare_list if item["狀態"] == "✅ AI優化")
        st.caption(f"📈 已完成 AI 優化: {ai_count}/{len(compare_list)} 支股票 | 數據獲取成功率: {len(compare_list)}/{len(SECTORS[selected_sector])}")
    else:
        st.error("❌ 無法載入任何產業數據")
        st.info("💡 建議：\n1. 點擊側邊欄「🔄 清除數據緩存」\n2. 刷新頁面\n3. 檢查側邊欄「🔧 調試選項」中的連線測試")
```

else:
st.error(f”❌ 無法取得 {selected_stock} 的股票數據”)
st.info(“💡 提示: 請檢查網路連線，或點擊側邊欄的「🔄 清除數據緩存」後重試”)
