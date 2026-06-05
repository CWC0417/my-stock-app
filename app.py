import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="量化智慧戰情室 v13.3 數據研判版", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"
EXTRA_FILE = "my_stock_extra_v2.json" # 換新檔案避免與舊版文字格式衝突

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室</h3>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="輸入密碼...", autocomplete="one-time-code")
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

# 資料抓取核心
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 65:
            return None, "歷史資料不足"
        return hist, "OK"
    except Exception as e:
        return None, str(e)

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 頂端標題區 ---
st.title("⚡ 智慧自選股戰情室 v13.3")
st.caption("🤖 數據自動研判系統 │ 🎯 動態 MA 買點切換 │ 🛡️ 雙重停損監控")

main_tab, control_tab = st.tabs(["📈 核心戰情面板", "⚙️ 股票管理控制台"])

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.warning("目前清單空空如也，請切換到「⚙️ 控制台」新增股票！")
    else:
        # 畫面控制選項
        col_ctrl1, col_ctrl2 = st.columns([1, 1])
        with col_ctrl1:
            view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格 (電腦)"], horizontal=True)
        with col_ctrl2:
            # 🎯 讓使用者自由切換要用 20MA 還是 60MA 當買點
            ma_strategy = st.radio("買點防線策略", ["波段操作 (20MA 月線)", "長線大底 (60MA 季線)"], horizontal=True)
            
        st.write("---")
        
        rows = []
        extra_db = load_json(EXTRA_FILE, {}) 
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, status = fetch_clean_stock_data(ticker_symbol)
            
            # 讀取生數據 (預設為 0)
            s_data = extra_db.get(ticker_symbol, {"f_buy": 0, "t_buy": 0, "rev_yoy": 0.0})
            
            # 🤖 系統自動判定邏輯 (籌碼與基本面)
            inst_net = s_data["f_buy"] + s_data["t_buy"]
            if inst_net > 500: chips_status = f"🟢 法人買超中 (+{inst_net}張)"
            elif inst_net < -500: chips_status = f"🔴 法人倒貨中 ({inst_net}張)"
            elif inst_net == 0: chips_status = "⚪ 無最新數據"
            else: chips_status = f"🟡 籌碼觀望中 ({inst_net}張)"
                
            if s_data["rev_yoy"] >= 10.0: fund_status = f"🟢 營收高成長 (+{s_data['rev_yoy']}%)"
            elif s_data["rev_yoy"] < 0.0: fund_status = f"🔴 營收衰退中 ({s_data['rev_yoy']}%)"
            elif s_data["rev_yoy"] == 0.0: fund_status = "⚪ 無最新數據"
            else: fund_status = f"🟡 營收平穩 (+{s_data['rev_yoy']}%)"
            
            if hist is None:
                continue # 簡化錯誤處理，直接跳過無資料的股票

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
            
            # 🎯 動態區間判定
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
            k_status = "🟢 出現止跌訊號 (紅K/下影線)" if is_stop_drop else "🔴 黑K下殺中 (觀望)"
            
            # 綜合策略評估
            if buy_lower <= price <= buy_upper:
                if is_stop_drop and (v_ma5 < v_ma20):
                    strategy_eval = f"🔥 終極買點：量縮止跌守 {ma_label}！"
                else:
                    strategy_eval = f"🟡 進入 {ma_label} 守備區，等待量縮止跌"
            elif price < buy_lower:
                strategy_eval = f"❌ 跌破 {ma_label}：暫不伸手接刀"
            else:
                strategy_eval = "⚪ 股價偏高：耐心等待拉回"

            # 停損計算 (跌破 60MA 或 高點回落 10%)
            historical_max = hist['Close'].max()
            peak_price = max(item["cost"], historical_max, price)
            trailing_stop_line = peak_price * 0.90 
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                if price < current_ma60 * 0.97: hold_action = "🚨 價格停損：跌破季線3%！"
                elif price < trailing_stop_line: hold_action = "🚨 移動停損：跌破高點拉回10%防線！"
                else: hold_action = "🍏 續抱安全區"
            else:
                pnl_str = "—"
                hold_action = "觀察中"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display, f"🛒 建議買入區間 ({ma_label})": buy_range_str, "🎯 戰術評估": strategy_eval,
                "👤 法人籌碼": chips_status, "📈 基本面營收": fund_status,
                "量能狀態": volume_status, "K線型態": k_status, 
                "🛡️ 移動停損": f"{trailing_stop_line:.2f} 元", "🚨 警報": hold_action, "目前總損益": pnl_str
            })

        # 渲染畫面
        if view_mode == "📋 完整表格 (電腦)":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ {r['當前價格 (元)']}"):
                    st.markdown(f"**🛒 買入區間 ({ma_label})：** <font color='#66ff66'>**{r[f'🛒 建議買入區間 ({ma_label})']}**</font>", unsafe_allow_html=True)
                    st.markdown(f"**🎯 戰術評估：** **{r['🎯 戰術評估']}**")
                    st.markdown(f"---")
                    st.markdown(f"**👤 籌碼 (自訂)：** {r['👤 法人籌碼']}")
                    st.markdown(f"**📈 營收 (自訂)：** {r['📈 基本面營收']}")
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
        st.subheader("📊 輸入客觀數據 (系統自動判斷)")
        if st.session_state.watchlist:
            extra_db = load_json(EXTRA_FILE, {})
            target_extra = st.selectbox("選擇股票輸入數據", list(st.session_state.watchlist.keys()), key="extra_target")
            current_extra = extra_db.get(target_extra, {"f_buy": 0, "t_buy": 0, "rev_yoy": 0.0})
            
            # 直接輸入生數據 (不包含情緒判斷)
            f_buy = st.number_input("近期外資買賣超 (張數)", value=current_extra.get("f_buy", 0), step=100)
            t_buy = st.number_input("近期投信買賣超 (張數)", value=current_extra.get("t_buy", 0), step=100)
            rev_yoy = st.number_input("最新單月營收年增率 (YoY %)", value=float(current_extra.get("rev_yoy", 0.0)), step=1.0)
            
            if st.button("💾 讓系統運算儲存", use_container_width=True):
                extra_db[target_extra] = {"f_buy": f_buy, "t_buy": t_buy, "rev_yoy": rev_yoy}
                save_json(EXTRA_FILE, extra_db)
                st.success(f"{target_extra} 數據已匯入，系統已更新燈號！")
                time.sleep(0.5)
                st.rerun()

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