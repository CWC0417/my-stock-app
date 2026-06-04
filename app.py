import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

st.set_page_config(page_title="終極量化智慧戰情室 v10.0", layout="wide")

# 🔑 在這裡設定你的專屬密碼 (可自由修改)
MY_PRIVATE_PASSWORD = "1234" 

# 使用新版專屬資料庫檔案，避免版本衝突
WATCHLIST_FILE = "my_watchlist_v10.json"

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

# 🛡️ 擴展到 90 天天數，以便完美計算 60MA (季線) 趨勢
@st.cache_data(ttl=300)
def fetch_clean_stock_data(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    hist = stock.history(period="90d") 
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
st.title("🚀 終極量化智慧自選股戰情室 v10.0")
st.caption("🔒 安全防護中 │ 🛡️ 抗封鎖快取 5分鐘 │ 📈 整合移動停損、季線趨勢與量能爆發辨識")

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
            st.cache_data.clear() 
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
            st.cache_data.clear() 
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
    st.subheader("📋 策略指標與動態停損導航面板")
    
    rows = []
    for ticker_symbol, item in st.session_state.watchlist.items():
        try:
            # 抓取90天輕量數據
            hist = fetch_clean_stock_data(ticker_symbol)
            net_price = hist['Close'].iloc[-1]
            
            # 確定當前市價
            if ticker_symbol in st.session_state.live_prices:
                price = st.session_state.live_prices[ticker_symbol]
                price_display = f"⚡ {price:.2f} (即時)"
            else:
                price = net_price
                price_display = f"🌐 {price:.2f} (網路)"
            
            # --- 技術指標量化計算 ---
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
            
            current_ma20 = hist['MA20'].iloc[-1]
            current_ma60 = hist['MA60'].iloc[-1]
            prev_ma60 = hist['MA60'].iloc[-2] if len(hist) > 1 else current_ma60
            
            current_vol = hist['Volume'].iloc[-1]
            avg_vol = hist['VolMA20'].iloc[-1]
            
            # 1. 月線買入區間評估
            if current_ma20 > 0:
                buy_lower = current_ma20
                buy_upper = current_ma20 * 1.05
                buy_range_str = f"{buy_lower:.2f} ~ {buy_upper:.2f} 元"
                
                if price < buy_lower:
                    price_eval = "🔴 跌破月線 (觀望接刀)"
                elif buy_lower <= price <= buy_upper:
                    price_eval = "🟢 黃金支撐 (正值買點)"
                else:
                    price_eval = "🟡 股價偏高 (建議等回檔)"
            else:
                buy_range_str = "計算中..."
                price_eval = "資料不足"
            
            # 2. 季線趨勢 與 20日均量爆發辨識
            ma60_trend = "季線翻揚📈" if current_ma60 > prev_ma60 else "季線下彎📉"
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1
            if vol_ratio >= 1.5:
                vol_status = "🔥 量能爆發"
            elif vol_ratio <= 0.5:
                vol_status = "💤 窒息量"
            else:
                vol_status = "均量"
            
            tech_tactics = f"{ma60_trend} ｜ {vol_status}"
            
            # 3. 核心：10% 移動停損防線計算 (追隨歷史與現價最高峰)
            historical_max = hist['Close'].max()
            peak_price = max(item["cost"], historical_max, price) # 成本、網路最高、手動輸入最高，三者取最大
            trailing_stop_line = peak_price * 0.90 # 從最高點撤退 10% 
            
            # 4. 持股動態動態監控
            if item["type"] == "已持股":
                my_cost = item["cost"]
                my_qty = item["qty"]
                pnl = (price - my_cost) * my_qty
                roi = (pnl / (my_cost * my_qty) * 100) if my_cost > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                
                if price < trailing_stop_line:
                    hold_action = "🚨 觸發移動停損！分批出場"
                else:
                    hold_action = "🍏 安全防禦線內，續抱"
            else:
                pnl_str = "—"
                hold_action = "觀察中 (無持股)"
                
            rows.append({
                "代碼": ticker_symbol,
                "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display,
                "🛒 建議買入價區間 (20MA)": buy_range_str,
                "🎯 當前價位評估": price_eval,
                "📊 季線趨勢 ｜ 盤中量能": tech_tactics,
                "🛡️ 10%動態移動停損點": f"{trailing_stop_line:.2f} 元",
                "🚨 持股警報動態": hold_action,
                "目前總損益": pnl_str
            })
        except Exception as e:
            rows.append({
                "代碼": ticker_symbol, "狀態": "錯誤", "當前價格 (元)": "失敗",
                "🛒 建議買入價區間 (20MA)": "—", "🎯 當前價位評估": f"⚠️ 錯誤: {str(e)[:20]}",
                "📊 季線趨勢 ｜ 盤中量能": "—", "🛡️ 10%動態移動停損點": "—",
                "🚨 持股警報動態": "—", "目前總損益": "—"
            })
            
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)