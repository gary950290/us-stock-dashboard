import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="美股分析儀表板（機構級評分版）", layout="wide")
st.title("📊 美股分析儀表板（行業基準 × 現金流驗證 × 前瞻政策）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"],
    "NeoCloud": ["NBIS","IREN","CRWV","APLD"]
}

# =========================
# 護城河資料
# =========================
COMPANY_MOAT_DATA = {...}  # ← ⚠️【完全保留你原本那一整段，不動】

MOAT_WEIGHTS = {"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 投資風格權重（升級版）
# =========================
STYLE_WEIGHTS = {
    "穩健型": {"valuation":0.35,"roe":0.35,"growth":0.10,"moat":0.20},
    "平衡型": {"valuation":0.30,"roe":0.25,"growth":0.20,"moat":0.25},
    "成長型": {"valuation":0.20,"roe":0.20,"growth":0.35,"moat":0.25}
}

# =========================
# 側邊欄
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",list(STYLE_WEIGHTS.keys()),index=1)

policy_alpha = st.sidebar.slider(
    "2026 政策風險係數 (Policy Risk Alpha)",
    0.8, 1.2, 1.0, 0.05
)

# =========================
# 工具函數
# =========================
@st.cache_data(ttl=3600)
def get_info(symbol):
    return yf.Ticker(symbol).info

def format_large_numbers(v):
    if v is None: return None
    if v >= 1e9: return f"{v/1e9:.2f} B"
    if v >= 1e6: return f"{v/1e6:.2f} M"
    return round(v,2)

def calculate_moat(symbol):
    data = COMPANY_MOAT_DATA.get(symbol,{k:0.5 for k in MOAT_WEIGHTS})
    return round(sum(data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS)*100,2)

# =========================
# ⭐ 新一代評分引擎
# =========================
def valuation_score_relative(pe, sector_pe_avg):
    if not pe or not sector_pe_avg:
        return 50.0
    ratio = pe / sector_pe_avg
    if ratio <= 0.7: return 95
    if ratio <= 1.0: return 85 - (ratio-0.7)*30
    if ratio <= 1.3: return 65 - (ratio-1.0)*40
    return max(30, 50 - (ratio-1.3)*40)

def roe_quality_score(roe, fcf, mcap, net_debt, ebitda):
    if not roe or roe <= 0:
        return 30.0
    base = min(roe/0.30,1.0)*100
    fcf_adj = 1.0
    if fcf is not None and mcap:
        if fcf/mcap > 0.05: fcf_adj = 1.1
        elif fcf < 0: fcf_adj = 0.7
    debt_adj = 1.0
    if net_debt is not None and ebitda and ebitda > 0:
        if net_debt/ebitda > 4.5: debt_adj = 0.6
        elif net_debt/ebitda > 3.0: debt_adj = 0.8
    return round(min(base*fcf_adj*debt_adj,100),2)

def growth_score_from_peg(fwd_pe, growth):
    if not fwd_pe or not growth or growth <= 0:
        return 50.0
    peg = fwd_pe / growth
    if peg < 1.0: return 90
    if peg < 1.5: return 75
    if peg < 2.0: return 60
    return 45

def total_score(val, roe, growth, moat, style, alpha):
    w = STYLE_WEIGHTS[style]
    raw = val*w["valuation"] + roe*w["roe"] + growth*w["growth"] + moat*w["moat"]
    return round(min(raw*alpha,100),2)

# =========================
# 初始化 session_state（保留輸入）
# =========================
for sector in SECTORS.values():
    for s in sector:
        st.session_state.setdefault(f"{s}_policy",50)
        st.session_state.setdefault(f"{s}_growth",50)
        st.session_state.setdefault(f"{s}_moat",calculate_moat(s))

# =========================
# 單一股票
# =========================
if mode == "單一股票分析":
    symbol = st.sidebar.text_input("股票代碼","NVDA")
    info = get_info(symbol)

    st.subheader(symbol)
    st.metric("股價", f"${info.get('currentPrice'):.2f}")

    # 手動輸入
    st.subheader("手動評分")
    st.number_input("政策分數",0,100,key=f"{symbol}_policy")
    st.number_input("成長分數",0,100,key=f"{symbol}_growth")
    st.number_input("護城河分數",0,100,key=f"{symbol}_moat")

    sector = next((k for k,v in SECTORS.items() if symbol in v),None)
    peers = SECTORS.get(sector,[])
    sector_pes = [get_info(p).get("trailingPE") for p in peers if get_info(p).get("trailingPE")]
    sector_avg_pe = sum(sector_pes)/len(sector_pes) if sector_pes else None

    val = valuation_score_relative(info.get("trailingPE"), sector_avg_pe)
    roe = roe_quality_score(
        info.get("returnOnEquity"),
        info.get("freeCashflow"),
        info.get("marketCap"),
        info.get("netDebt"),
        info.get("ebitda")
    )
    growth = growth_score_from_peg(info.get("forwardPE"), info.get("earningsGrowth"))
    moat = st.session_state[f"{symbol}_moat"]

    total = total_score(val, roe, growth, moat, style, policy_alpha)

    st.metric("估值分數",val)
    st.metric("ROE 品質分數",roe)
    st.metric("成長分數",growth)
    st.metric("綜合分數",total)

# =========================
# 產業比較
# =========================
else:
    sector = st.sidebar.selectbox("產業",list(SECTORS.keys()))
    rows=[]
    infos={s:get_info(s) for s in SECTORS[sector]}
    sector_pes=[i.get("trailingPE") for i in infos.values() if i.get("trailingPE")]
    sector_avg_pe=sum(sector_pes)/len(sector_pes) if sector_pes else None

    for s,i in infos.items():
        val=valuation_score_relative(i.get("trailingPE"),sector_avg_pe)
        roe=roe_quality_score(i.get("returnOnEquity"),i.get("freeCashflow"),i.get("marketCap"),i.get("netDebt"),i.get("ebitda"))
        growth=growth_score_from_peg(i.get("forwardPE"),i.get("earningsGrowth"))
        moat=st.session_state[f"{s}_moat"]
        total=total_score(val,roe,growth,moat,style,policy_alpha)

        rows.append({
            "股票":s,
            "股價":i.get("currentPrice"),
            "PE":i.get("trailingPE"),
            "FCF":format_large_numbers(i.get("freeCashflow")),
            "估值分數":val,
            "ROE 分數":roe,
            "成長分數":growth,
            "護城河":moat,
            "綜合分數":total
        })

    df=pd.DataFrame(rows).sort_values("綜合分數",ascending=False)
    st.dataframe(df,use_container_width=True)
