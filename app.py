import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="量化智慧戰情室 v12.2", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "1234" 
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 密碼鎖畫面
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

# ===================================================
# 💾 檔案讀寫邏輯
# ===================================================
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return default_data

def save_json(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {"2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}})
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# ===================================================
# 🔓 資料抓取核心 (防禦 Yahoo 限流機制)
# ===================================================
@st.cache_data(ttl=600) # 延長快取到 10 分鐘，減少對 Yahoo 的請求頻率
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="90d") 
        if hist.empty:
            return None, "找不到數據或遭限流"
        return hist, "OK"
    except Exception as e:
        return None, str(e)

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 頂端標題區 ---
st.title("🚀 智慧自選股戰情室 v12.2")
st.caption("🛡️ 已修復系統錯誤 │ 📱 支援手機卡片模式")

main_tab, control_tab = st.tabs(["📈 核心戰情面板", "⚙️ 股票管理控制台"])

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.warning("目前清單空空如也，請切換到「⚙️ 控制台」新增股票！")
    else:
        view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格 (電腦)"], horizontal=True)
        st.write("---")
        
        rows = []
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, status = fetch_clean_stock_data(ticker_symbol)
            
            if hist is None:
                # 處理 Yahoo 阻擋或無資料的情況
                rows.append({
                    "代碼": ticker_symbol, "名稱": stock_name, "狀態": "錯誤", "當前價格 (元)": "連線失敗",
                    "🛒 建議買入價區間 (20MA)": "—", "🎯 當前價位評估": f"⚠️ {status[:30]}",
                    "📊 季線與量能": "—", "🛡️ 10%動態移動停損點": "—", "🚨 持股警報動態": "請稍後再試", "目前總損益": "—"
                })
                continue

            # 正常計算邏輯
            net_price = hist['Close'].iloc[-1]
            if ticker_symbol in st.session_state.live_prices:
                price = st.session_state.live_prices[ticker_symbol]
                price_display = f"⚡ {price:.2f} (即時)"
            else:
                price = net_price
                price_display = f"🌐 {price:.2f} (網路)"
            
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
            
            current_ma20 = hist['MA20'].iloc[-1]
            current_ma60 = hist['MA60'].iloc[-1]
            prev_ma60 = hist['MA60'].iloc[-2] if len(hist) > 1 else current_ma60
            current_vol = hist['Volume'].iloc[-1]
            avg_vol = hist['VolMA20'].iloc[-1]
            
            if pd.notna(current_ma20) and current_ma20 > 0:
                buy_lower = current_ma20
                buy_upper = current_ma20 * 1.05
                buy_range_str = f"{buy_lower:.2f} ~ {buy_upper:.2f} 元"
                if price < buy_lower: price_eval = "🔴 跌破月線 (觀望)"
                elif buy_lower <= price <= buy_upper: price_eval = "🟢 黃金支撐 (買點)"
                else: price_eval = "🟡 股價偏高 (等回檔)"
            else:
                buy_range_str = "計算中..."
                price_eval = "資料不足"
            
            ma60_trend = "季線向上📈" if current_ma60 > prev_ma60 else "季線下彎📉"
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1
            if vol_ratio >= 1.5: vol_status = "🔥 量能爆發"
            elif vol_ratio <= 0.5: vol_status = "💤 窒息量"
            else: vol_status = "均量"
            
            historical_max = hist['Close'].max()
            peak_price = max(item["cost"], historical_max, price)
            trailing_stop_line = peak_price * 0.90
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                hold_action = "🚨 觸發移動停損！" if price < trailing_stop_line else "🍏 續抱安全區"
            else:
                pnl_str = "—"
                hold_action = "觀察中"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, 
                "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display, "🛒 建議買入價區間 (20MA)": buy_range_str,
                "🎯 當前價位評估": price_eval, "📊 季線與量能": f"{ma60_trend} ｜ {vol_status}",
                "🛡️ 10%動態移動停損點": f"{trailing_stop_line:.2f} 元", "🚨 持股警報動態": hold_action,
                "目前總損益": pnl_str
            })

        # 渲染畫面
        if view_mode == "📋 完整表格 (電腦)":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ {r['當前價格 (元)']} ｜ {r['狀態']}"):
                    st.markdown(f"**🎯 價位評估：** {r['🎯 當前價位評估']}")
                    st.markdown(f"**🛒 買入區間 (20MA)：** {r['🛒 建議買入價區間 (20MA)']}")
                    st.markdown(f"**📊 體質狀態：** {r['📊 季線與量能']}")
                    st.markdown(f"**🛡️ 移動停損防線：** <font color='red'>**{r['🛡️ 10%動態移動停損點']}**</font>", unsafe_allow_html=True)
                    st.markdown(f"**🚨 抱股警報：** {r['🚨 持股警報動態']}")
                    st.markdown(f"**💰 目前損益：** {r['目前總損益']}")

# ===================================================
# ⚙️ 頁籤二：股票管理控制台
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📝 自訂股票名稱")
        names_db = load_json(NAMES_FILE, {})
        if st.session_state.watchlist:
            target_stock_name = st.selectbox("選擇要改名的股票", list(st.session_state.watchlist.keys()), key="name_target")
            new_name = st.text_input(f"設定 {target_stock_name} 的別名", value=names_db.get(target_stock_name, ""))
            if st.button("💾 儲存別名", use_container_width=True):
                names_db[target_stock_name] = new_name
                save_json(NAMES_FILE, names_db)
                st.success("名稱已更新！")
                time.sleep(1)
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
                    time.sleep(1)
                    st.rerun()
            if st.button("🔄 清除所有手動現價", use_container_width=True):
                st.session_state.live_prices = {}
                st.cache_data.clear() # 💡 已修復的新版清除快取語法
                st.rerun()

    with col_right:
        st.subheader("➕ 新增股票 (上櫃加 .TWO)")
        new_stock = st.text_input("股票代碼", placeholder="例如: 2330.TW").upper().strip()
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"])
        cost = 0.0
        qty = 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1)
            qty = st.number_input("持有股數", min_value=0, step=100)
        if st.button("💾 確認儲存股票", use_container_width=True):
            if new_stock:
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
                save_json(WATCHLIST_FILE, st.session_state.watchlist)
                st.cache_data.clear() # 💡 已修復的新版清除快取語法
                st.success(f"已加入 {new_stock}")
                time.sleep(1)
                st.rerun()

        st.write("---")
        st.subheader("🗑️ 刪除庫存股票")
        if not st.session_state.watchlist:
            st.write("無股票可刪除")
        for stock_id in list(st.session_state.watchlist.keys()):
            if st.button(f"❌ 刪除 {stock_id}", key=f"del_{stock_id}", use_container_width=True):
                if stock_id in st.session_state.live_prices:
                    del st.session_state.live_prices[stock_id]
                del st.session_state.watchlist[stock_id]
                save_json(WATCHLIST_FILE, st.session_state.watchlist)
                st.cache_data.clear() # 💡 已修復的新版清除快取語法
                st.rerun()