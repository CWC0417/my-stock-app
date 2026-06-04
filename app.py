import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

st.set_page_config(page_title="安全抗封鎖戰情室 v9.0", layout="wide")

# 🔑 在這裡設定你的專屬密碼
MY_PRIVATE_PASSWORD = "36333948" 

WATCHLIST_FILE = "my_watchlist_v9.json"

# 驗證密碼狀態
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 密碼鎖畫面
if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center;'>🔒 歡迎來到個人私密看盤戰情室</h2>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="請輸入密碼...")
        if st.button("確認解鎖 🔓", use_container_width=True):
            if input_password == MY_PRIVATE_PASSWORD:
                st.session_state.authenticated = True
                st.success("密碼正確，正在開門...")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，拒絕存取！")
    st.stop()

# ===================================================
# 🔓 核心資料安全抓取區 (快取防禦機制)
# ===================================================

# 🛠️ 核心防禦：設定 5 分鐘 (300秒) 快取，5分鐘內重複刷網頁絕不驚動 Yahoo
@st.cache_data(ttl=300)
def fetch_clean_stock_data(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    # 只抓取歷史價格數據 (最輕量、絕對不會被 Yahoo 擋)
    hist = stock.history(period="60d")
    if hist.empty:
        raise ValueError("找不到該股票的歷史數據，請檢查代碼是否正確。")
    return hist

# 讀取自選股庫存資料
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

# --- 網頁介面設計 ---
st.title("⚡ 盤中即時自選股與精準買入價導航面板")
st.caption("🔒 密碼安全防護中 │ 🛡️ 已啟用抗封鎖快取機制 (數據每 5 分鐘自動刷新)")

# 側邊欄控制台
with st.sidebar:
    st.header("🛠️ 戰情室控制台")
    if st.button("🔒 登出系統"):
        st.session_state.authenticated = False
        st.rerun()
    st.write("---")
    
    # 功能一：盤中即時價格輸入
    st.subheader("🔥 盤中即時價覆蓋")
    if st.session_state.watchlist:
        target_stock = st.selectbox("選擇要更新現價的股票", list(st.session_state.watchlist.keys()))
        input_p = st.number_input(f"輸入 {target_stock} 目前券商即時價", min_value=0.0, step=0.1, key="live_p_input")
        if st.button("⚡ 立即同步現價並重新計算"):
            if input_p > 0:
                st.session_state.live_prices[target_stock] = input_p
                st.success(f"已成功覆蓋 {target_stock} 價格為 {input_p} 元！")
                st.rerun()
        if st.button("🔄 清除所有手動現價"):
            st.session_state.live_prices = {}
            st.clear_cache() # 手動還原時順便清空快取刷新
            st.rerun()
            
    st.write("---")
    # 功能二：新增股票
    st.subheader("➕ 新增股票")
    new_stock = st.text_input("輸入股票代碼", placeholder="例如: 2454.TW").upper().strip()
    stock_type = st.selectbox("狀態類別", ["觀察中 (尚未買進)", "已持股"])
    cost = 0.0
    qty = 0
    if stock_type == "已持股":
        cost = st.number_input("您的買入成本價 (元)", min_value=0.0, step=0.1)
        qty = st.number_input("持有股數", min_value=0, step=100)
    if st.button("確認儲存"):
        if new_stock:
            st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty}
            save_watchlist(st.session_state.watchlist)
            st.clear_cache() # 新增股票時清空快取，確保新股票能抓到資料
            st.success(f"成功加入 {new_stock}！")
            st.rerun()
            
    st.write("---")
    # 功能三：刪除股票
    st.subheader("🗑️ 刪除特定股票")
    for stock_id in list(st.session_state.watchlist.keys()):
        if st.button(f"❌ 刪除 {stock_id}", key=f"del_{stock_id}"):
            if stock_id in st.session_state.live_prices:
                del st.session_state.live_prices[stock_id]
            del st.session_state.watchlist[stock_id]
            save_watchlist(st.session_state.watchlist)
            st.rerun()

# 主畫面
if not st.session_state.watchlist:
    st.warning("目前監控清單空空如也，請在左側選單新增股票！")
else:
    st.subheader("📋 價格對照與買入時機動態評估表")
    
    rows = []
    for ticker_symbol, item in st.session_state.watchlist.items():
        try:
            # 使用我們設計的超輕量快取函數
            hist = fetch_clean_stock_data(ticker_symbol)
            
            # 從歷史數據的最後一筆直接抓取最新網路收盤價
            net_price = hist['Close'].iloc[-1]
            
            # 決定最終顯示價格
            if ticker_symbol in st.session_state.live_prices:
                price = st.session_state.live_prices[ticker_symbol]
                price_display = f"⚡ {price:.2f} (即時)"
            else:
                price = net_price
                price_display = f"🌐 {price:.2f} (網路)"
            
            # 計算20MA(月線)
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            current_ma20 = hist['MA20'].iloc[-1]
            
            # 計算建議買入價格區間
            if current_ma20 > 0:
                buy_price_lower = current_ma20
                buy_price_upper = current_ma20 * 1.05
                buy_range_str = f"{buy_price_lower:.2f} ~ {buy_price_upper:.2f} 元"
                
                if price < buy_price_lower:
                    price_eval = f"🔴 跌破月線 (空頭勿接刀)"
                elif buy_price_lower <= price <= buy_price_upper:
                    price_eval = f"🟢 正值買點 (黃金支撐區)"
                else:
                    price_eval = f"🟡 股價偏高 (建議等回檔)"
            else:
                buy_range_str = "計算中..."
                price_eval = "資料不足"

            # 損益動態計算
            if item["type"] == "已持股":
                my_cost = item["cost"]
                my_qty = item["qty"]
                pnl = (price - my_cost) * my_qty
                roi = (pnl / (my_cost * my_qty) * 100) if my_cost > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                stop_loss = f"{my_cost * 0.9:.2f} 元"
                take_profit = f"{my_cost * 1.2:.2f} 元"
            else:
                pnl_str = "—"
                stop_loss = f"{price * 0.9:.2f} 元"
                take_profit = f"{price * 1.2:.2f} 元"
                
            rows.append({
                "代碼": ticker_symbol,
                "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display,
                "🛒 建議買入價區間": buy_range_str,
                "🎯 當前價位評估": price_eval,
                "目前總損益": pnl_str,
                "當前20MA(月線)": f"{current_ma20:.2f} 元",
                "🔴 策略停損點": stop_loss,
                "🟢 策略停利點": take_profit
            })
        except Exception as e:
            rows.append({
                "代碼": ticker_symbol,
                "狀態": "錯誤",
                "當前價格 (元)": "讀取失敗",
                "🛒 建議買入價區間": "請稍後再試",
                "🎯 當前價位評估": f"⚠️ Yahoo暫時封鎖此伺服器: {str(e)[:30]}",
                "目前總損益": "—",
                "當前20MA(月線)": "—",
                "🔴 策略停損點": "—",
                "🟢 策略停利點": "—"
            })
            
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)