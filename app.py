import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# ===================================================
# 🔑 系統密碼與 API 設定
# ===================================================
MY_PRIVATE_PASSWORD = "36333948" 
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiMzQzNTY4MTIiLCJlbWFpbCI6IngxMjN5ejg3QGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjB9.X3YH2qYzM84f3iJeD0vendPFoUP7nvrONOyXvkfDdWQ"

st.set_page_config(page_title="個人化智慧看盤系統 v18.0 雲端版", layout="wide")

# 🚀 功能三：網頁最頂端設定錨點（一鍵回到頂部必備）
st.markdown("<div id='top'></div>", unsafe_allow_html=True) 

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (GSheets 雲端版)</h3>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="輸入密碼...", key="login_pwd")
        if st.button("確認解鎖 🔓", use_container_width=True):
            if input_password == MY_PRIVATE_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else: 
                st.error("❌ 密碼錯誤")
    st.stop()

# 2. 🔗 初始化 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_cloud = conn.read(worksheet="工作表1", ttl=0)
    df_cloud['stock_id'] = df_cloud['stock_id'].astype(str).str.strip()
    df_cloud['stock_id'] = df_cloud['stock_id'].str.split('.').str[0]
    df_cloud = df_cloud[df_cloud['stock_id'].notna() & (df_cloud['stock_id'] != "") & (df_cloud['stock_id'] != "nan")]
    df_cloud = df_cloud[~df_cloud['stock_id'].str.contains("必填", na=False)]
except Exception as e:
    st.error(f"🚨 讀取雲端資料表失敗，請檢查權限或 Secrets 設定。錯誤原因: {str(e)}")
    st.stop()

# 將雲端 DataFrame 拆解並對應回原本的系統核心字典中
watchlist = {}
names_db = {}
backup_db = {}

for _, row in df_cloud.iterrows():
    ticker = str(row['stock_id']).strip().upper()
    # 🎯 讀取分類欄位（如果雲端沒有這欄，預設給「未分類」）
    cat = str(row['分類']).strip() if '分類' in df_cloud.columns and pd.notna(row['分類']) else "未分類"
    
    watchlist[ticker] = {
        "type": str(row['type']).strip() if pd.notna(row['type']) else "觀察中 (尚未買進)",
        "cost": float(row['cost']) if pd.notna(row['cost']) else 0.0,
        "qty": int(row['qty']) if pd.notna(row['qty']) else 0,
        "category": cat  # 加入分類資料
    }
    names_db[ticker] = str(row['stock_name']).strip() if pd.notna(row['stock_name']) else ticker
    backup_db[ticker] = {
        "pe": float(row['pe']) if pd.notna(row['pe']) else 0.0,
        "yield": float(row['yield']) if pd.notna(row['yield']) else 0.0,
        "net_buy_5d": int(row['net_buy_5d']) if pd.notna(row['net_buy_5d']) else 0,
        "rev_6ma": float(row['rev_6ma']) if pd.notna(row['rev_6ma']) else 0.0,
        "rev_12ma": float(row['rev_12ma']) if pd.notna(row['rev_12ma']) else 0.0
    }

def save_to_google_sheets(w_dict, n_dict, b_dict):
    rows = []
    all_tickers = sorted(list(w_dict.keys()))
    for ticker in all_tickers:
        w = w_dict[ticker]
        n = n_dict.get(ticker, ticker)
        b = b_dict.get(ticker, {"pe": 0.0, "yield": 0.0, "net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0})
        rows.append({
            "stock_id": ticker,
            "stock_name": n,
            "分類": w.get("category", "未分類"), # 同步寫入分類
            "type": w["type"],
            "cost": w["cost"],
            "qty": w["qty"],
            "pe": b["pe"],
            "yield": b["yield"],
            "net_buy_5d": b["net_buy_5d"],
            "rev_6ma": b["rev_6ma"],
            "rev_12ma": b["rev_12ma"]
        })
    new_df = pd.DataFrame(rows)
    try:
        conn.update(worksheet="工作表1", data=new_df)
        return True
    except Exception as e:
        st.error(f"❌ 雲端資料同步更新失敗: {str(e)}")
        return False

@st.cache_data(ttl=3600)
def fetch_clean_stock_data(ticker_symbol, token):
    clean_id = ticker_symbol.replace(".TW", "").replace(".TWO", "")
    price_start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    val_start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    url = "https://api.finmindtrade.com/api/v4/data"
    
    try:
        res_price = requests.get(url, params={
            "dataset": "TaiwanStockPrice", "data_id": clean_id,
            "start_date": price_start_date, "token": token
        }, timeout=10)
        price_data = res_price.json()
        if price_data.get("msg") != "success" or not price_data.get("data"):
            return None, {}, "無法從 FinMind 取得股價，請確認代碼或 API 額度。"
            
        df_price = pd.DataFrame(price_data["data"])
        df_price.rename(columns={'close': 'Close', 'date': 'Date', 'max': 'High', 'min': 'Low', 'open': 'Open'}, inplace=True)
        df_price['Date'] = pd.to_datetime(df_price['Date'])
        df_price.set_index('Date', inplace=True)
        
        res_val = requests.get(url, params={
            "dataset": "TaiwanStockPER", "data_id": clean_id,
            "start_date": val_start_date, "token": token
        }, timeout=10)
        val_data_json = res_val.json()
        pe, yield_pct = None, None
        if val_data_json.get("msg") == "success" and val_data_json.get("data"):
            df_val = pd.DataFrame(val_data_json["data"])
            if not df_val.empty:
                latest_val = df_val.iloc[-1]
                pe = latest_val.get("PE_ratio")
                yield_pct = latest_val.get("dividend_yield")
        
        return df_price, {"pe": pe, "yield": yield_pct}, "OK"
    except Exception as e: 
        return None, {}, f"連線異常: {str(e)}"

def get_display_name(ticker):
    return names_db.get(ticker, ticker)

# ===================================================
# 🗂️ 側邊欄：全局控制與分類篩選
# ===================================================
st.sidebar.header("🛠️ 戰情控制面板")

# 🚀 功能一：一鍵展開開關
expand_all = st.sidebar.checkbox("🔓 一鍵展開所有股票資訊", value=False)
st.sidebar.divider()

# 🚀 功能二：股票分類篩選
all_cats = list(set([data["category"] for data in watchlist.values()])) if watchlist else []
if "未分類" in all_cats and len(all_cats) == 1:
    st.sidebar.info("💡 提示：您可以在「設定後台」幫股票加上分類喔！")
    selected_cat = "全部"
else:
    selected_cat = st.sidebar.selectbox("📂 股票分類篩選", ["全部"] + sorted([c for c in all_cats if c != "nan" and c != ""]))


# ===================================================
# 📊 介面啟動與主選單
# ===================================================
st.title("📊 個人化智慧看盤系統 v18.0 雲端版")
st.caption("☁️ 數據實時連動 Google Sheets │ 🚀 全面導入 FinMind API 安全速配版")

if st.button("🔄 強制清除股價快取 (抓取最新盤後資料)"):
    st.cache_data.clear()
    st.rerun()

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"])

# ===================================================
# 🟢 核心戰情分頁
# ===================================================
with main_tab:
    if not watchlist:
        st.info("💡 目前雲端試算表內沒有股票資料。請切換到「設定後台」新增股票！")
    else:
        ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_180")
        st.write("---")
        
        for ticker_symbol, item in watchlist.items():
            # 🎯 執行分類篩選過濾
            if selected_cat != "全部" and item["category"] != selected_cat:
                continue

            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol, FINMIND_TOKEN)
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0, "pe": 0.0, "yield": 0.0})
            
            if hist is None: 
                st.warning(f"⚠️ 暫時無法取得 【{stock_name} ({ticker_symbol})】 的即時股價。已切換為純備援顯示。原因：{status}")
                continue

            pe = b_item.get("pe", 0.0) if b_item.get("pe", 0.0) > 0 else (val_data.get("pe") if pd.notna(val_data.get("pe")) else 0.0)
            yield_pct = b_item.get("yield", 0.0) if b_item.get("yield", 0.0) > 0 else (val_data.get("yield") if pd.notna(val_data.get("yield")) else 0.0)
            net_buy_5d = b_item.get("net_buy_5d", 0)
            rev_6ma = b_item.get("rev_6ma", 0.0) 
            rev_12ma = b_item.get("rev_12ma", 0.0) 

            if pe == 0:
                pe_status, pe_color = "不適用 (ETF/未填寫)", "⚪"
            else:
                pe_status = f"便宜 ({pe:.1f})" if pe < 12 else (f"合理 ({pe:.1f})" if pe <= 20 else f"昂貴 ({pe:.1f})")
                pe_color = "🟢" if pe < 12 else ("🟡" if pe <= 20 else "🔴")
            
            if yield_pct == 0:
                yield_status, yield_color = "無配息", "⚪"
            else:
                yield_status = f"高殖利率 ({yield_pct:.2f}%)" if yield_pct >= 4.5 else f"一般 ({yield_pct:.2f}%)"
                yield_color = "🟢" if yield_pct >= 4.5 else "🟡"
            
            if rev_6ma == 0 and rev_12ma == 0:
                rev_status = "⚪ 不適用 (ETF/無營收)"
            elif rev_6ma >= rev_12ma:
                rev_status = f"🟢 多頭 (6MA {rev_6ma:,.2f} > 12MA {rev_12ma:,.2f})"
            else:
                rev_status = f"🔴 衰退 (6MA {rev_6ma:,.2f} < 12MA {rev_12ma:,.2f})"
            
            if net_buy_5d > 1500: 
                chips_status = f"🟢 主力大買 (+{net_buy_5d}張)"
            elif net_buy_5d < -1500: 
                chips_status = f"🔴 主力大賣 ({net_buy_5d}張)"
            else: 
                chips_status = f"🟡 籌碼震盪 ({net_buy_5d}張)"

            price = float(hist['Close'].iloc[-1])
            historical_max = float(hist['Close'].max())
            stop_base = max(item["cost"], historical_max)
            trailing_stop_line = stop_base * 0.90 
            
            if price > trailing_stop_line:
                drop_needed = ((price - trailing_stop_line) / price) * 100
                stop_light, hold_action, hold_color = f"🍏 安全 (再跌 {drop_needed:.1f}% 止損)", "續抱安全區", "🍏"
            else:
                drop_broken = ((trailing_stop_line - price) / trailing_stop_line) * 100
                stop_light, hold_action, hold_color = f"🔴 破線 (超限 {drop_broken:.1f}%)", "🚨 觸發移動停損！請執行賣出紀律！", "🔴"

            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            target_ma = hist['MA20'].iloc[-1] if "20MA" in ma_strategy else hist['MA60'].iloc[-1]
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA"
            buy_range_str = f"{target_ma:.2f} ~ {target_ma * 1.05:.2f}" if pd.notna(target_ma) else "資料天數不足"
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
            else: 
                pnl_str, hold_action, stop_light, hold_color = "—", "觀察中", "—", "⚪"
                
            # 🎯 expanded=expand_all 讓側邊欄開關可以控制這裡
            with st.expander(f"📈 {stock_name} ({ticker_symbol}) ｜ 🏷️ {item['category']} ｜ 現價: 🌐 {price:.2f} ｜ 🛑 {hold_color} {hold_action}", expanded=expand_all):
                if item["type"] == "已持股":
                    st.markdown("### 🛑 移動停損即時監控數據")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("⛰ *半年最高價*", f"{historical_max:.2f} 元")
                    col2.metric("🎯 *停損賣出線*", f"{trailing_stop_line:.2f} 元")
                    col3.metric("🚨 *死線倒數*", stop_light)
                    st.markdown(f"**💰 目前持股累積損益：** **{pnl_str}**")
                    st.write("---")
                
                st.markdown(f"**🛒 理想買入防線 ({ma_label})：** **{buy_range_str} 元**")
                st.markdown(f"**🎯 估值區間 (P/E)：** {pe_color} {pe_status} ｜ **🛡 股息底氣：** {yield_color} {yield_status}")
                st.markdown(f"**📈 營收趨勢判定 (6MA vs 12MA)：** {rev_status} ｜ **👤 主力籌碼：** {chips_status}")

# ===================================================
# ⚙️ 設定後台分頁
# ===================================================
with control_tab:
    st.subheader("☁️ 雲端同步狀態監控")
    st.info("💡 系統已成功綁定 Google Sheets。你在下方所做的所有新增、刪除或修改，都會自動同步寫回你的雲端試算表！")
    st.write("---")

    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("➕ 新增 / 編輯庫存股票")
        new_stock = st.text_input("股票代碼 (例: 2330.TW)", key="add_code").upper().strip()
        custom_name = st.text_input("股票中文別名 (例: 台積電)", key="add_name")
        stock_cat = st.text_input("分類 (例: 半導體、ETF)，預設為「未分類」", value="未分類", key="add_cat") # 🎯 新增的分類輸入框
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="add_type")
        
        cost, qty = 0.0, 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="add_cost")
            qty = st.number_input("持有股數", min_value=0, step=100, key="add_qty")
            
        if st.button("💾 確認儲存並同步至雲端", use_container_width=True):
            if new_stock:
                # 儲存時把 category 也放進去
                watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty, "category": stock_cat}
                if custom_name: 
                    names_db[new_stock] = custom_name
                
                if save_to_google_sheets(watchlist, names_db, backup_db):
                    st.success(f"✨ 股票 {new_stock} 成功同步至雲端試算表！")
                    time.sleep(0.5)
                    st.rerun()

        st.write("---")
        
        st.subheader("🗑️ 刪除庫存股票")
        if watchlist:
            stock_to_delete = st.selectbox("請選擇要從清單移除的股票", ["-- 請選擇 --"] + list(watchlist.keys()))
            if st.button("⚠️ 確認刪除並同步至雲端", type="primary", use_container_width=True):
                if stock_to_delete != "-- 請選擇 --" and stock_to_delete in watchlist:
                    del watchlist[stock_to_delete]
                    if stock_to_delete in names_db: del names_db[stock_to_delete]
                    if stock_to_delete in backup_db: del backup_db[stock_to_delete]
                    
                    if save_to_google_sheets(watchlist, names_db, backup_db):
                        st.success(f"已成功自雲端刪除 {stock_to_delete}！")
                        time.sleep(0.5)
                        st.rerun()
        else:
            st.info("目前沒有可刪除的股票。")

    with col_right:
        st.subheader("✍ 🛠️ 進階數據【手動備援區】")
        if watchlist:
            tgt_b = st.selectbox("選擇要備援的股票", list(watchlist.keys()), key="backup_tgt")
            
            cur_b = backup_db.get(tgt_b, {})
            v_pe = float(cur_b.get("pe", 0.0))
            v_yield = float(cur_b.get("yield", 0.0))
            v_chip = int(cur_b.get("net_buy_5d", 0))
            v_6ma = float(cur_b.get("rev_6ma", 0.0))
            v_12ma = float(cur_b.get("rev_12ma", 0.0))
            
            pe_in = st.number_input("手動本益比 (PE) *若為 ETF 請填 0*", value=v_pe, key=f"pe_in_{tgt_b}")
            y_in = st.number_input("手動殖利率 (%) *若為 ETF 請填 0*", value=v_yield, key=f"yield_in_{tgt_b}")
            chip_in = st.number_input("近 5 日法人累積買超 (張)", value=v_chip, key=f"chip_in_{tgt_b}")
            
            st.write("---")
            st.markdown("#### 📈 營收數據備援")
            rev6ma_in = st.number_input("6MA 營收水位", value=v_6ma, step=10.0, key=f"rev6__in_{tgt_b}")
            rev12ma_in = st.number_input("12MA 營收水位", value=v_12ma, step=10.0, key=f"rev12__in_{tgt_b}")
            
            if st.button("💾 儲存並同步到雲端卡片", use_container_width=True, key=f"save_btn_{tgt_b}"):
                backup_db[tgt_b] = {
                    "net_buy_5d": chip_in, "rev_6ma": rev6ma_in, "rev_12ma": rev12ma_in, "pe": pe_in, "yield": y_in
                }
                if save_to_google_sheets(watchlist, names_db, backup_db):
                    st.success(f"✨ {tgt_b} 專屬備援數據成功同步至雲端！")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.info("請先在左側新增股票。")

# ===================================================
# 🚀 功能四：懸浮按鈕 - 一鍵回到最上面 (放在最底部)
# ===================================================
st.markdown("""
    <style>
    .scroll-to-top {
        position: fixed;
        bottom: 30px;
        right: 30px;
        background-color: #ff4b4b; /* Streamlit 紅色 */
        color: white !important;
        padding: 12px 18px;
        border-radius: 50px;
        text-decoration: none;
        font-weight: bold;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
        z-index: 9999;
        transition: all 0.3s ease;
    }
    .scroll-to-top:hover {
        background-color: #d63636;
        transform: scale(1.05);
    }
    </style>
    <a href="#top" class="scroll-to-top">⬆️ 回到頂部</a>
""", unsafe_allow_html=True)
