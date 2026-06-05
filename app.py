import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time
import requests
import datetime

st.set_page_config(page_title="量化智慧戰情室 v14.0 全自動版", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室</h3>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="輸入密碼...")
        if st.button("確認解鎖 🔓", use_container_width=True):
            if input_password == MY_PRIVATE_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
    st.stop()

# 檔案讀寫
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        with open(filepath, "r") as f: return json.load(f)
    return default_data

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {"2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}})
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# ===================================================
# 🤖 自動化資料抓取核心 (Yfinance + FinMind)
# ===================================================
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 65: return None, "歷史資料不足"
        return hist, "OK"
    except Exception as e:
        return None, str(e)

# 🚀 新增：FinMind API 自動抓取台股籌碼與營收 (快取1小時，避免被阻擋)
@st.cache_data(ttl=3600)
def fetch_tw_fundamentals(ticker_symbol):
    tw_id = ticker_symbol.split(".")[0] # 去除 .TW 或 .TWO
    today = datetime.date.today()
    start_date_chips = (today - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    start_date_rev = (today - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    
    result = {"f_buy": 0, "t_buy": 0, "rev_yoy": 0.0, "status": "OK"}
    
    try:
        # 1. 抓取三大法人買賣超 (近幾天)
        url_chips = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={tw_id}&start_date={start_date_chips}"
        res_chips = requests.get(url_chips, timeout=5).json()
        if res_chips.get("msg") == "success" and len(res_chips.get("data", [])) > 0:
            df_chips = pd.DataFrame(res_chips["data"])
            # 取得最新一天的日期
            latest_date = df_chips['date'].max()
            df_latest = df_chips[df_chips['date'] == latest_date]
            
            f_data = df_latest[df_latest['name'] == '外資及陸資(不含外資自營商)']['buy_sell'].sum()
            t_data = df_latest[df_latest['name'] == '投信']['buy_sell'].sum()
            
            # FinMind 單位是「股」，換算成「張」
            result["f_buy"] = int(f_data / 1000)
            result["t_buy"] = int(t_data / 1000)

        # 2. 抓取每月營收 YoY
        url_rev = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={tw_id}&start_date={start_date_rev}"
        res_rev = requests.get(url_rev, timeout=5).json()
        if res_rev.get("msg") == "success" and len(res_rev.get("data", [])) > 0:
            df_rev = pd.DataFrame(res_rev["data"])
            latest_rev = df_rev.iloc[-1] # 取最新一個月
            result["rev_yoy"] = round(latest_rev.get("revenue_YearOverYearRatio", 0.0), 2)
            
    except Exception as e:
        result["status"] = "API連線失敗"
        
    return result

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 頂端標題區 ---
st.title("⚡ 智慧自選股戰情室 v14.0")
st.caption("🚀 全自動量化版 │ 🔗 FinMind API 串接籌碼營收 │ 🎯 動態 MA 買點切換")

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
            view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格 (電腦)"], horizontal=True)
        with col_ctrl2:
            ma_strategy = st.radio("買點防線策略", ["波段操作 (20MA 月線)", "長線大底 (60MA 季線)"], horizontal=True)
            
        st.write("---")
        
        rows = []
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, status = fetch_clean_stock_data(ticker_symbol)
            
            if hist is None: continue

            # 🤖 自動呼叫 API 抓取基本面與籌碼
            tw_data = fetch_tw_fundamentals(ticker_symbol)
            
            if tw_data["status"] == "OK":
                inst_net = tw_data["f_buy"] + tw_data["t_buy"]
                if inst_net > 500: chips_status = f"🟢 法人買超 (+{inst_net}張)"
                elif inst_net < -500: chips_status = f"🔴 法人賣超 ({inst_net}張)"
                elif inst_net == 0: chips_status = "⚪ 籌碼無動靜"
                else: chips_status = f"🟡 籌碼中性 ({inst_net}張)"
                    
                rev_yoy = tw_data["rev_yoy"]
                if rev_yoy >= 10.0: fund_status = f"🟢 營收高成長 (+{rev_yoy}%)"
                elif rev_yoy < 0.0: fund_status = f"🔴 營收衰退中 ({rev_yoy}%)"
                else: fund_status = f"🟡 營收平穩 (+{rev_yoy}%)"
            else:
                chips_status = "⚠️ 籌碼 API 錯誤"
                fund_status = "⚠️ 營收 API 錯誤"

            # 價格與均線計算
            net_price = hist['Close'].iloc[-1]
            price = st.session_state.live_prices.get(ticker_symbol, net_price)
            price_display = f"⚡ {price:.2f} (即時)" if ticker_symbol in st.session_state.live_prices else f"🌐 {price:.2f} (網路)"
            
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            hist['VolMA5'] = hist['Volume'].rolling(window=5).mean()
            hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
            
            current_ma20 = hist['MA20'].iloc[-1]
            current_ma60 = hist['MA60'].iloc[-1]
            
            target_ma = current_ma20 if "20MA" in ma_strategy else current_ma60
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA"
            
            if pd.notna(target_ma) and target_ma > 0:
                buy_lower = target_ma
                buy_upper = target_ma * 1.05
                buy_range_str = f"{buy_lower:.2f} ~ {buy_upper:.2f} 元"
            else:
                buy_range_str = "計算中..."

            # 技術與K線判定
            v_ma5 = hist['VolMA5'].iloc[-1]
            v_ma20 = hist['VolMA20'].iloc[-1]
            volume_status = "🟢 成功量縮" if v_ma5 < v_ma20 else "🟡 尚未量縮"
            
            open_p, close_p, high_p, low_p = hist['Open'].iloc[-1], hist['Close'].iloc[-1], hist['High'].iloc[-1], hist['Low'].iloc[-1]
            k_range = high_p - low_p
            lower_shadow = min(open_p, close_p) - low_p
            is_stop_drop = (k_range > 0 and (lower_shadow / k_range) >= 0.4) or (close_p > open_p)
            k_status = "🟢 出現止跌訊號" if is_stop_drop else "🔴 黑K下殺中"
            
            if buy_lower <= price <= buy_upper:
                if is_stop_drop and (v_ma5 < v_ma20): strategy_eval = f"🔥 終極買點：量縮止跌守 {ma_label}！"
                else: strategy_eval = f"🟡 進入 {ma_label} 守備區，等待量縮止跌"
            elif price < buy_lower: strategy_eval = f"❌ 跌破 {ma_label}：暫不伸手接刀"
            else: strategy_eval = "⚪ 股價偏高：耐心等待拉回"

            # 停損計算
            historical_max = hist['Close'].max()
            peak_price = max(item["cost"], historical_max, price)
            trailing_stop_line = peak_price * 0.90 
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                if price < current_ma60 * 0.97: hold_action = "🚨 價格停損：跌破季線3%！"
                elif price < trailing_stop_line: hold_action = "🚨 移動停損：跌破高點回落10%！"
                else: hold_action = "🍏 續抱安全區"
            else:
                pnl_str = "—"
                hold_action = "觀察中"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display, f"🛒 買入區間 ({ma_label})": buy_range_str, "🎯 戰術評估": strategy_eval,
                "👤 最新籌碼": chips_status, "📈 最新營收": fund_status,
                "量能狀態": volume_status, "K線型態": k_status, 
                "🛡️ 移動停損": f"{trailing_stop_line:.2f} 元", "🚨 警報": hold_action, "目前總損益": pnl_str
            })

        if view_mode == "📋 完整表格 (電腦)":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ {r['當前價格 (元)']}"):
                    st.markdown(f"**🛒 買入區間 ({ma_label})：** <font color='#66ff66'>**{r[f'🛒 買入區間 ({ma_label})']}**</font>", unsafe_allow_html=True)
                    st.markdown(f"**🎯 戰術評估：** **{r['🎯 戰術評估']}**")
                    st.markdown(f"---")
                    st.markdown(f"**👤 自動化籌碼：** {r['👤 最新籌碼']} *(外資+投信最新單日總和)*")
                    st.markdown(f"**📈 自動化營收：** {r['📈 最新營收']} *(上月營收 YoY)*")
                    st.markdown(f"**📊 技術與K線：** {r['量能狀態']} ｜ {r['K線型態']}")
                    st.markdown(f"---")
                    st.markdown(f"**🚨 警報：** {r['🚨 警報']}")
                    st.markdown(f"**💰 損益：** {r['目前總損益']}")

# ===================================================
# ⚙️ 頁籤二：股票管理控制台
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("🤖 系統自動化說明")
        st.info("""
        **目前的資料來源：**
        - **即時股價/均線/技術面**：美股 Yahoo Finance API 
        - **台股最新籌碼 (三大法人)**：FinMind API 自動抓取
        - **台股最新營收 (月營收 YoY)**：FinMind API 自動抓取
        
        *系統已接管所有基本面與籌碼面的判斷，您不再需要手動輸入資料！*
        """)

        st.write("---")
        st.subheader("🔥 盤中即時價覆蓋")
        if st.session_state.watchlist:
            target_stock_price = st.selectbox("選擇股票", list(st.session_state.watchlist.keys()), key="price_target")
            input_p = st.number_input(f"輸入 {target_stock_price} 即時價", min_value=0.0, step=0.1)
            if st.button("⚡ 同步現價", use_container_width=True):
                if input_p > 0:
                    st.session_state.live_prices[target_stock_price] = input_p
                    st.success("價格已同步！")
                    time.sleep(0.5)
                    st.rerun()

    with col_right:
        st.subheader("➕ 新增 / 編輯股票")
        names_db = load_json(NAMES_FILE, {})
        new_stock = st.text_input("股票代碼", placeholder="例如: 2330.TW").upper().strip()
        custom_name = st.text_input("自訂名稱 (選填)", placeholder="例如: 台積電")
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"])
        cost = 0.0
        qty = 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1)
            qty = st.number_input("持有股數", min_value=0, step=100)
            
        if st.button("💾 確認儲存", use_container_width=True):
            if new_stock:
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
                save_json(WATCHLIST_FILE, st.session_state.watchlist)
                if custom_name:
                    names_db[new_stock] = custom_name
                    save_json(NAMES_FILE, names_db)
                st.cache_data.clear()
                st.success(f"已儲存 {new_stock}")
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