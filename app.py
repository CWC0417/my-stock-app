import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

st.set_page_config(page_title="量化智慧戰情室 v13.0 策略雷達版", layout="wide")

# 🔑 密碼與檔案設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"

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

# ===================================================
# 🔓 資料抓取核心 (拉長到 6個月以計算 60MA 扣抵值)
# ===================================================
@st.cache_data(ttl=600)
def fetch_clean_stock_data(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") # 👈 關鍵：必須要有 6個月資料才能算 60MA 扣抵值
        if len(hist) < 65:
            return None, "歷史資料不足(至少需65個交易日)"
        return hist, "OK"
    except Exception as e:
        return None, str(e)

def get_display_name(ticker):
    names = load_json(NAMES_FILE, {})
    return names.get(ticker, ticker)

# --- 頂端標題區 ---
st.title("⚡ 智慧自選股戰情室 v13.0 策略雷達版")
st.caption("📈 已匯入：量縮洗盤判定 │ 🎯 季線扣抵值預測 │ 🚨 3天3%雙重停損防線")

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
                rows.append({
                    "代碼": ticker_symbol, "名稱": stock_name, "狀態": "錯誤", "當前價格 (元)": "連線失敗",
                    "🎯 戰術策略評估": f"⚠️ {status[:20]}", "🛡️ 移動停損防線": "—", "🚨 持股警報動態": "請稍後再試", "目前總損益": "—"
                })
                continue

            # 基礎價格計算
            net_price = hist['Close'].iloc[-1]
            price = st.session_state.live_prices.get(ticker_symbol, net_price)
            price_display = f"⚡ {price:.2f} (即時)" if ticker_symbol in st.session_state.live_prices else f"🌐 {price:.2f} (網路)"
            
            # 技術指標計算
            hist['MA20'] = hist['Close'].rolling(window=20).mean()
            hist['MA60'] = hist['Close'].rolling(window=60).mean()
            hist['VolMA5'] = hist['Volume'].rolling(window=5).mean()
            hist['VolMA20'] = hist['Volume'].rolling(window=20).mean()
            
            current_ma20 = hist['MA20'].iloc[-1]
            current_ma60 = hist['MA60'].iloc[-1]
            prev_ma60 = hist['MA60'].iloc[-2]
            
            # 1. 季線扣抵值判定 (看60個交易日前的價格)
            deduction_price = hist['Close'].iloc[-60]
            if price > deduction_price:
                deduction_status = "🟢 扣低值 (季線續揚力道強)"
            else:
                deduction_status = "🔴 扣高值 (季線恐走平下彎)"
                
            # 2. 量縮洗盤判定 (短均量 < 長均量)
            v_ma5 = hist['VolMA5'].iloc[-1]
            v_ma20 = hist['VolMA20'].iloc[-1]
            volume_status = "🟢 成功量縮" if v_ma5 < v_ma20 else "🟡 尚未量縮"
            
            # 3. K線止跌判定
            open_p = hist['Open'].iloc[-1]
            close_p = hist['Close'].iloc[-1]
            high_p = hist['High'].iloc[-1]
            low_p = hist['Low'].iloc[-1]
            k_range = high_p - low_p
            lower_shadow = min(open_p, close_p) - low_p
            
            is_stop_drop = False
            if k_range > 0 and (lower_shadow / k_range) >= 0.4:
                k_status = "🟢 出現長下影線 (止跌)"
                is_stop_drop = True
            elif close_p > open_p:
                k_status = "🟢 收紅K棒 (止跌)"
                is_stop_drop = True
            else:
                k_status = "🔴 黑K下殺中 (觀望)"
            
            # 綜合策略買點評估 (價格回檔到季線 0%~5% 區間)
            buy_lower = current_ma60
            buy_upper = current_ma60 * 1.05
            
            if buy_lower <= price <= buy_upper:
                if is_stop_drop and v_ma5 < v_ma20:
                    strategy_eval = "🔥 終極買點：量縮止跌守季線！"
                else:
                    strategy_eval = f"🟡 進入季線守備區 ({buy_lower:.1f}~{buy_upper:.1f})，等量縮止跌"
            elif price < buy_lower:
                strategy_eval = "❌ 跌破季線：暫不伸手接刀"
            else:
                strategy_eval = "⚪ 股價偏高：耐心等待拉回"

            # 4. 警報與雙重停損監控 (檢查過去3天是否都跌破季線3%)
            hist['Below_3Pct'] = hist['Close'] < (hist['MA60'] * 0.97)
            failed_days = hist['Below_3Pct'].iloc[-3:].sum() # 計算過去三天有幾天符合跌破 3%
            
            historical_max = hist['Close'].max()
            peak_price = max(item["cost"], historical_max, price)
            trailing_stop_line = peak_price * 0.90 # 原本的 10% 移動停損
            
            if item["type"] == "已持股":
                pnl = (price - item["cost"]) * item["qty"]
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)"
                
                # 停損優先級判斷
                if failed_days == 3:
                    hold_action = "🚨 價格停損：連續3天跌破季線3%！"
                elif current_ma60 < prev_ma60:
                    hold_action = "⚠️ 趨勢停損：季線已開始下彎！"
                elif price < trailing_stop_line:
                    hold_action = "🚨 移動停損：跌破高點拉回10%防線！"
                else:
                    hold_action = "🍏 續抱全區 (季線趨勢向上)"
            else:
                pnl_str = "—"
                hold_action = "觀察中"
                
            rows.append({
                "代碼": ticker_symbol, "名稱": stock_name, "狀態": "已持股" if item["type"] == "已持股" else "觀察中",
                "當前價格 (元)": price_display, "🎯 戰術策略評估": strategy_eval,
                "量能狀態": volume_status, "K線型態": k_status, "季線扣抵預測": deduction_status,
                "🛡️ 10%移動停損防線": f"{trailing_stop_line:.2f} 元", "🚨 持股警報動態": hold_action, "目前總損益": pnl_str
            })

        # 渲染畫面
        if view_mode == "📋 完整表格 (電腦)":
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            for r in rows:
                with st.expander(f"📈 {r['名稱']} ({r['代碼']}) ｜ {r['當前價格 (元)']}"):
                    st.markdown(f"**🎯 核心戰術評估：** <font color='orange'>**{r['🎯 戰術策略評估']}**</font>", unsafe_allow_html=True)
                    st.markdown(f"**📊 量能洗盤檢測：** {r['量能狀態']}")
                    st.markdown(f"**🕯️ K線止跌訊號：** {r['K線型態']}")
                    st.markdown(f"**🔮 季線扣抵預測：** {r['季線扣抵預測']}")
                    st.markdown(f"**🚨 抱股/停損警報：** {r['🚨 持股警報動態']}")
                    st.markdown(f"**💰 目前持股損益：** {r['目前總損益']}")
                    st.caption(f"移動停損點：{r['🛡️ 10%移動停損防線']}")

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
                st.cache_data.clear()
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
                st.cache_data.clear()
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
                st.cache_data.clear()
                st.rerun()