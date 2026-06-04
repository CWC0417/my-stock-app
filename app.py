import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

st.set_page_config(page_title="量化智慧戰情室 v10.5 手機優化版", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "1234" 
WATCHLIST_FILE = "my_watchlist_v10.json"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 密碼鎖畫面 (已修正 Google 密碼強烈建議干擾)
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室</h3>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        input_password = st.text_input(
            "請輸入管理員密碼", 
            type="password", 
            placeholder="輸入密碼...", 
            autocomplete="one-time-code" # 👈 關鍵防干擾指令
        )
        if st.button("確認解鎖 🔓", use_container_width=True):
            if input_password == MY_PRIVATE_PASSWORD:
                st.session_state.authenticated = True
                st.success("解鎖成功！")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
    st.stop()

# ===================================================
# 🔓 資料抓取核心
# ===================================================
@st.cache_data(ttl=300)
def fetch_clean_stock_data(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    hist = stock.history(period="90d") 
    if hist.empty:
        raise ValueError("找不到該股票歷史數據。")
    return hist

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return {"2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}}

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# --- 頂端標題區 ---
st.title("🚀 智慧自選股戰情室 v10.5")
st.caption("🛡️ 快取防禦中 │ 📱 已全面優化行動裝置操作體驗")

# 📱 核心改裝：使用大頁籤取代隱藏的側邊欄，對手機極度友善
main_tab, control_tab = st.tabs(["📈 核心戰情面板", "⚙️ 股票管理控制台"])

# ===================================================
# 📈 頁籤一：核心戰情面板
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.warning("目前清單空空如也，請切換到「⚙️ 控制台」新增股票！")
    else:
        # 🌟 貼心功能：讓你在手機上自由切換看盤模式
        view_mode = st.radio("顯示模式", ["📱 手機卡片 (推薦)", "📋 完整表格 (電腦)"], horizontal=True)
        st.write("---")
        
        rows = []
        for ticker_symbol, item in st.session_state.watchlist.items():
            try:
                hist = fetch_clean_stock_data(ticker_symbol)
                net_price = hist['Close'].iloc[-1]
                
                if ticker_symbol in st.session_state.live_prices:
                    price = st.session_state.live_prices[ticker_symbol]
                    price_display = f"⚡ {price:.2f} (即時)"
                else:
                    price = net_price
                    price_display = f"🌐 {price:.2f} (網路)"
                
                # 指標計算
                hist['MA20'] = hist['Close'].rolling(window=20).mean()
                hist['MA60'] = hist['Close'].rolling(window=60).mean()
                hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
                
                current_ma20 = hist['MA20'].iloc[-1]
                current_ma60 = hist['MA60'].iloc[-1]
                prev_ma60 = hist['MA60'].iloc[-2] if len(hist) > 1 else current_ma60
                
                current_vol = hist['Volume'].iloc[-1]
                avg_vol = hist['VolMA20'].iloc[-1]
                
                # 買點評估
                if current_ma20 > 0:
                    buy_lower = current_ma20
                    buy_upper = current_ma20 * 1.05
                    buy_range_str = f"{buy_lower:.2f} ~ {buy_upper:.2f} 元"
                    
                    if price < buy_lower:
                        price_eval = "🔴 跌破月線 (觀望)"
                        eval_color = "red"
                    elif buy_lower <= price <= buy_upper:
                        price_eval = "🟢 黃金支撐 (買點)"
                        eval_color = "green"
                    else:
                        price_eval = "🟡 股價偏高 (等回檔)"
                        eval_color = "orange"
                else:
                    buy_range_str = "計算中..."
                    price_eval = "資料不足"
                    eval_color = "gray"
                
                # 趨勢量能
                ma60_trend = "季線向上📈" if current_ma60 > prev_ma60 else "季線下彎📉"
                vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1
                if vol_ratio >= 1.5:
                    vol_status = "🔥 量能爆發"
                elif vol_ratio <= 0.5:
                    vol_status = "💤 窒息量"
                else:
                    vol_status = "均量"
                
                # 移動停損
                historical_max = hist['Close'].max()
                peak_price = max(item["cost"], historical_max, price)
                trailing_stop_line = peak_price * 0.90
                
                # 損益監控
                if item["type"] == "已持股":
                    my_cost = item["cost"]
                    my_qty = item["qty"]
                    pnl = (price - my_cost) * my_qty
                    roi = (pnl / (my_cost * my_qty) * 100) if my_cost > 0 else 0
                    pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                    
                    if price < trailing_stop_line:
                        hold_action = "🚨 觸發移動停損！"
                        hold_color = "red"
                    else:
                        hold_action = "🍏 續抱安全區"
                        hold_color = "green"
                else:
                    pnl_str = "—"
                    hold_action = "無持股 (觀察中)"
                    hold_color = "gray"
                    
                rows.append({
                    "代碼": ticker_symbol, "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                    "當前價格 (元)": price_display, "🛒 建議買入價區間 (20MA)": buy_range_str,
                    "🎯 當前價位評估": price_eval, "📊 季線與量能": f"{ma60_trend} ｜ {vol_status}",
                    "🛡️ 10%動態移動停損點": f"{trailing_stop_line:.2f} 元", "🚨 持股警報動態": hold_action,
                    "目前總損益": pnl_str, "20MA": current_ma20, "eval_color": eval_color, "hold_color": hold_color
                })
            except Exception as e:
                rows.append({
                    "代碼": ticker_symbol, "狀態": "錯誤", "當前價格 (元)": "失敗",
                    "🛒 建議買入價區間 (20MA)": "—", "🎯 當前價位評估": f"⚠️ 錯誤: {str(e)[:15]}",
                    "📊 季線與量能": "—", "🛡️ 10%動態移動停損點": "—", "🚨 持股警報動態": "—", "目前總損益": "—",
                    "eval_color": "gray", "hold_color": "gray"
                })

        # --- 根據使用者的選擇渲染畫面 ---
        if view_mode == "📋 完整表格 (電腦)":
            df = pd.DataFrame(rows).drop(columns=["eval_color", "hold_color", "20MA"], errors="ignore")
            st.dataframe(df, use_container_width=True)
            
        else:
            # 🚀 專門為手機設計的垂直卡片流
            for r in rows:
                with st.expander(f"📈 {r['代碼']} ｜ {r['當前價格 (元)']} ｜ {r['狀態']}"):
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
        st.subheader("🔥 盤中即時價覆蓋")
        if st.session_state.watchlist:
            target_stock = st.selectbox("選擇股票", list(st.session_state.watchlist.keys()), key="f_target")
            input_p = st.number_input(f"輸入 {target_stock} 即時價", min_value=0.0, step=0.1)
            if st.button("⚡ 同步現價", use_container_width=True):
                if input_p > 0:
                    st.session_state.live_prices[target_stock] = input_p
                    st.success("價格已同步！")
                    st.rerun()
            if st.button("🔄 清除手動現價", use_container_width=True):
                st.session_state.live_prices = {}
                st.cache_data.clear()
                st.rerun()

        st.write("---")
        st.subheader("➕ 新增股票 (上櫃請加 .TWO)")
        new_stock = st.text_input("股票代碼", placeholder="例如: 2330.TW 或 8069.TWO").upper().strip()
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"])
        cost = 0.0
        qty = 0
        if stock_type == "已持股":
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1)
            qty = st.number_input("持有股數", min_value=0, step=100)
        if st.button("💾 確認儲存股票", use_container_width=True):
            if new_stock:
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
                save_watchlist(st.session_state.watchlist)
                st.cache_data.clear()
                st.success(f"已加入 {new_stock}")
                st.rerun()

    with col_right:
        st.subheader("🗑️ 刪除庫存股票")
        if not st.session_state.watchlist:
            st.write("無股票可刪除")
        for stock_id in list(st.session_state.watchlist.keys()):
            if st.button(f"❌ 刪除 {stock_id}", key=f"del_tab_{stock_id}", use_container_width=True):
                if stock_id in st.session_state.live_prices:
                    del st.session_state.live_prices[stock_id]
                del st.session_state.watchlist[stock_id]
                save_watchlist(st.session_state.watchlist)
                st.cache_data.clear()
                st.rerun()
                
        st.write("---")
        if st.button("🔒 安全登出系統", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()