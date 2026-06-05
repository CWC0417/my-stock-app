import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
import datetime

# 🌟 務必確保此行是第一個 Streamlit 指令
st.set_page_config(page_title="個人化智慧看盤系統 v14.1", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data.json" # 儲存手動備援數據

# 💡 提示：如果不想被雲端共用 IP 限制，可以去 https://finmindtrade.com/ 免費註冊會員並把 Token 貼在下方
FINMIND_TOKEN = "" 

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖檢查
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室</h3>", unsafe_allow_html=True)
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

# 2. 基礎檔案讀寫函數
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)

# 初始化庫存清單
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {"2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}})
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# 3. Yfinance 價格資料抓取
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 65: return None, "歷史資料不足"
        return hist, "OK"
    except Exception as e:
        return None, str(e)

# 4. FinMind API 自動化核心 (內建極致抗塞車防護)
@st.cache_data(ttl=1800) # 快取半小時，防狂刷網頁被鎖
def fetch_tw_api_data(ticker_symbol, token=""):
    tw_id = ticker_symbol.split(".")[0]
    today = datetime.date.today()
    start_date_chips = (today - datetime.timedelta(days=12)).strftime("%Y-%m-%d")
    start_date_rev = (today - datetime.timedelta(days=65)).strftime("%Y-%m-%d")
    
    res_dict = {"f_buy": None, "t_buy": None, "rev_yoy": None, "api_ok": False}
    
    # 建立請求參數
    base_params = {"data_id": tw_id}
    if token: base_params["token"] = token
        
    try:
        # 抓取三大法人買賣超
        p_chips = base_params.copy()
        p_chips.update({"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "start_date": start_date_chips})
        req_chips = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_chips, timeout=4).json()
        
        if req_chips.get("msg") == "success" and len(req_chips.get("data", [])) > 0:
            df_chips = pd.DataFrame(req_chips["data"])
            latest_date = df_chips['date'].max()
            df_latest = df_chips[df_chips['date'] == latest_date]
            f_data = df_latest[df_latest['name'] == '外資及陸資(不含外資自營商)']['buy_sell'].sum()
            t_data = df_latest[df_latest['name'] == '投信']['buy_sell'].sum()
            res_dict["f_buy"] = int(f_data / 1000)
            res_dict["t_buy"] = int(t_data / 1000)
            res_dict["api_ok"] = True

        # 抓取每月營收
        p_rev = base_params.copy()
        p_rev.update({"dataset": "TaiwanStockMonthRevenue", "start_date": start_date_rev})
        req_rev = requests.get("https://api.finmindtrade.com/api/v4/data", params=p_rev, timeout=4).json()
        
        if req_rev.get("msg") == "success" and len(req_rev.get("data", [])) > 0:
            df_rev = pd.DataFrame(req_rev["data"])
            res_dict["rev_yoy"] = round(df_rev.iloc[-1].get("revenue_YearOverYearRatio", 0.0), 2)
            res_dict["api_ok"] = True
            
    except:
        res_dict["api_ok"] = False # 連線失敗或被擋，觸發手動備援
        
    return res_dict

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 介面架構生成 ---
st.title("⚡ 個人化智慧看盤系統 v14.1")
st.caption("🤖 雲端生產線特製版 │ 🔄 API 流量受限時自動切換「手動備援模式」 │ 🎯 20/60MA 雙防線")

# 這裡完美定義兩個頁籤，徹底解決 NameError
main_tab, control_tab = st.tabs(["📈 核心戰情面板", "⚙️ 股票管理控制台"])

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.warning("目前清單空空如也，請切換到「⚙️ 控制台」新增股票！")
    else:
        col_ctrl1, col_ctrl2 = st.columns([1, 1])
        with col_ctrl1:
            view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格 (電腦)"], horizontal=True, key="v_mode")
        with col_ctrl2:
            ma_strategy = st.radio("買點防線策略", ["波段操作 (20MA 月線)", "長線大底 (60MA 季線)"], horizontal=True, key="ma_strat")
            
        st.write("---")
        rows = []
        backup_db = load_json(BACKUP_DATA_FILE, {}) # 讀取手動輸入作為備援
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, status = fetch_clean_stock_data(ticker_symbol)
            if hist is None: continue

            # 🤖 嘗試呼叫自動化 API
            api_res = fetch_tw_api_data(ticker_symbol, token=FINMIND_TOKEN)
            backup_item = backup_db.get(ticker_symbol, {"f_buy": 0, "t_buy": 0, "rev_yoy": 0.0})
            
            # 🔄 智慧判定：如果 API 壞了，直接用手動備援資料！
            if api_res["api_ok"] and api_res["f_buy"] is not None:
                f_buy, t_buy, rev_yoy = api_res["f_buy"], api_res["t_buy"], api_res["rev_yoy"]
                mode_tag = "🤖 自動"
            else:
                f_buy, t_buy, rev_yoy = backup_item["f_buy"], backup_item["t_buy"], backup_item["rev_yoy"]
                mode_tag = "✍️ 備援"

            # 📊 籌碼與營收燈號判讀
            total_inst = f_buy + t_buy
            if total_inst > 500: chips_status = f"🟢 法人買超 (+{total_inst}張)"
            elif total_inst < -500: chips_status = f"🔴 法人賣超 ({total_inst}張)"
            else: chips_status = f"🟡 籌碼中性 ({total_inst}張)"
                
            if rev_yoy >= 10.0: fund_status = f"🟢 營收高成長 (+{rev_yoy}%)"
            elif rev_yoy < 0.0: fund_status = f"🔴 營收衰退中 ({rev_yoy}%)"
            else: fund_status = f"🟡 營收平穩 (+{rev_yoy}%)"

            # 均線技術計算
            net_price = hist['Close'].iloc[-1]
            price = st.session_state.live_prices.get(ticker_symbol, net_price)
            price_display = f"⚡ {price:.2f} (即時)" if ticker_symbol in st.session_state.live_prices else f"🌐 {price:.2f} (網路)"
            
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            hist['VolMA5'] = hist['Volume'].rolling(window=5).mean()
            hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
            
            target_ma = hist['MA20'].iloc[-1] if "20MA" in ma_strategy else hist['MA60'].iloc[-1]
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA"
            
            if pd.notna(target_ma) and target_ma > 0:
                buy_range_str = f"{target_ma:.2f} ~ {target_ma * 1.05:.2f} 元"
            else:
                buy_range_str = "計算中..."

            v_ma5, v_ma20 = hist['VolMA5'].iloc[-1], hist['VolMA20'].iloc[-1]
            volume_status = "🟢 成功量縮" if v_ma5 < v_ma20 else "🟡 尚未量縮"
            
            open_p, close_p, high_p, low_p = hist['Open'].iloc[-1], hist['Close'].iloc[-1], hist['High'].iloc[-1], hist['Low'].iloc[-1]
            k_range = high_p - low_p
            is_stop_drop = (k_range > 0 and ((min(open_p, close_p) - low_p) / k_range) >= 0.4) or (close_p > open_p)
            k_status = "🟢 出現止跌訊號" if is_stop_drop else "🔴 黑K下殺中"
            
            # 停損計算
            historical_max = hist['Close'].max()
            trailing_stop_line = max(item["cost"], historical_max, price) * 0.90 
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                hold_action = "🚨 移動停損防線！" if price < trailing_stop_line else "🍏 續抱安全區"
            else:
                pnl_str, hold_action = "—", "觀察中"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "狀態": item["type"], "當前價格 (元)": price_display, 
                f"🛒 買入區間 ({ma_label})": buy_range_str, "👤 法人籌碼": chips_status, "📈 最新營收": fund_status,
                "量能狀態": volume_status, "K線型態": k_status, "🚨 警報": hold_action, "目前總損益": pnl_str, "來源": mode_tag
            })

        # 渲染畫面
        if view_mode == "📋 完整表格 (電腦)":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ {r['當前價格 (元)']} ｜ 🛑 {r['🚨 警報']}"):
                    st.markdown(f"**🛒 買入區間 ({ma_label})：** <font color='#66ff66'>**{r[f'🛒 買入區間 ({ma_label})']}**</font>", unsafe_allow_html=True)
                    st.markdown(f"---")
                    st.markdown(f"**👤 法人籌碼：** {r['👤 法人籌碼']} `[{r['來源']}]`")
                    st.markdown(f"**📈 最新營收：** {r['📈 最新營收']} `[{r['來源']}]`")
                    st.markdown(f"**📊 技術指標：** {r['量能狀態']} ｜ {r['K線型態']}")
                    st.markdown(f"**💰 持股損益：** {r['目前總損益']}")

# ===================================================
# ⚙️ 頁籤二：股票管理控制台
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("✍️ 籌碼與營收【手動備援輸入區】")
        st.caption("💡 當雲端 API 被流量限制亮紅燈時，系統會自動改抓這裡你輸入的數字來判斷紅綠燈！")
        
        if st.session_state.watchlist:
            backup_db = load_json(BACKUP_DATA_FILE, {})
            target_b = st.selectbox("選擇要手動備援的股票", list(st.session_state.watchlist.keys()), key="sb")
            cur_b = backup_db.get(target_b, {"f_buy": 0, "t_buy": 0, "rev_yoy": 0.0})
            
            in_f = st.number_input("外資近幾日買賣超 (張)", value=int(cur_b.get("f_buy", 0)), step=100, key="if")
            in_t = st.number_input("投信近幾日買賣超 (張)", value=int(cur_b.get("t_buy", 0)), step=100, key="it")
            in_rev = st.number_input("最新單月營收年增率 (YoY %)", value=float(cur_b.get("rev_yoy", 0.0)), step=1.0, key="ir")
            
            if st.button("💾 儲存備援數據", use_container_width=True):
                backup_db[target_b] = {"f_buy": in_f, "t_buy": in_t, "rev_yoy": in_rev}
                save_json(BACKUP_DATA_FILE, backup_db)
                st.success("備援數據儲存成功！若 API 被阻擋，系統將自動以此數值進行研判。")
                time.sleep(0.5)
                st.rerun()

        st.write("---")
        st.subheader("🔥 盤中即時價覆蓋")
        if st.session_state.watchlist:
            target_stock_price = st.selectbox("選擇股票點選現價", list(st.session_state.watchlist.keys()), key="p_tgt")
            input_p = st.number_input(f"輸入 {target_stock_price} 即時價", min_value=0.0, step=0.1, key="ip_val")
            if st.button("⚡ 同步現價", use_container_width=True):
                if input_p > 0:
                    st.session_state.live_prices[target_stock_price] = input_p
                    st.success("現價同步成功！")
                    time.sleep(0.5)
                    st.rerun()

    with col_right:
        st.subheader("➕ 新增 / 編輯庫存股票")
        names_db = load_json(NAMES_FILE, {})
        new_stock = st.text_input("股票代碼 (例: 2330.TW)", placeholder="2330.TW", key="ns_id").upper().strip()
        custom_name = st.text_input("股票中文別名 (例: 台積電)", placeholder="台積電", key="ns_nm")
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="ns_tp")
        cost, qty = 0.0, 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="ns_cs")
            qty = st.number_input("持有股數", min_value=0, step=100, key="ns_qt")
            
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
        st.subheader("🗑️ 刪除庫存股票")
        if st.session_state.watchlist:
            for stock_id in list(st.session_state.watchlist.keys()):
                if st.button(f"❌ 刪除 {stock_id}", key=f"del_{stock_id}", use_container_width=True):
                    if stock_id in st.session_state.live_prices: del st.session_state.live_prices[stock_id]
                    del st.session_state.watchlist[stock_id]
                    save_json(WATCHLIST_FILE, st.session_state.watchlist)
                    st.cache_data.clear()
                    st.rerun()