import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

# ===================================================
# 🔑 系統密碼與檔案設定
# ===================================================
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v16.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v16.json"

st.set_page_config(page_title="個人化智慧看盤系統 v16.6", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v16.6)</h3>", unsafe_allow_html=True)
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

# 2. 資料讀寫工具
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding='utf-8') as f: return json.load(f)
        except: return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, "w", encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {})

backup_db = load_json(BACKUP_DATA_FILE, {}) 
names_db = load_json(NAMES_FILE, {})

# 3. yfinance 核心價格引擎 (含防阻擋機制)
@st.cache_data(ttl=300)
def fetch_clean_stock_data(ticker_symbol):
    try:
        time.sleep(0.3)  # 🛡️ 增加 0.3 秒延遲，避免連續請求被 Yahoo 阻擋
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="6mo") 
        
        if hist.empty or len(hist) < 30: 
            return None, {}, "歷史資料不足或遭阻擋"
            
        info = stock.info
        pe = info.get("trailingPE") or info.get("forwardPE")
        yield_pct = info.get("dividendYield")
        if yield_pct: yield_pct = round(yield_pct * 100, 2)
        
        return hist, {"pe": pe, "yield": yield_pct}, "OK"
    except Exception as e: 
        return None, {}, str(e)

def get_display_name(ticker):
    return names_db.get(ticker, ticker)

# ===================================================
# 📊 介面啟動與主選單
# ===================================================
st.title("📊 個人化智慧看盤系統 v16.6")
st.caption("🪵 6MA / 12MA 戰略版 │ ☁️ 雲端備援機制 │ 🛡️ 抗 Yahoo 阻擋機制與完整管理後台")

if st.button("🔄 強制清除股價快取 (若股價卡住請點此)"):
    st.cache_data.clear()
    st.rerun()

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"])

# ===================================================
# 🟢 核心戰情分頁
# ===================================================
with main_tab:
    if not st.session_state.watchlist:
        st.info("💡 目前系統內沒有股票。請切換到「設定後台」新增股票或上傳備份檔！")
    else:
        ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_166")
        st.write("---")
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol)
            
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0, "pe": 0.0, "yield": 0.0})
            
            if hist is None: 
                st.warning(f"⚠️ 暫時無法取得 【{stock_name} ({ticker_symbol})】 的即時股價資料。已切換為純備援顯示。原因：{status}")
                continue # 若連線失敗，跳過畫圖，保留警告

            # 綜合數據 (優先用即時，若無則用手動備援)
            pe = val_data.get("pe") if val_data.get("pe") is not None else b_item.get("pe", 0.0)
            yield_pct = val_data.get("yield") if val_data.get("yield") is not None else b_item.get("yield", 0.0)
            net_buy_5d = b_item.get("net_buy_5d", 0)
            rev_6ma = b_item.get("rev_6ma", 0.0) 
            rev_12ma = b_item.get("rev_12ma", 0.0) 

            # 狀態燈號計算
            if pe == 0:
                pe_status, pe_color = "不適用 (ETF)", "⚪"
            else:
                pe_status = f"便宜 ({pe:.1f})" if pe < 12 else (f"合理 ({pe:.1f})" if pe <= 20 else f"昂貴 ({pe:.1f})")
                pe_color = "🟢" if pe < 12 else ("🟡" if pe <= 20 else "🔴")
            
            if yield_pct == 0:
                yield_status, yield_color = "無配息", "⚪"
            else:
                yield_status = f"高殖利率 ({yield_pct:.1f}%)" if yield_pct >= 4.5 else f"一般 ({yield_pct:.1f}%)"
                yield_color = "🟢" if yield_pct >= 4.5 else "🟡"
            
            if rev_6ma == 0 and rev_12ma == 0:
                rev_status = "⚪ 不適用 (ETF/無營收)"
            elif rev_6ma >= rev_12ma:
                rev_status = f"🟢 多頭 (6MA {rev_6ma:,.2f} > 12MA {rev_12ma:,.2f})"
            else:
                rev_status = f"🔴 衰退 (6MA {rev_6ma:,.2f} < 12MA {rev_12ma:,.2f})"
            
            if net_buy_5d > 1500: chips_status = f"🟢 主力大買 (+{net_buy_5d}張)"
            elif net_buy_5d < -1500: chips_status = f"🔴 主力大賣 ({net_buy_5d}張)"
            else: chips_status = f"🟡 籌碼震盪 ({net_buy_5d}張)"

            # 價格計算
            price = hist['Close'].iloc[-1]
            historical_max = float(hist['Close'].max())
            stop_base = max(item["cost"], historical_max