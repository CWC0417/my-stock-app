import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

st.set_page_config(page_title="盤中即時價與買入價位導航 v7.0", layout="wide")

WATCHLIST_FILE = "my_watchlist_v7.json"

# 讀取自選股庫存資料
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return {
        "2330.TW": {"type": "觀察中", "cost": 0.0, "qty": 0},
        "2317.TW": {"type": "觀察中", "cost": 0.0, "qty": 0}
    }

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)

# 初始化狀態
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "live_prices" not in st.session_state:
    st.session_state.live_prices = {}

# --- 網頁介面設計 ---
st.title("⚡ 盤中即時自選股與精準買入價導航面板")
st.caption("✅ 自動計算月線黃金買入價 0%~5% 區間 │ ✅ 支援盤中即時價覆蓋 │ ✅ 秒級同步判斷目前價位")

# 側邊欄：管理清單與盤中即時價
with st.sidebar:
    st.header("🛠️ 戰情室控制台")
    
    # 功能一：盤中即時價格輸入
    st.subheader("🔥 盤中即時價覆蓋 (開盤用)")
    if st.session_state.watchlist:
        target_stock = st.selectbox("選擇要更新現價的股票", list(st.session_state.watchlist.keys()))
        input_p = st.number_input(f"輸入 {target_stock} 目前券商即時價", min_value=0.0, step=0.1, key="live_p_input")
        if st.button("⚡ 立即同步現價並重新計算"):
            if input_p > 0:
                st.session_state.live_prices[target_stock] = input_p
                st.success(f"已成功覆蓋 {target_stock} 價格為 {input_p} 元！")
                st.rerun()
        if st.button("🔄 清除所有手動現價 (還原網路價)"):
            st.session_state.live_prices = {}
            st.rerun()
            
    st.write("---")
    
    # 功能二：新增股票
    st.subheader("➕ 新增股票 / 修改庫存")
    new_stock = st.text_input("輸入股票代碼", placeholder="例如: 2454.TW 或 TSLA").upper().strip()
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
            st.success(f"成功加入/更新 {new_stock}！")
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
    st.subheader("📋 價格對照與買入時機動態評功表")
    
    rows = []
    for ticker_symbol, item in st.session_state.watchlist.items():
        try:
            stock = yf.Ticker(ticker_symbol)
            info = stock.info
            name = info.get('shortName', ticker_symbol)
            
            # 決定價格
            net_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            if ticker_symbol in st.session_state.live_prices:
                price = st.session_state.live_prices[ticker_symbol]
                price_display = f"⚡ {price:.2f} (即時)"
            else:
                price = net_price
                price_display = f"🌐 {price:.2f} (網路)"
            
            # 技術面數據計算 (月線)
            hist = stock.history(period="60d")
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            current_ma20 = hist['MA20'].iloc[-1] if not hist.empty else 0
            
            # --- 🎯 核心：計算建議買入價格區間 (月線 ~ 月線 + 5%) ---
            if current_ma20 > 0:
                buy_price_lower = current_ma20
                buy_price_upper = current_ma20 * 1.05
                buy_range_str = f"{buy_price_lower:.2f} ~ {buy_price_upper:.2f} 元"
                
                # 比對現價與建議買入價
                if price < buy_price_lower:
                    price_eval = f"🔴 跌破月線 (空頭勿接刀)"
                elif buy_price_lower <= price <= buy_price_upper:
                    price_eval = f"🟢 正值買點 (黃金支撐區)"
                else:
                    price_eval = f"🟡 股價偏高 (建議等回檔)"
            else:
                buy_range_str = "計算中..."
                price_eval = "資料不足"

            # 損益與出場點動態計算
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
                "名稱": name,
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
            st.error(f"無法抓取 {ticker_symbol} 資料。")
            
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

st.markdown("""
---
### 💡 戰情室看盤教學：
1. **🛒 建議買入價區間**：這是系統幫你動態算出的「安全無痛進場區」。只要當前價格掉進這個區間內，欄位就會亮起 **「🟢 正值買點」**。
2. **手動覆蓋的好處**：開盤時，網路抓到的價格可能有延遲。此時只要在左側輸入你手機看盤軟體看到的當下現價，系統就會**立刻拿最新現價去跟建議買入價對照**，讓你秒懂現在到底能不能敲單！
""")