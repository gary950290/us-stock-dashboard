# app.py
import streamlit as st
import yfinance as yf
import time
import random
import pandas as pd
import json
import os
from tempfile import NamedTemporaryFile

# -------------------------
# 設定：儲存檔案名稱（持久化）
# -------------------------
VAULT_FILE = "investment_vault_2026.json"

# -------------------------
# 檔案讀寫（原子寫入）
# -------------------------
def load_vault():
    if not os.path.exists(VAULT_FILE):
        # 初始範例結構
        data = {
            "sectors": {
                "科技股": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
                "金融股": ["JPM", "BAC", "WFC", "GS", "C"],
                "能源股": ["XOM", "CVX", "COP", "SLB", "EOG"],
                "醫療股": ["JNJ", "UNH", "PFE", "ABBV", "TMO"]
            },
            "user_scores": {}  # 格式: {"AAPL": 7.5, ...}
        }
        save_vault(data)
        return data
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 保險回退
        return {"sectors": {}, "user_scores": {}}

def save_vault(data):
    # 原子寫入以避免檔案損壞
    tmp = NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=".")
    try:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        tmp.close()
        os.replace(tmp.name, VAULT_FILE)
    finally:
        if os.path.exists(tmp.name):
            try:
                os.remove(tmp.name)
            except Exception:
                pass

# -------------------------
# yfinance 抓取（含重試、延遲、快取）
# -------------------------
@st.cache_data(ttl=300)
def get_stock_info(symbol: str):
    """
    嘗試抓取 ticker.info，包含簡單重試與隨機 delay。
    回傳 dict 或 None。
    """
    max_retries = 3
    base_delay = 2
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(0.4, 0.8))
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            # 基本判斷：需要有 symbol 或 shortName 才算有效
            if info and (info.get("symbol") or info.get("shortName") or info.get("longName")):
                # 強制放入 symbol 欄位以便後續一致性
                info["symbol"] = info.get("symbol", symbol)
                return info
            else:
                # 若空，稍等並重試
                time.sleep(base_delay * (attempt + 1))
        except Exception as e:
            # 若 Rate limiting，延長等待
            err = str(e)
            if "429" in err or "Rate limit" in err:
                time.sleep(base_delay * (attempt + 1))
                continue
            else:
                # 不同錯誤就跳出
                st.error(f"抓取 {symbol} 發生錯誤：{err[:200]}")
                break
    return None

# -------------------------
# 批次抓取（包含進度）
# -------------------------
def batch_fetch(symbols):
    all_infos = {}
    failed = []
    total = len(symbols)
    progress = st.progress(0)
    status = st.empty()
    for i, s in enumerate(symbols):
        status.text(f"抓取 {s} ({i+1}/{total})...")
        info = get_stock_info(s)
        if info:
            all_infos[s] = info
        else:
            failed.append(s)
        progress.progress((i+1)/total)
    status.empty()
    progress.empty()
    return all_infos, failed

# -------------------------
# 內建簡易 "AI" 分析 (rule-based)
# 目的：快速產生可讀的分析與綜合評分，供 UI 顯示
# -------------------------
def compute_combined_score(info: dict, user_score: float | None):
    """
    根據 available metrics 計算一個 0-100 的合成分數（越高越好）。
    欄位權重（可調）：
        - user_score (人工評分): 30%
        - forwardPE: 20% (PE 低為好 -> 反向)
        - returnOnEquity: 25% (越高越好)
        - revenueGrowth: 15% (越高越好)
        - marketCap: 10% (越大代表流動性 & 大型公司穩定)
    注意：缺值會自動降權處理。
    """
    # 權重
    w_user = 0.30
    w_pe = 0.20
    w_roe = 0.25
    w_rev = 0.15
    w_mc = 0.10

    # user score: 假設輸入 0-10，normalize -> 0-100
    us = None
    if user_score is not None:
        try:
            us = max(0.0, min(10.0, float(user_score))) * 10.0
        except:
            us = None

    # forwardPE: 越小越好；我們把合理範圍 5 - 100 映射到 100 - 0
    pe = info.get("forwardPE") or info.get("trailingPE") or None
    pe_score = None
    if pe and isinstance(pe, (int, float)) and pe > 0:
        # clamp
        p = float(pe)
        p = max(5.0, min(200.0, p))
        pe_score = (1.0 - (p - 5.0) / (200.0 - 5.0)) * 100.0

    # ROE: 期望 0% - 60% 映射 0-100
    roe = info.get("returnOnEquity")
    roe_score = None
    if roe and isinstance(roe, (int, float)):
        r = max(-0.5, min(0.6, float(roe)))  # -50% .. 60%
        roe_score = ((r - (-0.5)) / (1.1)) * 100.0  # normalize

    # revenueGrowth: -1 .. 2 (即 -100% 到 +200%) 映射 0-100
    rg = info.get("revenueGrowth")
    rg_score = None
    if rg and isinstance(rg, (int, float)):
        g = max(-1.0, min(2.0, float(rg)))
        rg_score = ((g + 1.0) / 3.0) * 100.0

    # marketCap: map log-scale to 0-100
    mc = info.get("marketCap")
    mc_score = None
    if mc and isinstance(mc, (int, float)) and mc > 0:
        import math
        # 使用 log10 市值，並對常見範圍 1e7 to 1e12 做映射
        v = math.log10(mc)
        v = max(7.0, min(12.0, v))
        mc_score = ((v - 7.0) / 5.0) * 100.0

    # 合併：若某項為 None，則對應權重降為 0，並把其他權重重新 normalize
    parts = []
    weights = []
    if us is not None:
        parts.append(us * w_user)
        weights.append(w_user)
    if pe_score is not None:
        parts.append(pe_score * w_pe)
        weights.append(w_pe)
    if roe_score is not None:
        parts.append(roe_score * w_roe)
        weights.append(w_roe)
    if rg_score is not None:
        parts.append(rg_score * w_rev)
        weights.append(w_rev)
    if mc_score is not None:
        parts.append(mc_score * w_mc)
        weights.append(w_mc)

    if not weights:
        return 50.0  # 完全沒資料時回傳中性分數

    # normalize by sum(weights)
    sum_w = sum(weights)
    combined = sum(parts) / sum_w
    # clamp 0-100
    combined = max(0.0, min(100.0, combined))
    return round(combined, 2)

def generate_text_summary(info: dict, user_score):
    """
    根據已取得的 fields 產生簡短可閱讀的分析段落（rule-based）。
    也會在 '來源' 中標示哪些欄位來自 yfinance，哪些來自 user。
    """
    lines = []
    s = info.get("symbol", "N/A")
    name = info.get("shortName") or info.get("longName") or s
    lines.append(f"公司：{name} ({s})")

    # highlight key metrics if available
    if info.get("forwardPE") or info.get("trailingPE"):
        pe = info.get("forwardPE") or info.get("trailingPE")
        lines.append(f"- 本益比 (PE)：{round(pe,2)}（由 yfinance 提供）")
    if info.get("returnOnEquity") is not None:
        lines.append(f"- ROE：{info.get('returnOnEquity')*100:.2f}%（由 yfinance 提供）")
    if info.get("revenueGrowth") is not None:
        lines.append(f"- 營收成長率：{info.get('revenueGrowth')*100:.2f}%（由 yfinance 提供）")
    if info.get("marketCap") is not None:
        lines.append(f"- 市值：${info.get('marketCap')/1e9:.2f}B（由 yfinance 提供）")
    if user_score is not None:
        lines.append(f"- 你的人工評分：{user_score} / 10（由 你 提供）")

    # quick rule-based interpretation
    # 判斷簡單語句
    pe_val = info.get("forwardPE") or info.get("trailingPE")
    roe_val = info.get("returnOnEquity")
    rg = info.get("revenueGrowth")

    interpret = []
    if pe_val and isinstance(pe_val, (int,float)):
        if pe_val < 15:
            interpret.append("估值相對低（PE < 15）")
        elif pe_val > 40:
            interpret.append("估值偏高（PE > 40）")
    if roe_val and isinstance(roe_val, (int,float)):
        if roe_val > 0.15:
            interpret.append("ROE 高，資本回報佳")
        elif roe_val < 0:
            interpret.append("ROE 負值，需注意獲利能力")
    if rg and isinstance(rg, (int,float)):
        if rg > 0.2:
            interpret.append("營收強勁成長")
        elif rg < -0.1:
            interpret.append("營收衰退顯著")

    if interpret:
        lines.append("- 小結：" + "；".join(interpret) + "。")
    else:
        lines.append("- 小結：資訊不足或指標中性，建議查看更多財報細節。")

    return "\n".join(lines)

# -------------------------
# UI 與主流程
# -------------------------
def display_sector_ui(vault):
    st.sidebar.header("📁 產業 & 股票管理")
    # 顯示現有產業
    sectors = vault.get("sectors", {})
    sector_names = list(sectors.keys())

    # 選擇產業或新增
    selected_sector = st.sidebar.selectbox("選擇產業（或新增）", options=sector_names + ["__新增產業__"])
    if selected_sector == "__新增產業__":
        new_name = st.sidebar.text_input("輸入新產業名稱")
        if new_name:
            if new_name in sectors:
                st.sidebar.warning("產業已存在。")
            else:
                sectors[new_name] = []
                save_vault(vault)
                st.sidebar.success(f"已新增產業：{new_name}")
                # refresh (簡單方式)
                st.experimental_rerun()
        st.sidebar.markdown("---")
        selected_sector = None

    # 如果已選產業，顯示該產業的股票並提供新增/刪除
    if selected_sector:
        st.sidebar.subheader(f"產業：{selected_sector}")
        stocks = sectors.get(selected_sector, [])
        st.sidebar.write("目前股票：")
        if stocks:
            st.sidebar.write(", ".join(stocks))
        else:
            st.sidebar.write("（尚無股票）")

        # 新增 ticker
        add_ticker = st.sidebar.text_input("新增股票代號 (逗號分隔可一次多個)", key="add_ticker_input")
        if st.sidebar.button("➕ 新增股票到此產業"):
            if add_ticker.strip():
                for t in [x.strip().upper() for x in add_ticker.split(",") if x.strip()]:
                    if t not in stocks:
                        stocks.append(t)
                sectors[selected_sector] = stocks
                vault["sectors"] = sectors
                save_vault(vault)
                st.sidebar.success("已新增並儲存。")
                st.experimental_rerun()

        # 刪除某個 ticker
        del_ticker = st.sidebar.selectbox("選擇要移除的股票", options=["-- 不移除 --"] + stocks)
        if del_ticker and del_ticker != "-- 不移除 --":
            if st.sidebar.button("🗑️ 移除選定股票"):
                stocks.remove(del_ticker)
                sectors[selected_sector] = stocks
                vault["sectors"] = sectors
                save_vault(vault)
                st.sidebar.success(f"已移除 {del_ticker}")
                st.experimental_rerun()

        st.sidebar.markdown("---")
        # 允許重命名或刪除產業
        if st.sidebar.button("🗑️ 刪除此產業（含內部股票）"):
            confirm = st.sidebar.checkbox(f"確認刪除 {selected_sector}", key="confirm_del_sector")
            if confirm:
                sectors.pop(selected_sector, None)
                vault["sectors"] = sectors
                save_vault(vault)
                st.sidebar.success(f"已刪除產業 {selected_sector}")
                st.experimental_rerun()

    # 提供整體儲存/匯出按鈕
    st.sidebar.markdown("---")
    if st.sidebar.button("💾 手動儲存目前設定"):
        save_vault(vault)
        st.sidebar.success("已儲存到本機。")

    if st.sidebar.button("📤 匯出 JSON (顯示)"):
        st.sidebar.code(json.dumps(vault, ensure_ascii=False, indent=2))

    return vault

def display_main_area(vault):
    st.title("📈 股票產業分析工具（已加入持久化與內建分析）")
    st.caption("資料來源主要來自 yfinance；你也可手動輸入個股分數，系統會把 yfinance 與你輸入的分數合併後產生分析與排序。")

    sectors = vault.get("sectors", {})
    user_scores = vault.get("user_scores", {})

    # 預設選產業
    if not sectors:
        st.warning("目前沒有任何產業，請在側邊欄新增產業與股票。")
        return

    selected_sector = st.selectbox("選擇要分析的產業", options=list(sectors.keys()))
    tickers = sectors.get(selected_sector, [])
    st.info(f"此產業將分析 {len(tickers)} 檔股票：{', '.join(tickers)}")

    # 使用者可一次自訂多檔的手動分數（表格輸入）
    st.subheader("🔧 手動輸入 / 編輯 你的評分 (0-10)")
    if tickers:
        cols = st.columns([2, 1, 1])
        with cols[0]:
            st.write("股票代號")
        with cols[1]:
            st.write("你的評分 (0-10)")
        with cols[2]:
            st.write("儲存 / 清除")
        # 逐列呈現
        for s in tickers:
            c1, c2, c3 = st.columns([2,1,1])
            with c1:
                st.write(s)
            with c2:
                val = user_scores.get(s, "")
                new_val = st.text_input(f"score_{s}", value=str(val) if val!="" else "", key=f"score_input_{s}")
            with c3:
                if st.button(f"保存_{s}", key=f"save_{s}"):
                    # 驗證並存檔
                    try:
                        if new_val == "":
                            # 若空字串視為清除
                            if s in user_scores:
                                user_scores.pop(s, None)
                        else:
                            num = float(new_val)
                            if num < 0 or num > 10:
                                st.error("評分請介於 0-10。")
                            else:
                                user_scores[s] = round(num, 2)
                        vault["user_scores"] = user_scores
                        save_vault(vault)
                        st.success(f"{s} 的分數已儲存。")
                    except Exception as e:
                        st.error(f"儲存失敗：{e}")
                    st.experimental_rerun()
                if st.button(f"清除_{s}", key=f"clear_{s}"):
                    if s in user_scores:
                        user_scores.pop(s, None)
                        vault["user_scores"] = user_scores
                        save_vault(vault)
                        st.success(f"{s} 的分數已清除。")
                    else:
                        st.info("原本就沒有分數。")
                    st.experimental_rerun()

    st.markdown("---")
    # 分析按鈕
    if st.button("🚀 開始分析（抓取 yfinance + 產生內建分析）"):
        with st.spinner("抓取資料並運算中..."):
            infos, failed = batch_fetch(tickers)
            if failed:
                st.warning(f"下列代號抓取失敗：{', '.join(failed)}（可能無效代號或被限流）")

            # 整理 table
            records = []
            for t in tickers:
                info = infos.get(t, {}) if infos else {}
                rec = {
                    "公司名稱": info.get("shortName", info.get("longName", "N/A")),
                    "代號": t,
                    "前瞻 PE": round(info.get("forwardPE", 0), 2) if info.get("forwardPE") else ("N/A" if info.get("trailingPE") is None else round(info.get("trailingPE"),2)),
                    "ROE %": f"{info.get('returnOnEquity', None)*100:.2f}%" if info.get('returnOnEquity') is not None else "N/A",
                    "營收增長 %": f"{info.get('revenueGrowth', None)*100:.2f}%" if info.get('revenueGrowth') is not None else "N/A",
                    "市值 (B)": f"${info.get('marketCap', 0)/1e9:.2f}B" if info.get('marketCap') else "N/A",
                    "人工評分": user_scores.get(t, "N/A"),
                }
                # 計算合成分數與分析文字
                combined = compute_combined_score(info, user_scores.get(t, None))
                summary = generate_text_summary(info, user_scores.get(t, None))
                rec["合成分數 (0-100)"] = combined
                rec["分析摘要（點擊右側展開看詳細）」] = "查看"
                records.append((t, rec, summary, info))

            # 將 records 轉為 DataFrame（以合成分數排序）
            df_rows = [r for (_, r, _, _) in records]
            df = pd.DataFrame(df_rows)
            try:
                df_sorted = df.sort_values("合成分數 (0-100)", ascending=False)
            except:
                df_sorted = df
            st.subheader("📋 同業比較表（依合成分數排序）")
            st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True)

            # 顯示每檔的文字摘要與來源
            st.subheader("🔎 各檔股票詳細說明（來源標示）")
            for (t, rec, summary, info) in records:
                with st.expander(f"{t} — {rec['公司名稱']}，合成分數：{rec['合成分數 (0-100)']}"):
                    st.markdown(summary)
                    st.markdown("**來源說明（此處列出此檔股票資訊的來源）**")
                    # 判斷哪些欄位存在且來源為 yfinance；人工評分來源於 user
                    src_lines = []
                    # 主要欄位
                    if info:
                        src_lines.append("- yfinance: shortName/longName, forwardPE/trailingPE, returnOnEquity, revenueGrowth, marketCap 等欄位。")
                    else:
                        src_lines.append("- 無 yfinance 資料（抓取失敗或代號錯誤）。")
                    if user_scores.get(t) is not None:
                        src_lines.append("- 你的人工評分：直接由你在 UI 輸入並儲存在本地 JSON。")
                    st.markdown("\n".join(src_lines))
                    # 顯示 raw info 的重點欄位（條列式）
                    st.markdown("**條列式重點數據**")
                    bullet = []
                    if info:
                        bullet.append(f"- 公司名稱：{info.get('shortName') or info.get('longName')}")
                        if info.get("forwardPE") or info.get("trailingPE"):
                            pe_val = info.get("forwardPE") or info.get("trailingPE")
                            bullet.append(f"- PE：{pe_val}")
                        if info.get("returnOnEquity") is not None:
                            bullet.append(f"- ROE：{info.get('returnOnEquity')*100:.2f}%")
                        if info.get("revenueGrowth") is not None:
                            bullet.append(f"- 營收成長率：{info.get('revenueGrowth')*100:.2f}%")
                        if info.get("marketCap") is not None:
                            bullet.append(f"- 市值：${info.get('marketCap')/1e9:.2f}B")
                    else:
                        bullet.append("- 無可用細項數據（yfinance 抓取失敗）。")
                    st.markdown("\n".join(bullet))

            # 儲存最新 vault（把 user_scores 與 sectors 寫回檔案）
            vault["user_scores"] = user_scores
            vault["sectors"] = sectors
            save_vault(vault)
            st.success("分析完成，結果已顯示並且本地已儲存你的人工評分。")

    # 使用說明
    with st.expander("📖 使用說明與備註"):
        st.markdown("""
        - 來源：主資料來自 yfinance（網路抓取），人工評分由你在 UI 中輸入並儲存在本地 JSON (`investment_vault_2026.json`)。
        - 若 yfinance 抓取失敗，app 會顯示失敗列表；你可以檢查代號是否正確。
        - 內建 AI 為 rule-based 分析（立即可用），若你有穩定的 AI Key 想串外部模型，可再提供，我可以幫你把呼叫外部模型的範例加入（需你提供 API Key）。
        - 所有你手動輸入的評分會被保存在同一個 JSON，重新啟動 app 仍會保留。
        """)

# -------------------------
# main
# -------------------------
def main():
    st.set_page_config(page_title="股票產業分析", page_icon="📈", layout="wide")
    # load
    vault = load_vault()
    vault = display_sector_ui(vault)
    display_main_area(vault)

if __name__ == "__main__":
    main()
