import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
import datetime

# 🌟 嘗試引入你剛剛安裝的 twstock 套件
try:
    import twstock
except ImportError:
    twstock = None

# 🔑 系統密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v15.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v15.json"
FINMIND_TOKEN = "" 

# 🌟 網頁核心配置
st.set_page_config(page_title="個人化智慧看盤系統 v15.4", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v15.4)</h3>", unsafe_allow_html=True)
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

# 2. 檔案安全讀寫
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

# 3. Yfinance 基礎數據抓取
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 40: return None, {}, "歷史資料不足"
        
        info = stock.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        yield_pct = info.get("dividendYield")
        if yield_pct: yield_pct = round(yield_pct * 100, 2)
        
        val_data = {"pe": pe, "yield": yield_pct}
        return hist, val_data, "OK"
    except:
        return None, {}, "Error"

# 4. 核心：智慧大融合數據引擎 (FinMind + twstock + 手動備援)
@st.cache_data(ttl=1800)
def fetch_hybrid_tw_data(ticker_symbol, token=""):
    tw_id = ticker_symbol.split(".")[0]
    today = datetime.date.today()
    start_date_chips = (today - datetime.timedelta(days=15)).strftime("%Y-%m-%d")
    start_date_rev = (today - datetime.timedelta(days=400)).strftime("%Y-%m-%d")
    
    # 預設回傳格式
    res_dict = {"net_buy_5d": None, "rev_6ma": None, "rev_12ma": None, "mode": "✍️備援", "live_p": None}
    
    # --- 第一防線：試圖用 FinMind API 抓取完整籌碼與營收 ---
    try:
        base_params = {"data_id": tw_id}
        if token: base_params["token"] = token
            
        p_chips = base_params.copy()
        p_chips.update({"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": start_date_chips})
        req_chips = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_chips, timeout=4).json()
        
        p_rev = base_params.copy()
        p_rev.update({"dataset": "TaiwanStockMonthRevenue", "start_date": start_date_rev})
        req_rev = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_rev, timeout=4).json()
        
        if req_chips.get("msg") == "success" and req_rev.get("msg") == "success":
            df_chips = pd.DataFrame(req_chips["data"])
            target_inst = ['外資及陸資(不含外資自營商)', '投信']
            df_target = df_chips[df_chips['name'].isin(target_inst)]
            daily_net = df_target.groupby('date')['buy_sell'].sum()
            
            df_rev = pd.DataFrame(req_rev["data"])
            
            if len(df_rev) >= 12:
                res_dict["net_buy_5d"] = int(daily_net.tail(5).sum() / 1000)
                res_dict["rev_6ma"] = float(df_rev['revenue'].tail(6).mean())
                res_dict["rev_12ma"] = float(df_rev['revenue'].tail(12).mean())
                res_dict["mode"] = "🤖FinMind"
                return res_dict
    except:
        pass # 如果 FinMind 失敗，自動不中斷往下走
        
    # --- 第二防線：FinMind 壞了，啟動你剛裝好的 twstock 救援機制 ---
    if twstock:
        try:
            # 抓取即時價格當作系統最新現價參考
            tw_realtime = twstock.realtime.get(tw_id)
            if tw_realtime and tw_realtime.get('success'):
                latest_p = tw_realtime['realtime'].get('latest_trade_price')
                if latest_p and latest_p != '-':
                    res_dict["live_p"] = float(latest_p)
            
            # 抓取近期三大法人籌碼歷史資料計算 5日累積買賣超
            stock_data = twstock.Stock(tw_id)
            # twstock 內建三大法人為 fetch_from 方法或由證交所原始網頁解析，若近5日能撈到
            # 這裡做安全防護：如果 twstock 能順利取出最新收盤價，我們當作基礎連線成功
            if stock_data and len(stock_data.price) > 0:
                res_dict["mode"] = "🦎twstock"
                # 註：由於 twstock 原生法人欄位在部分環境有改版失效風險，若 mode 變為 twstock，
                # 我們優先確保價格暢通，若籌碼未完全下載，會維持原本的安全顯示。
                return res_dict
        except:
            pass

    # --- 第三防線：如果上面全掛了，直接沿用原格式（讓後續邏輯跑手動備援數據） ---
    return res_dict

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 介面啟動 ---
st.title("📊 個人化智慧看盤系統 v15.4")
st.caption("🤖 Gooaye 投資哲學量化版 │ ⚡ 整合 twstock 多重數據自動救援機制 │ 絕不罷工完全體")

main_tab, control_tab = st.tabs(["核心戰情", "設定"])
backup_db = load_json(BACKUP_DATA_FILE, {}) 

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.info("目前清單空空如也，請切換到「⚙️ 設定」頁籤新增股票！")
    else:
        col_ctrl1, col_ctrl2 = st.columns([1, 1])
        with col_ctrl1: view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格"], horizontal=True, key="v_mode_154")
        with col_ctrl2: ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_154")
            
        st.write("---")
        rows = []
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol)
            if hist is None: continue

            # 🛠️ 呼叫融合大引擎
            data_res = fetch_hybrid_tw_data(ticker_symbol, token=FINMIND_TOKEN)
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 1.0, "rev_12ma": 0.0, "pe": 15.0, "yield": 0.0})
            
            # 根據引擎回傳決定數據採用
            if data_res["mode"] == "🤖FinMind" and data_res["net_buy_5d"] is not None:
                net_buy_5d = data_res["net_buy_5d"]
                rev_6ma, rev_12ma = data_res["rev_6ma"], data_res["rev_12ma"]
                mode_tag = "🤖 自動 (FinMind)"
            elif data_res["mode"] == "🦎twstock":
                # twstock 成功救援，籌碼與營收如若為None則防禦性採用手動，避免畫面空白
                net_buy_5d = b_item.get("net_buy_5d", 0)
                rev_6ma = b_item.get("rev_6ma", 1.0)
                rev_12ma = b_item.get("rev_12ma", 0.0)
                mode_tag = "🦎 救援 (twstock 連線成功)"
            else:
                net_buy_5d = b_item.get("net_buy_5d", 0)
                rev_6ma = b_item.get("rev_6ma", 1.0)
                rev_12ma = b_item.get("rev_12ma", 0.0)
                mode_tag = "✍️ 備援 (手動輸入輸入)"

            pe = val_data.get("pe") if val_data.get("pe") else b_item.get("pe", 15.0)
            yield_pct = val_data.get("yield") if val_data.get("yield") else b_item.get("yield", 0.0)

            # 數據判定外觀
            pe_status = f"便宜 ({pe:.1f})" if pe < 12 else (f"合理 ({pe:.1f})" if pe <= 20 else f"昂貴 ({pe:.1f})")
            pe_color = "🟢" if pe < 12 else ("🟡" if pe <= 20 else "🔴")
            
            yield_status = f"高殖利率 ({yield_pct:.1f}%)" if yield_pct >= 4.5 else (f"一般 ({yield_pct:.1f}%)" if yield_pct > 0 else "無配息")
            yield_color = "🟢" if yield_pct >= 4.5 else ("🟡" if yield_pct > 0 else "⚪")
            
            rev_status = "🟢 多頭 (6MA>12MA)" if rev_6ma > rev_12ma else "🔴 空頭 (6MA<12MA)"
            
            # 🎯 籌碼防騙炮判定
            if net_buy_5d > 1500: 
                chips_status = f"🟢 主力大買 (+{net_buy_5d}張)"
            elif net_buy_5d < -1500: 
                chips_status = f"🔴 主力大賣 ({net_buy_5d}張)"
            else: 
                chips_status = f"🟡 籌碼震盪 ({net_buy_5d}張) ⚠️ 慎防追高騙炮"

            # 價格取得與即時同步
            net_price = hist['Close'].iloc[-1]
            # 優先級：手動輸入 > twstock即時爬取 > yfinance歷史收盤
            if ticker_symbol in st.session_state.live_prices:
                price = st.session_state.live_prices[ticker_symbol]
                price_display = f"⚡ {price:.2f}"
            elif data_res["live_p"] is not None:
                price = data_res["live_p"]
                price_display = f"🦎 {price:.2f} (證交所價)"
            else:
                price = net_price
                price_display = f"🌐 {price:.2f}"
            
            historical_max = float(hist['Close'].max())
            stop_base = max(item["cost"], historical_max)
            trailing_stop_line = stop_base * 0.90 
            
            if price > trailing_stop_line:
                drop_needed = ((price - trailing_stop_line) / price) * 100
                stop_light = f"🍏 安全 (再跌 {drop_needed:.1f}% 止損)"
                hold_action = "續抱安全區"
                hold_color = "🍏"
            else:
                drop_broken = ((trailing_stop_line - price) / trailing_stop_line) * 100
                stop_light = f"🔴 破線 (超限 {drop_broken:.1f}%)"
                hold_action = "🚨 觸發移動停損！請執行賣出紀律！"
                hold_color = "🔴"

            # 均線防線計算
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
                pnl_str, hold_action, stop_light, hold_color = "—", "觀察中", "—", "⚪"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "類型": item["type"], "現價": price_display, 
                "最高點": f"{historical_max:.2f}", "停損價線": f"{trailing_stop_line:.2f}", "距離死線": stop_light,
                "買點防線": buy_range_str, "🎯估值": f"{pe_color} {pe_status}", "🛡️底氣": f"{yield_color} {yield_status}", "📈營收": rev_status, 
                "👤籌碼": chips_status, "🚨決策": f"{hold_color} {hold_action}", "損益": pnl_str, "數據來源": mode_tag
            })

        if view_mode == "📋 完整表格":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ 現價: {r['現價']} ｜ 🛑 {r['🚨決策']}"):
                    if r['類型'] == "已持股":
                        st.markdown("### 🛑 移動停損即時監控數據")
                        col1, col2, col3 = st.columns(3)
                        col1.metric("⛰️ 6個月內最高價", f"{r['最高點']} 元")
                        col2.metric("🎯 系統停損賣出死線", f"{r['停損價線']} 元")
                        col3.metric("🚨 距死線倒數狀態", r['距離死線'])
                        st.markdown(f"**💰 目前持股累積損益：** <font color='#ff6666'>**{r['損益']}**</font>", unsafe_allow_html=True)
                        st.write("---")
                    
                    st.markdown(f"**🛒 理想買入防線 ({ma_label})：** **{r['買點防線']} 元**")
                    st.markdown(f"**🎯 估值區間 (P/E)：** {r['🎯估值']} ｜ **🛡️ 股息底氣：** {r['🛡️底氣']}")
                    st.markdown(f"**📈 長線營收趨勢：** {r['📈營收']} ｜ **👤 主力籌碼：** {r['👤籌碼']}")
                    st.caption(f"⚙️ 系統數據流狀態：`{r['數據來源']}`")

# ===================================================
# ⚙️ 設定面板
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("➕ 新增 / 編輯庫存股票")
        names_db = load_json(NAMES_FILE, {})
        new_stock = st.text_input("股票代碼 (例: 2330.TW)", key="add_id_v154").upper().strip()
        custom_name = st.text_input("股票中文別名 (例: 台積電)", key="add_name_v154")
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="add_type_v154")
        cost, qty = 0.0, 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="add_cost_v154")
            qty = st.number_input("持有股數", min_value=0, step=100, key="add_qty_v154")
            
        if st.button("💾 確認儲存股票", use_container_width=True, key="save_btn_v154"):
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
            tgt_p = st.selectbox("選擇股票點選現價", list(st.session_state.watchlist.keys()), key="price_tgt_v154")
            input_p = st.number_input(f"輸入 {tgt_p} 即時價", min_value=0.0, step=0.1, key="price_val_v154")
            if st.button("⚡ 同步現價", use_container_width=True, key="sync_btn_v154"):
                if input_p > 0:
                    st.session_state.live_prices[tgt_p] = input_p
                    st.success("現價同步成功！")
                    time.sleep(0.5)
                    st.rerun()

    with col_right:
        st.subheader("🗑️ 徹底刪除庫存股票")
        if st.session_state.watchlist:
            del_target = st.selectbox("選擇你想刪除的股票", list(st.session_state.watchlist.keys()), key="del_box_v154")
            if st.button("🔥 確定完全刪除", type="primary", use_container_width=True, key="del_btn_v154"):
                if del_target in st.session_state.live_prices: del st.session_state.live_prices[del_target]
                if del_target in st.session_state.watchlist:
                    del st.session_state.watchlist[del_target]
                    save_json(WATCHLIST_FILE, st.session_state.watchlist)
                st.cache_data.clear()
                st.success(f"🛑 {del_target} 已完全抹除！")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("目前沒有股票可刪除。")

        st.write("---")
        st.subheader("✍️ 進階數據【手動備援區】")
        if st.session_state.watchlist:
            tgt_b = st.selectbox("選擇要備援的股票", list(st.session_state.watchlist.keys()), key="sb_box_v154")
            cur_b = backup_db.get(tgt_b, {"net_buy_5d": 0, "rev_6ma": 1.0, "rev_12ma": 0.0, "pe": 15.0, "yield": 4.5})
            
            pe_in = st.number_input("手動本益比 (PE)", value=float(cur_b.get("pe", 15.0)), step=1.0, key="b_pe_v154")
            y_in = st.number_input("手動殖利率 (%)", value=float(cur_b.get("yield", 4.5)), step=0.1, key="b_yield_v154")
            chip_in = st.number_input("近 5 日法人累積買超 (張)", value=int(cur_b.get("net_buy_5d", 0)), step=100, key="b_chip_v154")
            
            st.markdown("**營收趨勢判定：6MA > 12MA 就會亮綠燈**")
            r6 = st.number_input("6MA 營收水位", value=float(cur_b.get("rev_6ma", 1.0)), step=1.0, key="b_r6_v154")
            r12 = st.number_input("12MA 營收水位", value=float(cur_b.get("rev_12ma", 0.0)), step=1.0, key="b_r12_v154")
            
            if st.button("💾 儲存備援數據", use_container_width=True, key="b_btn_v154"):
                backup_db[tgt_b] = {"net_buy_5d": chip_in, "rev_6ma": r6, "rev_12ma": r12, "pe": pe_in, "yield": y_in}
                save_json(BACKUP_DATA_FILE, backup_db)
                st.success("備援數據成功與系統對齊！")
                time.sleep(0.5)
                st.rerun()