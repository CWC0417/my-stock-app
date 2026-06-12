import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta

# ===================================================
# 🔑 系統密碼與 API 設定
# ===================================================
MY_PRIVATE_PASSWORD = "36333948" 
FINMIND_TOKEN ="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiMzQzNTY4MTIiLCJlbWFpbCI6IngxMjN5ejg3QGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjB9.X3YH2qYzM84f3iJeD0vendPFoUP7nvrONOyXvkfDdWQ" 

WATCHLIST_FILE = "my_watchlist_v18.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v18.json"

st.set_page_config(page_title="個人化智慧看盤系統 v18.0", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 1. 密碼鎖
if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v18.0)</h3>", unsafe_allow_html=True)
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
            with open(filepath, "r", encoding='utf-8') as f: 
                return json.load(f)
        except: 
            return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, "w", encoding='utf-8') as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_json(WATCHLIST_FILE, {})

backup_db = load_json(BACKUP_DATA_FILE, {}) 
names_db = load_json(NAMES_FILE, {})

# 3. 🚀 FinMind 核心引擎 (v18.0 穩定版)
@st.cache_data(ttl=3600)
def fetch_clean_stock_data(ticker_symbol, token):
    # 自動清理代碼，去除後綴只留純數字
    clean_id = ticker_symbol.replace(".TW", "").replace(".TWO", "").replace(".V", "")
    
    price_start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
    val_start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    
    url = "https://api.finmindtrade.com/api/v4/data"
    
    try:
        res_price = requests.get(url, params={
            "dataset": "TaiwanStockPrice",
            "data_id": clean_id,
            "start_date": price_start_date,
            "token": token
        }, timeout=10)
        
        price_data = res_price.json()
        if price_data.get("msg") != "success" or not price_data.get("data"):
            return None, {}, "代碼或 API 限制"
            
        df_price = pd.DataFrame(price_data["data"])
        df_price.rename(columns={'close': 'Close', 'date': 'Date'}, inplace=True)
        df_price['Date'] = pd.to_datetime(df_price['Date'])
        df_price.set_index('Date', inplace=True)
        
        res_val = requests.get(url, params={
            "dataset": "TaiwanStockPER",
            "data_id": clean_id,
            "start_date": val_start_date,
            "token": token
        }, timeout=10)
        
        val_data_json = res_val.json()
        pe, yield_pct = None, None
        
        if val_data_json.get("msg") == "success" and val_data_json.get("data"):
            df_val = pd.DataFrame(val_data_json["data"])
            if not df_val.empty:
                latest_val = df_val.iloc[-1]
                pe = latest_val.get("PE_ratio")
                yield_pct = latest_val.get("dividend_yield")
        
        return df_price, {"pe": pe, "yield": yield_pct}, "OK"
        
    except Exception as e: 
        return None, {}, str(e)

def get_display_name(ticker):
    return names_db.get(ticker, ticker)

# ===================================================
# 📊 介面啟動與主選單
# ===================================================
st.title("📊 個人化智慧看盤系統 v18.0")

if st.button("🔄 強制清除股價快取"):
    st.cache_data.clear()
    st.rerun()

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"])

with main_tab:
    if not st.session_state.watchlist:
        st.info("💡 請至「設定後台」新增股票。")
    else:
        ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_180")
        st.write("---")
        
        for ticker_symbol, item in st.session_state.watchlist.items():
            stock_name = get_display_name(ticker_symbol)
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol, FINMIND_TOKEN)
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0, "pe": 0.0, "yield": 0.0})
            
            if hist is None: 
                st.warning(f"⚠️ {stock_name} ({ticker_symbol}) 暫時無法連線。")
                continue

            # 數據邏輯
            pe = b_item.get("pe", 0.0) if b_item.get("pe", 0.0) > 0 else (val_data.get("pe") if pd.notna(val_data.get("pe")) else 0.0)
            yield_pct = b_item.get("yield", 0.0) if b_item.get("yield", 0.0) > 0 else (val_data.get("yield") if pd.notna(val_data.get("yield")) else 0.0)
            
            # 修正後的停損邏輯
            price = float(hist['Close'].iloc[-1])
            historical_max = float(hist['Close'].max())
            stop_base = max(item["cost"], historical_max) # 已修正右括號
            trailing_stop_line = stop_base * 0.90 
            
            # 顯示卡片 (略，保持你原本設計)
            with st.expander(f"📈 {stock_name} ({ticker_symbol}) ｜ 現價: {price:.2f}"):
                st.write(f"停損賣出線：{trailing_stop_line:.2f}")
                st.write(f"本益比：{pe}")

with control_tab:
    # 這裡放你的設定後台代碼
    st.write("設定區")