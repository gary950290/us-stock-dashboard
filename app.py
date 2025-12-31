import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser
from urllib.parse import quote

# =========================
# 基本設定
# =========================
st.set_page_config(
    page_title="美股分析儀表板（RSS + 手動調整版）",
    layout="wide"
)
st.title("📊 美股分析儀表板（政策 & 護城河細緻化版）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"]
}

# =========================
# 護城河分數資料
# =========================
COMPANY_MOAT_DATA = {
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},
    "CRWD":{"retention":0.88,"switching":0.75,"patent":0.6,"network":0.8},
    "PANW":{"retention":0.85,"switching":0.7,"patent":0.65,"network":0.75},
    "ZS":{"retention":0.8,"switching":0.65,"patent":0.5,"network":0.7},
    "OKTA":{"retention":0.82,"switching":0.6,"patent":0.55,"network":0.65},
    "S":{"retention":0.78,"switching":0.55,"patent":0.5,"network":0.6},
    "AMD":{"retention":0.8,"switching":0.7,"patent":0.6,"network":0.7},
    "INTC":{"retention":0.75,"switching":0.65,"patent":0.7,"network":0.6},
    "TSM":{"retention":0.9,"switching":0.85,"patent":0.9,"network":0.8},
    "AVGO":{"retention":0.85,"switching":0.8,"patent":0.85,"network":0.75}
}
MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"],index=0)
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)
WEIGHTS = {
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1}
}

# =========================
# 工具函數
# =========================
def get_price(symbol):
    info=yf.Ticker(symbol).info
    return info.get("currentPrice"), info.get("regularMarketChangePercent")

def get_fundamentals(symbol):
    info=yf.Ticker(symbol).info
    data={
        "股價":info.get("currentPrice"),
        "PE":info.get("trailingPE"),
        "Forward PE":info.get("forwardPE"),
        "EPS":info.get("trailingEps"),
        "ROE":info.get("returnOnEquity"),
        "市值":info.get("marketCap"),
        "FCF":info.get("freeCashflow"),
        "Revenue_5Y_CAGR":info.get("revenueGrowth")
    }
    for k in data:
        if isinstance(data[k],float):
            data[k]=round(data[k],4)
    return pd.DataFrame(data.items(),columns=["指標","數值"])

def format_large_numbers(value):
    if isinstance(value,(int,float)) and value is not None:
        if value>=1e9:
            return f"{value/1e9:.2f} B"
        elif value>=1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def format_df(df,decimals=2):
    display_df=df.copy()
    float_cols=display_df.select_dtypes(include=["float","float64"]).columns
    display_df[float_cols]=display_df[float_cols].round(decimals)
    return display_df

def calculate_moat(symbol):
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data[k]*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

# =========================
# 半自動政策分數 (RSS + URL encode)
# =========================
POSITIVE_KEYWORDS = ["subsidy","grant","support","funding","incentive","government contract"]
NEGATIVE_KEYWORDS = ["restriction","ban","penalty","tax","fine","lawsuit"]

def get_policy_score_google_news(company, industry, max_results=10):
    query = f"{company} {industry}"
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    titles = [entry.title for entry in feed.entries[:max_results]]
    
    score = 0
    for t in titles:
        t_lower = t.lower()
        score += sum([1 for k in POSITIVE_KEYWORDS if k in t_lower])
        score -= sum([1 for k in NEGATIVE_KEYWORDS if k in t_lower])
    
    if len(titles) > 0:
        score_norm = max(min((score/len(titles)+1)/2*100,100),0)
    else:
        score_norm = 50
    return round(score_norm,2), len(titles)

# =========================
# 計算綜合分數
# =========================
def compute_scores(row,sector,manual_scores=None):
    PE_lower,PE_upper=15,50
    PE=row.get("PE")
    PE_score=max(0,min(100,(PE_upper-PE)/(PE_upper-PE_lower)*100)) if PE else 50
    ROE=row.get("ROE")
    ROE_score=min(max(ROE/0.3*100,0),100) if ROE else 50
    symbol=row["股票"]
    
    Policy_score, news_count = get_policy_score_google_news(symbol, sector)
    Moat_score = calculate_moat(symbol)
    growth=row.get("Revenue_5Y_CAGR")
    Growth_score=min(max(growth/0.3*100,0),100) if growth else 50
    
    if manual_scores and symbol in manual_scores:
        Policy_score = manual_scores[symbol].get("Policy_score",Policy_score)
        Moat_score = manual_scores[symbol].get("Moat_score",Moat_score)
        Growth_score = manual_scores[symbol].get("Growth_score",Growth_score)
    
    w=WEIGHTS[style]
    Total_score=round(PE_score*w["PE"]+ROE_score*w["ROE"]+Policy_score*w["Policy"]+
                      Moat_score*w["Moat"]+Growth_score*w["Growth"],2)
    
    return PE_score,ROE_score,Policy_score,Moat_score,Growth_score,Total_score,news_count

# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol=st.sidebar.text_input("輸入美股代碼","NVDA")
    st.subheader(f"📌 {symbol} 分析")
    price,change=get_price(symbol)
    if price:
        st.metric("即時股價",f"${price:.2f}",f"{change:.2f}%")
    funds_df=get_fundamentals(symbol)
    for col in ["FCF","市值"]:
        if col in funds_df["指標"].values:
            funds_df.loc[funds_df["指標"]==col,"數值"]=funds_df.loc[funds_df["指標"]==col,"數值"].apply(format_large_numbers)
    st.table(funds_df)
    
    policy_score, news_count = get_policy_score_google_news(symbol, "semiconductor")
    st.metric("政策分數", f"{policy_score}", f"新聞數量: {news_count}")
    st.metric("護城河分數", calculate_moat(symbol))

# =========================
# 產業共同比較 + 手動分數調整
# =========================
elif mode=="產業共同比較":
    sector=st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
    st.subheader(f"🏭 {sector} 產業比較")
    
    # 手動輸入分數
    st.sidebar.subheader("手動調整分數 (可選)")
    manual_scores = {}
    for symbol in SECTORS[sector]:
        Policy_default, _ = get_policy_score_google_news(symbol, sector)
        Moat_default = calculate_moat(symbol)
        Growth_default = 50
        st.sidebar.markdown(f"**{symbol} 調整**")
        manual_policy = st.sidebar.slider(f"{symbol} 政策分數", 0, 100, int(Policy_default))
        manual_moat = st.sidebar.slider(f"{symbol} 護城河分數", 0, 100, int(Moat_default))
        manual_growth = st.sidebar.slider(f"{symbol} 成長分數", 0, 100, int(Growth_default))
        manual_scores[symbol] = {
            "Policy_score": manual_policy,
            "Moat_score": manual_moat,
            "Growth_score": manual_growth
        }
    
    rows=[]
    for symbol in SECTORS[sector]:
        try:
            df=get_fundamentals(symbol)
            row={"股票":symbol}
            for _,r in df.iterrows():
                row[r["指標"]]=r["數值"]
            PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s,news_count=compute_scores(row,sector,manual_scores)
            row["PE_score"]=round(PE_s,2)
            row["ROE_score"]=round(ROE_s,2)
            row["Policy_score"]=round(Policy_s,2)
            row["Moat_score"]=round(Moat_s,2)
            row["Growth_score"]=round(Growth_s,2)
            row["綜合分數"]=round(Total_s,2)
            row["新聞數量"]=news_count
            row["手動調整"]= "Yes" if symbol in manual_scores else "No"
            for col in ["FCF","市值"]:
                if col in row:
                    row[col]=format_large_numbers(row[col])
            rows.append(row)
        except:
            pass
    if rows:
        result_df=pd.DataFrame(rows)
        result_df=format_df(result_df)
        result_df=result_df.sort_values("綜合分數",ascending=False)
        st.dataframe(result_df,use_container_width=True)

# =========================
# 評分公式說明
# =========================
with st.expander("📘 評分依據與公式"):
    st.markdown("""
    **各因子計算方式**：
    - **PE_score (估值)**：PE 越低越好，行業合理區間 15~50，線性映射 0~100
    - **ROE_score (盈利能力)**：ROE 越高越好，30% ROE 為滿分，線性映射 0~100
    - **Policy_score (政策)**：RSS 抓取新聞 + 手動調整
    - **Moat_score (護城河)**：續約率、轉換成本、專利、網路效應加權計算 0~100，可手動調整
    - **Growth_score (成長潛力)**：近五年營收 CAGR / 30%，線性映射 0~100，可手動調整
    - **綜合分數** = 加權總分，依投資風格調整權重
    """)
