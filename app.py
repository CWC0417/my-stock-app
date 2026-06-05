import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
import datetime

# 🌟 網頁核心配置 (必須是第一行)
st.set_page_config(page_title="個人化看盤系統 v15.1", layout="wide")

# 🔑 系統設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v15.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v15.json"
FINMIND_TOKEN = "" 

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v15.1)</h3>", unsafe_allow_html=True)
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

# 2. 檔案讀寫
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {"2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}})
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# 3. Yfinance 抓取 (歷史價格 + 估值 + 殖利率)
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 65: return None, {}, "歷史資料不足"
        
        info = stock.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        yield_pct = info.get("dividendYield")
        if yield_pct: yield_pct = round(yield_pct * 100, 2)
        
        val_data = {"pe": pe, "yield": yield_pct}
        return hist, val_data, "OK"
    except Exception as e:
        return None, {}, str(e)

# 4. FinMind API (長線營收 6MA/12MA + 5日波段籌碼)
@st.cache_data(ttl=1800)
def fetch_tw_api_data(ticker_symbol, token=""):
    tw_id = ticker_symbol.split(".")[0]
    today = datetime.date.today()
    start_date_chips = (today - datetime.timedelta(days=15)).strftime("%Y-%m-%d")
    start_date_rev = (today - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
    
    res_dict = {"net_buy_5d": None, "rev_6ma": None, "rev_12ma": None, "api_ok": False}
    base_params = {"data_id": tw_id}
    if token: base_params["token"] = token
        
    try:
        # 籌碼
        p_chips = base_params.copy()
        p_chips.update({"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": start_date_chips})
        req_chips = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_chips, timeout=5).json()
        if req_chips.get("msg") == "success" and len(req_chips.get("data", [])) > 0:
            df_chips = pd.DataFrame(req_chips["data"])
            target_inst = ['外資及陸資(不含外資自營商)', '投信']
            df_target = df_chips[df_chips['name'].isin(target_inst)]
            daily_net = df_target.groupby('date')['buy_sell'].sum()
            res_dict["net_buy_5d"] = int(daily_net.tail(5).sum() / 1000)

        # 營收
        p_rev = base_params.copy()
        p_rev.update({"dataset": "TaiwanStockMonthRevenue", "start_date": start_date_rev})
        req_rev = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_rev, timeout=5).json()
        if req_rev.get("msg") == "success" and len(req_rev.get("data", [])) > 0:
            df_rev = pd.DataFrame(req_rev["data"])
            if len(df_rev) >= 12:
                res_dict["rev_6ma"] = df_rev['revenue'].tail(6).mean()
                res_dict["rev_12ma"] = df_rev['revenue'].tail(12).mean()
                res_dict["api_ok"] = True
    except:
        res_dict["api_ok"] = False 
    return res_dict

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 介面 ---
st.title("⚡ 個人化看盤系統 v15.1")
st.caption("🤖 數據透明化特製版 │ 🛑 移動停損精準試算 │ 🗑️ 修正刪除緩存錯誤")

main_tab, control_tab = st.tabs(["📈 核心戰情面板", "⚙️ 股票管理與手動備援"])

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.warning("請切換到「⚙️ 控制台」新增股票！")
    else:
        col_ctrl1, col_ctrl2 = st.columns([1, 1])
        with col_ctrl1: view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格"], horizontal=True)
        with col_ctrl2: ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True)
            
        st.write("---")
        rows = []
        backup_db = load_json(BACKUP_DATA_FILE, {}) 
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol)
            if hist is None: continue

            # 備援判斷
            api_res = fetch_tw_api_data(ticker_symbol, token=FINMIND_TOKEN)
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 0, "rev_12ma": 0, "pe": 15, "yield": 0})
            
            if api_res["api_ok"] and api_res["net_buy_5d"] is not None:
                net_buy_5d = api_res["net_buy_5d"]
                rev_6ma, rev_12ma = api_res["rev_6ma"], api_res["rev_12ma"]
                mode_tag = "🤖"
            else:
                net_buy_5d = b_item["net_buy_5d"]
                rev_6ma, rev_12ma = b_item["rev_6ma"], b_item["rev_12ma"]
                mode_tag = "✍️"

            pe = val_data.get("pe") if val_data.get("pe") else b_item.get("pe", 0)
            yield_pct = val_data.get("yield") if val_data.get("yield") else b_item.get("yield", 0)

            # 燈號判定
            if pe and pe > 0:
                if pe < 12: pe_status = f"🟢 便宜 ({pe:.1f})"
                elif 12 <= pe <= 20: pe_status = f"🟡 合理 ({pe:.1f})"
                else: pe_status = f"🔴 昂貴 ({pe:.1f})"
            else: pe_status = "⚪ 無資料"

            if yield_pct and yield_pct >= 4.5: yield_status = f"🟢 高殖利率 ({yield_pct:.1f}%)"
            elif yield_pct and yield_pct > 0: yield_status = f"🟡 一般配息 ({yield_pct:.1f}%)"
            else: yield_status = "⚪ 無配息"

            if rev_6ma and rev_12ma:
                rev_status = "🟢 多頭 (6MA>12MA)" if rev_6ma > rev_12ma else "🔴 空頭 (6MA<12MA)"
            else: rev_status = "⚪ 資料不足"

            if net_buy_5d > 1500: chips_status = f"🟢 大買 (+{net_buy_5d}張)"
            elif net_buy_5d < -1500: chips_status = f"🔴 大賣 ({net_buy_5d}張)"
            else: chips_status = f"🟡 中性 ({net_buy_5d}張)"

            # 價格計算
            net_price = hist['Close'].iloc[-1]
            price = st.session_state.live_prices.get(ticker_symbol, net_price)
            price_display = f"⚡ {price:.2f}" if ticker_symbol in st.session_state.live_prices else f"🌐 {price:.2f}"
            
            # 🛑 股癌移動停損演算法核心 (高點回落 10%)
            historical_max = float(hist['Close'].max())
            stop_base = max(item["cost"], historical_max) # 基準點：成本或歷史最高價
            trailing_stop_line = stop_base * 0.90         # 停損死線
            
            if price > trailing_stop_line:
                drop_needed = ((price - trailing_stop_line) / price) * 100
                stop_light = f"🍏 安全 (再跌 {drop_needed:.1f}% 觸發停損)"
                hold_action = "🍏 續抱安全區"
            else:
                drop_broken = ((trailing_stop_line - price) / trailing_stop_line) * 100
                stop_light = f"🔴 嚴重破線 (已超越死線 {drop_broken:.1f}%)"
                hold_action = "🚨 觸發移動停損！技術面走爛，請落實紀律！"

            # 均線技術面
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            target_ma = hist['MA20'].iloc[-1] if "20MA" in ma_strategy else hist['MA60'].iloc[-1]
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA"
            buy_range_str = f"{target_ma:.2f} ~ {target_ma * 1.05:.2f}" if pd.notna(target_ma) else "計算中"
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
            else:
                pnl_str, hold_action, stop_light = "—", "觀察中", "—"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "狀態": item["type"], "現價": price_display, 
                "波段最高": f"{historical_max:.2f}", "移動停損價": f"{trailing_stop_line:.2f}", "停損倒數": stop_light,
                "買點防線": buy_range_str, "🎯估值": pe_status, "🛡️底氣": yield_status, "📈營收": rev_status, 
                "🚨決策": hold_action, "損益": pnl_str
            })

        if view_mode == "📋 完整表格":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ 現價: {r['現價']} ｜ 🛑 {r['🚨決策']}"):
                    if r['狀態'] == "已持股":
                        st.markdown("### 🛑 移動停損透明監控")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("⛰️ 6個月最高價", f"{r['波段最高']} 元")
                        col2.metric("🎯 系統停損死線", f"{r['移動停損價']} 元")
                        col3.metric("🚨 停損安全狀態", r['停損倒數'])
                        st.markdown(f"**💰 目前持股損益：** {r['損益']}")
                        st.write("---")
                    
                    st.markdown(f"**🛒 買入防線 ({ma_label})：** <font color='#66ff66'>**{r['買點防線']} 元**</font>", unsafe_allow_html=True)
                    st.markdown(f"**🎯 估值區間：** {r['🎯估值']} ｜ **🛡️ 股息底氣：** {r['🛡️底氣']} ｜ **📈 長線營收：** {r['📈營收']}")

# ===================================================
# ⚙️ 頁籤二：股票管理與手動備援
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("➕ 新增 / 編輯庫存股票")
        names_db = load_json(NAMES_FILE, {})
        new_stock = st.text_input("股票代碼 (例: 2330.TW)", key="add_id").upper().strip()
        custom_name = st.text_input("股票中文別名 (例: 台積電)", key="add_name")
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="add_type")
        cost, qty = 0.0, 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="add_cost")
            qty = st.number_input("持有股數", min_value=0, step=100, key="add_qty")
            
        if st.button("💾 確認儲存股票", use_container_width=True):
            if new_stock:
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
                save_json(WATCHLIST_FILE, st.session_state.watchlist)
                if custom_name:
                    names_db[new_stock] = custom_name
                    save_json(NAMES_FILE, names_db)
                st.cache_data.clear()
                st.success(f"股票 {new_stock} 儲存成功！")
                time.sleep(0.5)
                st.rerun()

        st.write("---")
        st.subheader("🔥 盤中現價同步")
        if st.session_state.watchlist:
            tgt_p = st.selectbox("選擇股票點選現價", list(st.session_state.watchlist.keys()), key="price_tgt")
            input_p = st.number_input(f"輸入 {tgt_p} 即時價", min_value=0.0, step=0.1, key="price_val")
            if st.button("⚡ 同步現價", use_container_width=True):
                if input_p > 0:
                    st.session_state.live_prices[tgt_p] = input_p
                    st.success("現價同步成功！")
                    time.sleep(0.5)
                    st.rerun()

    with col_right:
        # 🛡️ 修復後的刪除功能：採用獨立下拉選單，完全解決按鈕衝突與緩存卡死問題！
        st.subheader("🗑️ 徹底刪除庫存股票")
        st.caption("🚨 注意：點擊確認後，該股票的所有庫存、名稱與即時價紀錄將被完全抹除。")
        if st.session_state.watchlist:
            del_target = st.selectbox("選擇你想刪除的股票", list(st.session_state.watchlist.keys()), key="del_box")
            if st.button("🔥 確定完全刪除", type="primary", use_container_width=True):
                # 移除價格快取
                if del_target in st.session_state.live_prices: 
                    del st.session_state.live_prices[del_target]
                # 移除清單
                if del_target in st.session_state.watchlist:
                    del st.session_state.watchlist[del_target]
                    save_json(WATCHLIST_FILE, st.session_state.watchlist)
                st.cache_data.clear()
                st.success(f"🛑 {del_target} 已從系統中完美剔除！")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("目前清單內沒有任何股票可供刪除。")

        st.write("---")
        st.subheader("✍️ 進階數據【手動備援區】")
        if st.session_state.watchlist:
            tgt_b = st.selectbox("選擇要備援的股票", list(st.session_state.watchlist.keys()), key="sb_box")
            cur_b = backup_db.get(tgt_b, {"net_buy_5d": 0, "rev_6ma": 1, "rev_12ma": 0, "pe": 0, "yield": 0})
            pe_in = st.number_input("手動本益比 (PE)", value=float(cur_b.get("pe", 0)), step=1.0, key="b_pe")
            y_in = st.number_input("手動殖利率 (%)", value=float(cur_b.get("yield", 0)), step=0.1, key="b_yield")
            chip_in = st.number_input("近 5 日法人累積買超 (張)", value=int(cur_b.get("net_buy_5d", 0)), step=100, key="b_chip")
            r6 = st.number_input("6MA 營收水位", value=float(cur_b.get("rev_6ma", 1)), step=10.0, key="b_r6")
            r12 = st.number_input("12MA 營收水位", value=float(cur_b.get("rev_12ma", 0)), step=10.0, key="b_r12")
            if st.button("💾 儲存備援數據", use_container_width=True, key="b_btn"):
                backup_db[tgt_b] = {"net_buy_5d": chip_in, "rev_6ma": r6, "rev_12ma": r12, "pe": pe_in, "yield": y_in}
                save_json(BACKUP_DATA_FILE, backup_db)
                st.success("備援數據儲存成功！")
                time.sleep(0.5)
                st.rerun()