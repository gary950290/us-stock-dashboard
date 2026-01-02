import streamlit as st
import pandas as pd
import yfinance as yf
from math import log, sqrt

# =========================
# 設定
# =========================
st.set_page_config(page_title="美股分析儀表板", layout="wide")
st.title("📊 美股分析儀表板（手動分數 + 行業動態PE/ROE）")

# =========================
# 產業股票池
# =========================
SECTORS = {
    "Mag7": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA"],
    "資安": ["CRWD","PANW","ZS","OKTA","FTNT","S"],
    "半導體": ["NVDA","AMD","INTC","TSM","AVGO"],
    "能源": ["TSLA","CEG","FLNC","TE","NEE","ENPH","EOSE","VST","PLUG","OKLO","SMR","BE","GEV"]
}

# =========================
# 護城河資料 - 增加其他產業的範例數據
# ==========================
# 數值 0.0 - 1.0 (1.0為最高)
COMPANY_MOAT_DATA = {
    # Mag7 (已存在)
    "AAPL":{"retention":0.95,"switching":0.9,"patent":0.8,"network":1.0},
    "MSFT":{"retention":0.92,"switching":0.85,"patent":0.7,"network":0.9},
    "GOOGL":{"retention":0.9,"switching":0.8,"patent":0.75,"network":0.95},
    "AMZN":{"retention":0.85,"switching":0.7,"patent":0.7,"network":0.9},
    "META":{"retention":0.8,"switching":0.6,"patent":0.6,"network":0.85},
    "NVDA":{"retention":0.9,"switching":0.8,"patent":0.95,"network":0.8},
    "TSLA":{"retention":0.85,"switching":0.6,"patent":0.7,"network":0.7},

    # 資安 (強調轉換成本、先發優勢)
    "CRWD":{"retention":0.88,"switching":0.95,"patent":0.65,"network":0.75},
    "PANW":{"retention":0.85,"switching":0.9,"patent":0.7,"network":0.7},
    "ZS":{"retention":0.78,"switching":0.88,"patent":0.6,"network":0.65},

    # 半導體 (強調專利、技術優勢)
    "AMD":{"retention":0.75,"switching":0.7,"patent":0.9,"network":0.6},
    "INTC":{"retention":0.8,"switching":0.75,"patent":0.92,"network":0.5},
    "TSM":{"retention":0.95,"switching":0.95,"patent":0.98,"network":0.9},
    "AVGO":{"retention":0.8,"switching":0.8,"patent":0.85,"network":0.7},

    # 能源 (強調政策/品牌，護城河相對較低)
    "NEE":{"retention":0.8,"switching":0.8,"patent":0.5,"network":0.5},
    "ENPH":{"retention":0.7,"switching":0.6,"patent":0.7,"network":0.4},
}

MOAT_WEIGHTS={"retention":0.4,"switching":0.3,"patent":0.2,"network":0.1}

# =========================
# 側邊欄設定
# =========================
st.sidebar.header("⚙️ 分析設定")
mode = st.sidebar.selectbox("選擇模式",["產業共同比較","單一股票分析"])
style = st.sidebar.selectbox("投資風格",["穩健型","成長型","平衡型"],index=2)
WEIGHTS = {
    "穩健型":{"PE":0.4,"ROE":0.3,"Policy":0.1,"Moat":0.2,"Growth":0.0},
    "成長型":{"PE":0.2,"ROE":0.2,"Policy":0.2,"Moat":0.1,"Growth":0.3},
    "平衡型":{"PE":0.3,"ROE":0.2,"Policy":0.2,"Moat":0.2,"Growth":0.1}
}

# =========================
# 快取工具函數
# =========================
@st.cache_data
def get_price(symbol):
    """獲取即時股價和漲跌幅"""
    info=yf.Ticker(symbol).info
    return info.get("currentPrice"), info.get("regularMarketChangePercent")

@st.cache_data
def get_fundamentals(symbol):
    """獲取基本財報數據"""
    info=yf.Ticker(symbol).info
    data={
        "股價":info.get("currentPrice"),
        "PE":info.get("trailingPE"),
        "Forward PE":info.get("forwardPE"), # 用於成長性評估
        "EPS":info.get("trailingEps"),
        "ROE":info.get("returnOnEquity"),
        "市值":info.get("marketCap"),
        "FCF":info.get("freeCashflow") # 用於政策和穩定性評估
    }
    return pd.DataFrame(data.items(),columns=["指標","數值"])

def get_sector_by_symbol(symbol):
    """根據代碼查找所屬產業"""
    for sector_name, stocks in SECTORS.items():
        if symbol in stocks:
            return sector_name
    return "未知"

def format_large_numbers(value):
    """格式化大數字為 B 或 M 顯示"""
    if isinstance(value,(int,float)) and value is not None:
        if value>=1e9:
            return f"{value/1e9:.2f} B"
        elif value>=1e6:
            return f"{value/1e6:.2f} M"
        else:
            return f"{value:.2f}"
    return value

def calculate_moat(symbol):
    """根據預設權重和公司數據計算護城河分數 (0-100)"""
    # 查找公司數據，如果沒有則使用平均值
    data=COMPANY_MOAT_DATA.get(symbol,{"retention":0.5,"switching":0.5,"patent":0.5,"network":0.5})
    score=sum([data.get(k,0.5)*MOAT_WEIGHTS[k] for k in MOAT_WEIGHTS])*100
    return round(score,2)

def calculate_sector_specific_growth_score(PE, FWD_PE, ROE, FCF_ratio, sector):
    """
    根據產業特性和財報數據，計算基礎成長分數 (0-100)
    FCF_ratio = FCF / MarketCap
    """
    base_score = 50
    
    # 成長性：通常看 FWD_PE/PE 比例 (低於1表示市場預期成長) 及 ROE
    pe_ratio = FWD_PE / PE if PE and FWD_PE and PE != 0 else 1.0

    if sector == "Mag7" or sector == "資安":
        # 成長/科技股：極度看重預期成長，高 ROE 加分
        growth_factor = 0
        if pe_ratio < 1.0 and pe_ratio > 0:
            # PE Ratio 越低，市場預期成長越高，分數越高 (100 - X * 50)
            growth_factor = (1 - pe_ratio) * 100 
        
        roe_boost = min(ROE * 5, 50) if ROE and ROE > 0 else 0
        
        base_score = max(50, 50 + growth_factor * 0.5 + roe_boost * 0.5)

    elif sector == "半導體":
        # 循環性產業：PE比值變化表示週期復甦/衰退
        cycle_boost = 0
        if pe_ratio < 0.8 and pe_ratio > 0: # FWD PE 顯著低於 Trailing PE，預期強勁復甦
            cycle_boost = 30
        
        base_score = max(0, min(100, 50 + cycle_boost))
        
    elif sector == "能源":
        # 價值/穩定型產業：成長性權重低，但仍以穩定 ROE 和估值改善為依據
        if ROE and ROE > 0.15: # 15% 以上 ROE 視為優異
            base_score += 10
        if pe_ratio < 0.9 and pe_ratio > 0: # 估值改善加分
             base_score += 10
    
    return round(min(100, base_score), 2)

def calculate_sector_specific_policy_score(PE, ROE, FCF_ratio, sector):
    """
    根據產業特性和財報數據，計算基礎政策分數 (0-100)
    FCF_ratio = FCF / MarketCap (FCF/市值比)
    """
    base_score = 50
    
    if sector == "Mag7":
        # Mag7：政策穩定性高，但反壟斷風險存在。注重 FCF 穩定性
        if FCF_ratio is not None and FCF_ratio > 0.03: # 3% 以上 FCF/市值視為極佳現金產生能力
            base_score += 15
        
    elif sector == "資安":
        # 資安：政策傾向於網路安全支出，因此穩定性高。
        base_score += 10 # 預設加分，反映行業趨勢
        
    elif sector == "半導體":
        # 半導體：受國家補貼/晶片法案影響大。
        # 這裡需要更細緻的判斷，但保持現有結構，給予行業性加分
        base_score += 10 

    elif sector == "能源":
        # 能源：極度受政府氣候/環保政策影響，FCF 至關重要。
        if FCF_ratio is not None and FCF_ratio > 0.05: # 高 FCF/市值表示現金流充裕，政策變動衝擊小
            base_score += 25
        elif FCF_ratio is not None and FCF_ratio < 0:
            base_score = 30 # 現金流為負，政策風險高
    
    return round(min(100, base_score), 2)


def compute_scores(row, manual_scores=None, sector_avg_pe=None, sector_avg_roe=None):
    """計算所有單項分數和綜合分數"""
    symbol = row["股票"]
    PE = row.get("PE")
    ROE = row.get("ROE")
    FCF = row.get("FCF")
    FWD_PE = row.get("Forward PE")
    MarketCap = row.get("市值")
    sector = get_sector_by_symbol(symbol)
    
    # 計算 FCF/市值比例 (用於政策/穩定性評估)
    FCF_ratio = FCF / MarketCap if FCF is not None and MarketCap is not None and MarketCap != 0 and MarketCap is not None else None

    # 1. 護城河分數 (僅根據COMPANY_MOAT_DATA和MOAT_WEIGHTS計算)
    Moat_score = calculate_moat(symbol)

    # 2. 成長/政策分數 (根據行業特性計算基礎分數)
    Policy_score_base = calculate_sector_specific_policy_score(PE, ROE, FCF_ratio, sector)
    Growth_score_base = calculate_sector_specific_growth_score(PE, FWD_PE, ROE, FCF_ratio, sector)

    # 3. PE 分數 (行業動態比較)
    PE_score = 50
    if PE is not None and PE > 0 and sector_avg_pe is not None and sector_avg_pe > 0:
        # PE 越低越好，分數範圍 0-100。相對行業平均而言，低於平均分數高。
        PE_ratio = sector_avg_pe / PE if PE != 0 else 0
        PE_score = min(100, PE_ratio * 50) 
    
    # 4. ROE 分數 (行業動態比較 + FCF 懲罰)
    ROE_score = 50
    if ROE is not None and ROE > 0 and sector_avg_roe is not None and sector_avg_roe > 0:
        # ROE 越高越好，分數範圍 0-100。相對於行業平均，高於平均分數高。
        ROE_ratio = ROE / sector_avg_roe if sector_avg_roe != 0 else 0
        ROE_score = min(100, ROE_ratio * 50)
    
    # FCF < 0 則對 ROE 分數進行懲罰 (財務穩定性風險)
    if FCF is not None and isinstance(FCF,(int,float)) and FCF < 0:
        ROE_score *= 0.8
        
    # 5. 應用手動分數覆蓋 (如果存在)
    manual_data = manual_scores.get(symbol, {}) if manual_scores else {}
    Policy_score = manual_data.get("Policy_score", Policy_score_base)
    Moat_score = manual_data.get("Moat_score", Moat_score) # Moat 分數也允許手動覆蓋
    Growth_score = manual_data.get("Growth_score", Growth_score_base)
    
    # 6. 計算綜合分數
    w=WEIGHTS[style]
    Total_score=round(PE_score*w["PE"]+ROE_score*w["ROE"]+Policy_score*w["Policy"]+
                      Moat_score*w["Moat"]+Growth_score*w["Growth"],2)
    
    return PE_score, ROE_score, Policy_score, Moat_score, Growth_score, Total_score

# =========================
# 初始化 session_state
# =========================
for sector_companies in SECTORS.values():
    for symbol in sector_companies:
        # 首次運行時，用基礎計算值填寫 Session State
        if f"{symbol}_policy" not in st.session_state:
            st.session_state[f"{symbol}_policy"] = 50 
        if f"{symbol}_moat" not in st.session_state:
            st.session_state[f"{symbol}_moat"] = calculate_moat(symbol)
        if f"{symbol}_growth" not in st.session_state:
            st.session_state[f"{symbol}_growth"] = 50
        
        # 確保 MOAT 分數在每次會話開始時都使用 calculate_moat 的值
        st.session_state[f"{symbol}_moat_base"] = calculate_moat(symbol)


# =========================
# 單一股票分析
# =========================
if mode=="單一股票分析":
    symbol=st.sidebar.text_input("輸入美股代碼","NVDA")
    
    sector_found = get_sector_by_symbol(symbol)
    st.subheader(f"📌 {symbol} 分析 ({sector_found} 產業)")
    
    price,change="N/A","N/A"
    try:
        price,change=get_price(symbol)
        if price != "N/A":
            st.metric("即時股價",f"${price:.2f}",f"{change:.2f}%")
    except Exception as e:
        st.error(f"無法抓取即時股價：{e}")

    funds_df=pd.DataFrame()
    PE_val=ROE_val=FCF_val=FWD_PE_val=MarketCap_val=None
    try:
        funds_df=get_fundamentals(symbol)
        # 提取數值
        df_dict = funds_df.set_index('指標')['數值'].to_dict()
        PE_val = df_dict.get("PE")
        ROE_val = df_dict.get("ROE")
        FCF_val = df_dict.get("FCF")
        FWD_PE_val = df_dict.get("Forward PE")
        MarketCap_val = df_dict.get("市值")

        # 格式化顯示
        for col in ["FCF","市值"]:
            if col in funds_df["指標"].values:
                funds_df.loc[funds_df["指標"]==col,"數值"]=funds_df.loc[funds_df["指標"]==col,"數值"].apply(format_large_numbers)
    except Exception as e:
        st.warning(f"無法抓取財報數據：{e}")
        
    st.table(funds_df)
    
    st.subheader("手動輸入分數 (0-100)")

    # 計算行業平均 (用於 PE/ROE 動態分數)
    sector_avg_pe,sector_avg_roe=None,None
    if sector_found != "未知":
        pe_list=[]
        roe_list=[]
        for s in SECTORS[sector_found]:
            try:
                df=get_fundamentals(s)
                pe_val_s=df.loc[df["指標"]=="PE","數值"].values
                roe_val_s=df.loc[df["指標"]=="ROE","數值"].values
                if len(pe_val_s)>0 and isinstance(pe_val_s[0], (int, float)): pe_list.append(pe_val_s[0])
                if len(roe_val_s)>0 and isinstance(roe_val_s[0], (int, float)): roe_list.append(roe_val_s[0])
            except:
                pass
        if pe_list: sector_avg_pe=sum(pe_list)/len(pe_list)
        if roe_list: sector_avg_roe=sum(roe_list)/len(roe_list)
        
        st.info(f"💡 {sector_found} 產業平均 PE: {sector_avg_pe:.2f}, ROE: {sector_avg_roe:.2%}")

    # 必須傳遞所有數據點給 compute_scores，即使部分為 None
    row_data = {
        "股票":symbol, 
        "PE":PE_val, 
        "ROE":ROE_val, 
        "FCF":FCF_val, 
        "Forward PE":FWD_PE_val, 
        "市值":MarketCap_val
    }
    
    # 執行一次分數計算，以獲取基礎分數
    PE_s_base, ROE_s_base, Policy_s_base, Moat_s_base, Growth_s_base, Total_s_base = compute_scores(
        row_data, 
        manual_scores={}, # 傳入空字典以計算基礎分數
        sector_avg_pe=sector_avg_pe, 
        sector_avg_roe=sector_avg_roe
    )
    
    # --- 修正: 加入 step=1.0 確保數字輸入為浮點數 ---
    manual_policy = st.number_input(
        f"政策分數 (行業基礎: {Policy_s_base:.2f})", 
        0, 100, 
        value=st.session_state.get(f"{symbol}_policy", Policy_s_base),
        key=f"{symbol}_policy",
        step=1.0 
    )
    manual_moat = st.number_input(
        f"護城河分數 (計算基礎: {Moat_s_base:.2f})", 
        0, 100, 
        value=st.session_state.get(f"{symbol}_moat", Moat_s_base),
        key=f"{symbol}_moat",
        step=1.0
    )
    manual_growth = st.number_input(
        f"成長分數 (行業基礎: {Growth_s_base:.2f})", 
        0, 100, 
        value=st.session_state.get(f"{symbol}_growth", Growth_s_base),
        key=f"{symbol}_growth",
        step=1.0
    )
    # --- 修正結束 ---
    
    # 最終計算
    PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
        row_data,
        manual_scores={symbol:{
            "Policy_score":manual_policy,
            "Moat_score":manual_moat,
            "Growth_score":manual_growth
        }},
        sector_avg_pe=sector_avg_pe,
        sector_avg_roe=sector_avg_roe
    )
    
    st.subheader("分析結果")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("PE_score", f"{PE_s:.2f}")
    col2.metric("ROE_score", f"{ROE_s:.2f}")
    col3.metric("政策分數", f"{Policy_s:.2f}")
    col4.metric("護城河分數", f"{Moat_s:.2f}")
    col5.metric("成長分數", f"{Growth_s:.2f}")
    col6.metric(f"綜合分數 ({style})", f"{Total_s:.2f}")

# =========================
# 產業共同比較
# =========================
elif mode=="產業共同比較":
    sector=st.sidebar.selectbox("選擇產業",list(SECTORS.keys()),index=0)
    st.subheader(f"🏭 {sector} 產業比較 - 投資風格：{style}")
    
    st.sidebar.markdown("### 手動分數輸入")
    
    manual_scores = {}
    
    # 第一次循環：獲取/設定手動分數到 session_state
    for symbol in SECTORS[sector]:
        # 獲取基礎分數
        Moat_s_base = st.session_state.get(f"{symbol}_moat_base", calculate_moat(symbol))

        # --- 修正: 加入 step=1.0 確保數字輸入為浮點數 ---
        manual_policy = st.sidebar.number_input(
            f"[{symbol}] 政策分數", 
            0, 100, 
            value=st.session_state.get(f"{symbol}_policy", 50), 
            key=f"sidebar_{symbol}_policy",
            step=1.0
        )
        manual_moat = st.sidebar.number_input(
            f"[{symbol}] 護城河分數 (基礎: {Moat_s_base:.2f})", 
            0, 100, 
            value=st.session_state.get(f"{symbol}_moat", Moat_s_base), 
            key=f"sidebar_{symbol}_moat",
            step=1.0
        )
        manual_growth = st.sidebar.number_input(
            f"[{symbol}] 成長分數", 
            0, 100, 
            value=st.session_state.get(f"{symbol}_growth", 50), 
            key=f"sidebar_{symbol}_growth",
            step=1.0
        )
        # --- 修正結束 ---
        
        # 更新 session state
        st.session_state[f"{symbol}_policy"] = manual_policy
        st.session_state[f"{symbol}_moat"] = manual_moat
        st.session_state[f"{symbol}_growth"] = manual_growth

        manual_scores[symbol] = {
            "Policy_score": manual_policy,
            "Moat_score": manual_moat,
            "Growth_score": manual_growth
        }
    
    # 計算行業平均 PE/ROE
    pe_list=[]
    roe_list=[]
    all_fundamentals = {}
    
    for s in SECTORS[sector]:
        try:
            df=get_fundamentals(s)
            df_dict = df.set_index('指標')['數值'].to_dict()
            all_fundamentals[s] = df_dict
            
            pe_val=df_dict.get("PE")
            roe_val=df_dict.get("ROE")
            
            if pe_val is not None and isinstance(pe_val, (int, float)): pe_list.append(pe_val)
            if roe_val is not None and isinstance(roe_val, (int, float)): roe_list.append(roe_val)
        except:
            pass
            
    sector_avg_pe=sum(pe_list)/len(pe_list) if pe_list else None
    sector_avg_roe=sum(roe_list)/len(roe_list) if roe_list else None
    
    if sector_avg_pe and sector_avg_roe:
        st.info(f"本產業平均 PE: {sector_avg_pe:.2f}, ROE: {sector_avg_roe:.2%}")
    
    rows=[]
    for symbol in SECTORS[sector]:
        try:
            row={"股票":symbol}
            row.update(all_fundamentals.get(symbol, {}))

            PE_s,ROE_s,Policy_s,Moat_s,Growth_s,Total_s = compute_scores(
                row, manual_scores, sector_avg_pe, sector_avg_roe
            )
            
            row["PE_score"]=round(PE_s,2)
            row["ROE_score"]=round(ROE_s,2)
            row["Policy_score"]=round(Policy_s,2)
            row["Moat_score"]=round(Moat_s,2)
            row["Growth_score"]=round(Growth_s,2)
            row["綜合分數"]=round(Total_s,2)
            
            # 格式化顯示數據
            for col in ["FCF","市值","股價"]:
                if col in row:
                    row[col]=format_large_numbers(row[col])
            rows.append(row)
        except Exception as e:
            pass
    
    if rows:
        result_df=pd.DataFrame(rows)
        # 移除 Forward PE 和 EPS（表格會太寬）
        columns_to_show = ["股票","股價","PE","Forward PE","ROE","FCF","市值","PE_score","ROE_score","Policy_score","Moat_score","Growth_score","綜合分數"]
        
        # 過濾掉不存在的列
        final_cols = [col for col in columns_to_show if col in result_df.columns]
        
        result_df=result_df.sort_values("綜合分數",ascending=False).round(2)
        st.dataframe(result_df[final_cols],use_container_width=True)
    else:
        st.warning("無法加載所有股票數據，請檢查代碼或網路連接。")

