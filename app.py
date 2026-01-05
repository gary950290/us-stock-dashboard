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

# 1. OpenRouter 配置 (2026 免費模型)

# =========================

OR_MODELS = [  
“google/gemini-2.5-flash-preview-09-2025:free”,  
“deepseek/deepseek-r1:free”,  
“qwen/qwen3-coder:free”,  
“openrouter/auto”  
]

try:  
OR_API_KEY = st.secrets[“OPENROUTER_API_KEY”]  
except:  
st.error(“❌ 找不到 OPENROUTER_API_KEY。請在 Streamlit Secrets 中設定。”)  
st.stop()

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

# 優先從檔案讀取舊有數據

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

# 3. 工具函數 (改進版)

# =========================

@st.cache_data(ttl=300)  
def get_stock_data(symbol):  
try:  
ticker = yf.Ticker(symbol)  
return ticker.info  
except: return None

def call_openrouter(prompt, status, max_retries=3):  
“”“改進版：增加重試機制和詳細錯誤日誌”””
headers = {
“Authorization”: f”Bearer {OR_API_KEY}”,
“HTTP-Referer”: “http://localhost:8501”,
“Content-Type”: “application/json”
}

```
for model in OR_MODELS:  
    for attempt in range(max_retries):
        try:  
            status.write(f"🤖 模型: {model} (嘗試 {attempt+1}/{max_retries})...")  
            payload = {
                "model": model, 
                "messages": [{"role": "user", "content": prompt}], 
                "response_format": {"type": "json_object"}
            }
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions", 
                headers=headers, 
                data=json.dumps(payload), 
                timeout=30
            )
            
            if res.status_code == 200:  
                result = json.loads(res.json()['choices'][0]['message']['content'])
                status.write(f"✅ 成功使用 {model}")
                return result
            else:
                status.write(f"⚠️ HTTP {res.status_code}: {res.text[:100]}")
                
        except json.JSONDecodeError as e:
            status.write(f"⚠️ JSON 解析失敗: {str(e)[:50]}")
        except requests.Timeout:
            status.write(f"⏱️ 請求超時，重試中...")
        except Exception as e:
            status.write(f"❌ 錯誤: {str(e)[:50]}")
        
        if attempt < max_retries - 1:
            time.sleep(2)  # 重試前等待2秒
            
return None  
```

def run_ai_analysis(symbol, sector, status):  
“”“改進版：增強錯誤處理和狀態反饋”””
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
  
prompt = f"""分析 {symbol} ({sector})。
```

數據: PE={info.get(‘forwardPE’, ‘N/A’)}, ROE={info.get(‘returnOnEquity’, ‘N/A’)}, 營收增長={info.get(‘revenueGrowth’, ‘N/A’)}。
請根據該股票特性微調權重(四個權重總和必須=1.0)。

回傳JSON格式(嚴格遵守):
{{
“sentiment”: “看多/中性/看空”,
“summary”: “一句話總結投資觀點”,
“suggested_weights”: {{
“Valuation”: 0.25,
“Quality”: 0.25,
“Growth”: 0.30,
“MoatPolicy”: 0.20
}},
“reason”: “調整權重的具體原因”
}}”””

```
insight = call_openrouter(prompt, status)  
if insight and "suggested_weights" in insight:  
    # 驗證權重總和
    weights = insight["suggested_weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:  # 容許1%誤差
        status.write(f"⚠️ {symbol}: 權重總和={total:.2f}，自動標準化")
        # 標準化權重
        insight["suggested_weights"] = {k: v/total for k, v in weights.items()}
    
    st.session_state.stock_vault[symbol]["weights"] = insight["suggested_weights"]  
    st.session_state.stock_vault[symbol]["insight"] = insight  
    save_vault()
    status.write(f"✅ {symbol}: AI分析完成並已存檔")
    return True
else:
    status.write(f"❌ {symbol}: AI分析失敗，保持預設權重")
    return False  
```

# =========================

# 4. UI 與 持久化邏輯

# =========================

st.title(“🏛️ 2026 專業美股投資評比系統”)

selected_sector = st.sidebar.selectbox(“選擇產業”, list(SECTORS.keys()))  
selected_stock = st.sidebar.selectbox(“選擇股票”, SECTORS[selected_sector])

# 精準初始化

if selected_stock not in st.session_state.stock_vault:  
st.session_state.stock_vault[selected_stock] = {  
“manual”: {“Policy”: 50, “Moat”: 50},  
“weights”: DEFAULT_WEIGHTS.copy(),  
“insight”: None  
}

# 手動評分同步並存檔

def sync_vault():  
st.session_state.stock_vault[selected_stock][“manual”][“Policy”] = st.session_state[f”{selected_stock}_p”]  
st.session_state.stock_vault[selected_stock][“manual”][“Moat”] = st.session_state[f”{selected_stock}_m”]  
save_vault()

st.sidebar.subheader(“✏️ 2026 手動評分”)  
vault_m = st.session_state.stock_vault[selected_stock][“manual”]  
st.sidebar.slider(“政策受益度”, 0, 100, value=vault_m[“Policy”], key=f”{selected_stock}_p”, on_change=sync_vault)  
st.sidebar.slider(“護城河粘性”, 0, 100, value=vault_m[“Moat”], key=f”{selected_stock}_m”, on_change=sync_vault)

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
with st.status(f”處理 {selected_sector} ({len(SECTORS[selected_sector])}支股票)…”, expanded=True) as status:  
success_count = 0
fail_count = 0
for idx, s in enumerate(SECTORS[selected_sector], 1):  
status.write(f”📊 [{idx}/{len(SECTORS[selected_sector])}] 處理 {s}…”)  
if run_ai_analysis(s, selected_sector, status):
success_count += 1
else:
fail_count += 1
time.sleep(1)  # 避免API限流

```
    status.update(
        label=f"✅ 完成！成功: {success_count} | 失敗: {fail_count}", 
        state="complete" if fail_count == 0 else "error"
    )
    time.sleep(2)
    st.rerun()  
```

# =========================

# 5. 結果呈現

# =========================

info = get_stock_data(selected_stock)  
if info:  
s_data = st.session_state.stock_vault[selected_stock]  
total_score = calculate_score(info, s_data[“weights”], s_data[“manual”])

```
if s_data["insight"]:  
    ins = s_data["insight"]  
    st.info(f"### AI 洞察 ({ins['sentiment']}): {ins['summary']}\n**權重調整理由**: {ins['reason']}")  

c1, c2, c3 = st.columns(3)  
c1.metric("🎯 綜合評分", total_score)  
c2.metric("前瞻 PE", info.get("forwardPE", "N/A"))  
c3.metric("狀態", "AI 已優化" if s_data["insight"] else "預設模式")  

# 顯示當前權重
with st.expander("⚖️ 查看當前評分權重"):
    weights_df = pd.DataFrame([
        {"維度": k, "權重": f"{v:.1%}", "數值": v} 
        for k, v in s_data["weights"].items()
    ])
    st.dataframe(weights_df, use_container_width=True, hide_index=True)

# 改進版產業橫向比較
with st.expander("🏭 查看產業橫向排序 (包含AI權重)", expanded=True):  
    compare_list = []  
    for s in SECTORS[selected_sector]:  
        s_info = get_stock_data(s)  
        s_v = st.session_state.stock_vault.get(s, {
            "manual": {"Policy": 50, "Moat": 50}, 
            "weights": DEFAULT_WEIGHTS.copy(),
            "insight": None
        })  
        if s_info:  
            s_total = calculate_score(s_info, s_v["weights"], s_v["manual"])  
            
            # 取得權重（顯示為百分比）
            weights = s_v["weights"]
            
            compare_list.append({  
                "股票": s, 
                "綜合分數": s_total,   
                "前瞻PE": s_info.get("forwardPE", "N/A"),  
                "政策": s_v["manual"]["Policy"], 
                "護城河": s_v["manual"]["Moat"],
                "估值權重": f"{weights['Valuation']:.0%}",
                "質量權重": f"{weights['Quality']:.0%}",
                "成長權重": f"{weights['Growth']:.0%}",
                "護城河權重": f"{weights['MoatPolicy']:.0%}",
                "狀態": "✅ AI優化" if s_v.get("insight") else "⚪ 預設"  
            })  
    
    if compare_list:  
        df = pd.DataFrame(compare_list).sort_values("綜合分數", ascending=False)
        
        # 使用顏色標記AI優化狀態
        def highlight_ai_optimized(row):
            if row['狀態'] == '✅ AI優化':
                return ['background-color: #e8f5e9'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            df.style.apply(highlight_ai_optimized, axis=1),
            use_container_width=True,
            hide_index=True
        )
        
        # 統計資訊
        ai_count = sum(1 for item in compare_list if item['狀態'] == '✅ AI優化')
        st.caption(f"📊 已完成 AI 優化: {ai_count}/{len(compare_list)} 支股票")
```
