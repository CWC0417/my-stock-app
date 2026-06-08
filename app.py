import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

# 🔑 系統密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v15.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v15.json"

st.set_page_config(page_title="個人化智慧看盤系統 v15.8", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v15.8)</h3>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="輸入密碼...", key="login_pwd")
        if st.button("確認解鎖 🔓", use_container_width=True):
            if input_password == MY_PRIVATE_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("❌ 密碼錯誤")
    st.stop()

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

# 3. yfinance 核心價格引擎
@st.cache_data(ttl=300)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        if len(hist) < 30: return None, {}, "歷史資料不足"
        info = stock.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        yield_pct = info.get("dividendYield")
        if yield_pct: yield_pct = round(yield_pct * 100, 2)
        return hist, {"pe": pe, "yield": yield_pct}, "OK"
    except: return None, {}, "Error"

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 介面啟動 ---
st.title("📊 個人化智慧看盤系統 v15.8")
st.caption("🪵 ETF 友善相容版 │ 自動識別 0 值的無營收/無本益比狀態 │ 排除燈號誤判")

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"])
backup_db = load_json(BACKUP_DATA_FILE, {}) 

with main_tab:
    if not st.session_state.watchlist:
        st.info("目前清單空空如也，請切換到「設定後台」新增股票！")
    else:
        ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_158")
        st.write("---")
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol)
            if hist is None: continue

            # 🛠️ 預設值全面改為 0.0，利於新股票或 ETF 初始化
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "m_rev_1": 0.0, "m_rev_2": 0.0, "pe": 0.0, "yield": 0.0})
            
            net_buy_5d = b_item.get("net_buy_5d", 0)
            m_rev_1 = b_item.get("m_rev_1", 0.0) 
            m_rev_2 = b_item.get("m_rev_2", 0.0) 

            # 嚴謹的資料排除流向
            pe = val_data.get("pe") if val_data.get("pe") is not None else b_item.get("pe", 0.0)
            yield_pct = val_data.get("yield") if val_data.get("yield") is not None else b_item.get("yield", 0.0)

            # 🧠 修正本益比 0 值的 ETF 誤判
            if pe == 0:
                pe_status = "不適用 (ETF)"
                pe_color = "⚪"
            else:
                pe_status = f"便宜 ({pe:.1f})" if pe < 12 else (f"合理 ({pe:.1f})" if pe <= 20 else f"昂貴 ({pe:.1f})")
                pe_color = "🟢" if pe < 12 else ("🟡" if pe <= 20 else "🔴")
            
            # 🧠 修正殖利率 0 值的無配息狀態
            if yield_pct == 0:
                yield_status = "無配息"
                yield_color = "⚪"
            else:
                yield_status = f"高殖利率 ({yield_pct:.1f}%)" if yield_pct >= 4.5 else f"一般 ({yield_pct:.1f}%)"
                yield_color = "🟢" if yield_pct >= 4.5 else "🟡"
            
            # 🧠 修正營收同時為 0 值的 ETF 誤判
            if m_rev_1 == 0 and m_rev_2 == 0:
                rev_status = "⚪ 不適用 (ETF/無營收)"
            elif m_rev_1 >= m_rev_2:
                rev_status = f"🟢 多頭 (本月 {m_rev_1:,.0f} > 上月 {m_rev_2:,.0f})"
            else:
                rev_status = f"🔴 衰退 (本月 {m_rev_1:,.0f} < 上月 {m_rev_2:,.0f})"
            
            if net_buy_5d > 1500: chips_status = f"🟢 主力大買 (+{net_buy_5d}張)"
            elif net_buy_5d < -1500: chips_status = f"🔴 主力大賣 ({net_buy_5d}張)"
            else: chips_status = f"🟡 籌碼震盪 ({net_buy_5d}張)"

            price = hist['Close'].iloc[-1]
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

            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            target_ma = hist['MA20'].iloc[-1] if "20MA" in ma_strategy else hist['MA60'].iloc[-1]
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA"
            buy_range_str = f"{target_ma:.2f} ~ {target_ma * 1.05:.2f}" if pd.notna(target_ma) else "計算中"
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
            else: pnl_str, hold_action, stop_light, hold_color = "—", "觀察中", "—", "⚪"
                
            with st.expander(f"📈 {stock_name} ({ticker_symbol}) ｜ 現價: 🌐 {price:.2f} ｜ 🛑 {hold_color} {hold_action}"):
                if item["type"] == "已持股":
                    st.markdown("### 🛑 移動停損即時監控數據")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("⛰ *6個月最高價*", f"{historical_max:.2f} 元")
                    col2.metric("🎯 *停損賣出線*", f"{trailing_stop_line:.2f} 元")
                    col3.metric("🚨 *死線倒數*", stop_light)
                    st.markdown(f"**💰 目前持股累積損益：** **{pnl_str}**")
                    st.write("---")
                
                st.markdown(f"**🛒 理想買入防線 ({ma_label})：** **{buy_range_str} 元**")
                st.markdown(f"**🎯 估值區間 (P/E)：** {pe_color} {pe_status} ｜ **🛡 股息底氣：** {yield_color} {yield_status}")
                st.markdown(f"**📈 月營收趨勢：** {rev_status} ｜ **👤 主力籌碼：** {chips_status}")

# ===================================================
# ⚙ 設定面板 (v15.8 記憶體與 0 值防呆優化版)
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.subheader("➕ 新增 / 編輯庫存股票")
        names_db = load_json(NAMES_FILE, {})
        new_stock = st.text_input("股票代碼 (例: 0050.TW)", key="add_stock_code_input").upper().strip()
        custom_name = st.text_input("股票中文別名 (例: 元大台灣50)", key="add_stock_name_input")
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="add_stock_type_select")
        cost, qty = 0.0, 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="add_stock_cost_input")
            qty = st.number_input("持有股數", min_value=0, step=100, key="add_stock_qty_input")
            
        if st.button("💾 確認儲存股票", use_container_width=True, key="save_stock_btn"):
            if new_stock:
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
                save_json(WATCHLIST_FILE, st.session_state.watchlist)
                if custom_name: names_db[new_stock] = custom_name; save_json(NAMES_FILE, names_db)
                st.cache_data.clear(); st.success(f"股票 {new_stock} 儲存成功！"); time.sleep(0.5); st.rerun()

    with col_right:
        st.subheader("✍ 填寫手動數據")
        if st.session_state.watchlist:
            tgt_b = st.selectbox("選擇要備援的股票", list(st.session_state.watchlist.keys()), key="select_target_stock_box")
            
            # 預設值調整為 0.0 方便直接留空
            cur_b = backup_db.get(tgt_b, {"net_buy_5d": 0, "m_rev_1": 0.0, "m_rev_2": 0.0, "pe": 0.0, "yield": 0.0})
            
            pe_in = st.number_input("手動本益比 (PE) *若為 ETF 請填 0*", value=float(cur_b.get("pe", 0.0)), key=f"pe_in_{tgt_b}")
            y_in = st.number_input("手動殖利率 (%) *可輸入最新預估值*", value=float(cur_b.get("yield", 0.0)), key=f"yield_in_{tgt_b}")
            chip_in = st.number_input("近 5 日法人累積買超 (張)", value=int(cur_b.get("net_buy_5d", 0)), key=f"chip_in_{tgt_b}")
            
            st.write("---")
            st.markdown("#### 📈 營收數據備援（直接填寫網站數值）")
            rev1_in = st.number_input("最新月份營收 *若為 ETF 請填 0*", value=float(cur_b.get("m_rev_1", 0.0)), key=f"rev1_in_{tgt_b}")
            rev2_in = st.number_input("前個月份營收 *若為 ETF 請填 0*", value=float(cur_b.get("m_rev_2", 0.0)), key=f"rev2_in_{tgt_b}")
            
            if st.button("💾 儲存並同步到卡片", use_container_width=True, key=f"save_backup_btn_{tgt_b}"):
                backup_db[tgt_b] = {"net_buy_5d": chip_in, "m_rev_1": rev1_in, "m_rev_2": rev2_in, "pe": pe_in, "yield": y_in}
                save_json(BACKUP_DATA_FILE, backup_db)
                st.success(f"✨ {tgt_b} 專屬數據同步成功！")
                time.sleep(0.5); st.rerun()