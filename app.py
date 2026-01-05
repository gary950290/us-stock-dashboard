import streamlit as st  
import pandas as pd  
import yfinance as yf  
import time  
import requests  
import json  
import os

# =========================

# 0. Data Persistence Config

# =========================

VAULT_FILE = “investment_vault_2026.json”

def save_vault():  
with open(VAULT_FILE, “w”, encoding=“utf-8”) as f:  
json.dump(st.session_state.stock_vault, f, ensure_ascii=False, indent=4)

def load_vault():  
if os.path.exists(VAULT_FILE):  
try:  
with open(VAULT_FILE, “r”, encoding=“utf-8”) as f:  
return json.load(f)  
except:  
return {}  
return {}

# =========================

# 1. OpenRouter Config

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
st.error(“Error: OPENROUTER_API_KEY not found in secrets”)  
st.stop()

# =========================

# 2. Core Config

# =========================

st.set_page_config(page_title=“2026 US Stock Analysis System”, layout=“wide”)

SECTORS = {  
“Mag7”: [“AAPL”,“MSFT”,“GOOGL”,“AMZN”,“META”,“NVDA”,“TSLA”],  
“Cybersecurity”: [“CRWD”,“PANW”,“ZS”,“OKTA”,“FTNT”,“S”],  
“Semiconductor”: [“NVDA”,“AMD”,“INTC”,“TSM”,“AVGO”],  
“Energy”: [“TSLA”,“CEG”,“FLNC”,“TE”,“NEE”,“ENPH”,“EOSE”,“VST”,“PLUG”,“OKLO”,“SMR”,“BE”,“GEV”],  
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

# 3. Utility Functions

# =========================

@st.cache_data(ttl=300)  
def get_stock_data(symbol):  
try:  
ticker = yf.Ticker(symbol)  
return ticker.info  
except:
return None

def call_openrouter(prompt, status, max_retries=3):  
headers = {
“Authorization”: f”Bearer {OR_API_KEY}”,
“HTTP-Referer”: “http://localhost:8501”,
“Content-Type”: “application/json”
}

```
for model in OR_MODELS:  
    for attempt in range(max_retries):
        try:  
            status.write(f"AI Model: {model} (Attempt {attempt+1}/{max_retries})")  
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
                status.write(f"Success with {model}")
                return result
            else:
                status.write(f"HTTP {res.status_code}: {res.text[:100]}")
                
        except json.JSONDecodeError as e:
            status.write(f"JSON parse error: {str(e)[:50]}")
        except requests.Timeout:
            status.write("Request timeout, retrying...")
        except Exception as e:
            status.write(f"Error: {str(e)[:50]}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
            
return None  
```

def run_ai_analysis(symbol, sector, status):  
info = get_stock_data(symbol)  
if not info:
status.write(f”Failed to get data for {symbol}”)
return False

```
if symbol not in st.session_state.stock_vault:  
    st.session_state.stock_vault[symbol] = {
        "manual": {"Policy": 50, "Moat": 50}, 
        "weights": DEFAULT_WEIGHTS.copy(), 
        "insight": None
    }  
  
prompt = f"""Analyze {symbol} ({sector}).
```

Data: PE={info.get(‘forwardPE’, ‘N/A’)}, ROE={info.get(‘returnOnEquity’, ‘N/A’)}, Revenue Growth={info.get(‘revenueGrowth’, ‘N/A’)}.
Adjust weights (must sum to 1.0).

Return JSON format:
{{
“sentiment”: “bullish/neutral/bearish”,
“summary”: “one sentence investment thesis”,
“suggested_weights”: {{
“Valuation”: 0.25,
“Quality”: 0.25,
“Growth”: 0.30,
“MoatPolicy”: 0.20
}},
“reason”: “explanation for weight adjustment”
}}”””

```
insight = call_openrouter(prompt, status)  
if insight and "suggested_weights" in insight:  
    weights = insight["suggested_weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        status.write(f"{symbol}: Weight sum={total:.2f}, normalizing")
        insight["suggested_weights"] = {k: v/total for k, v in weights.items()}
    
    st.session_state.stock_vault[symbol]["weights"] = insight["suggested_weights"]  
    st.session_state.stock_vault[symbol]["insight"] = insight  
    save_vault()
    status.write(f"{symbol}: AI analysis complete and saved")
    return True
else:
    status.write(f"{symbol}: AI analysis failed, keeping default weights")
    return False  
```

# =========================

# 4. UI

# =========================

st.title(“2026 Professional US Stock Analysis System”)

selected_sector = st.sidebar.selectbox(“Select Sector”, list(SECTORS.keys()))  
selected_stock = st.sidebar.selectbox(“Select Stock”, SECTORS[selected_sector])

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

st.sidebar.subheader(“Manual Scoring”)  
vault_m = st.session_state.stock_vault[selected_stock][“manual”]  
st.sidebar.slider(“Policy Benefit”, 0, 100, value=vault_m[“Policy”], key=f”{selected_stock}_p”, on_change=sync_vault)  
st.sidebar.slider(“Moat Strength”, 0, 100, value=vault_m[“Moat”], key=f”{selected_stock}_m”, on_change=sync_vault)

col_b1, col_b2 = st.sidebar.columns(2)  
if col_b1.button(“AI Analyze Single”):  
with st.status(f”Analyzing {selected_stock}…”, expanded=True) as status:  
if run_ai_analysis(selected_stock, selected_sector, status):  
status.update(label=“Analysis Complete”, state=“complete”)  
else:
status.update(label=“Analysis Issue”, state=“error”)
time.sleep(1)
st.rerun()

if col_b2.button(“Analyze All Sector”):  
with st.status(f”Processing {selected_sector} ({len(SECTORS[selected_sector])} stocks)…”, expanded=True) as status:  
success_count = 0
fail_count = 0
for idx, s in enumerate(SECTORS[selected_sector], 1):  
status.write(f”[{idx}/{len(SECTORS[selected_sector])}] Processing {s}…”)  
if run_ai_analysis(s, selected_sector, status):
success_count += 1
else:
fail_count += 1
time.sleep(1)

```
    status.update(
        label=f"Complete! Success: {success_count} | Failed: {fail_count}", 
        state="complete" if fail_count == 0 else "error"
    )
    time.sleep(2)
    st.rerun()  
```

# =========================

# 5. Results Display

# =========================

info = get_stock_data(selected_stock)  
if info:  
s_data = st.session_state.stock_vault[selected_stock]  
total_score = calculate_score(info, s_data[“weights”], s_data[“manual”])

```
if s_data["insight"]:  
    ins = s_data["insight"]  
    st.info(f"### AI Insight ({ins['sentiment']}): {ins['summary']}\n**Weight Adjustment Reason**: {ins['reason']}")  

c1, c2, c3 = st.columns(3)  
c1.metric("Overall Score", total_score)  
c2.metric("Forward PE", info.get("forwardPE", "N/A"))  
c3.metric("Status", "AI Optimized" if s_data["insight"] else "Default Mode")  

with st.expander("View Current Weights"):
    weights_df = pd.DataFrame([
        {"Dimension": k, "Weight": f"{v:.1%}", "Value": v} 
        for k, v in s_data["weights"].items()
    ])
    st.dataframe(weights_df, use_container_width=True, hide_index=True)

with st.expander("Sector Comparison (with AI Weights)", expanded=True):  
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
            weights = s_v["weights"]
            
            compare_list.append({  
                "Stock": s, 
                "Score": s_total,   
                "Fwd PE": s_info.get("forwardPE", "N/A"),  
                "Policy": s_v["manual"]["Policy"], 
                "Moat": s_v["manual"]["Moat"],
                "Val%": f"{weights['Valuation']:.0%}",
                "Qual%": f"{weights['Quality']:.0%}",
                "Growth%": f"{weights['Growth']:.0%}",
                "Moat%": f"{weights['MoatPolicy']:.0%}",
                "Status": "AI" if s_v.get("insight") else "Default"  
            })  
    
    if compare_list:  
        df = pd.DataFrame(compare_list).sort_values("Score", ascending=False)
        
        def highlight_ai_optimized(row):
            if row['Status'] == 'AI':
                return ['background-color: #e8f5e9'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            df.style.apply(highlight_ai_optimized, axis=1),
            use_container_width=True,
            hide_index=True
        )
        
        ai_count = sum(1 for item in compare_list if item['Status'] == 'AI')
        st.caption(f"AI Optimized: {ai_count}/{len(compare_list)} stocks")
```
