import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

# 檔名定義
WATCHLIST_FILE = "my_watchlist_v10.json"
NAMES_FILE = "my_stock_names.json"

# 載入名稱對照表
def load_names():
    if os.path.exists(NAMES_FILE):
        with open(NAMES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_names(names_dict):
    with open(NAMES_FILE, "w") as f:
        json.dump(names_dict, f)

# 核心顯示名稱函數
def get_display_name(ticker):
    names = load_names()
    return names.get(ticker, ticker) # 有自訂名稱就顯示，沒的話顯示代號

# ... (中間密碼與資料載入邏輯同前) ...

# ===================================================
# ⚙️ 頁籤二：股票管理控制台 (加入名稱編輯區)
# ===================================================
with control_tab:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📝 自訂股票名稱")
        names_db = load_names()
        target_stock = st.selectbox("選擇要改名的股票", list(st.session_state.watchlist.keys()))
        new_name = st.text_input(f"設定 {target_stock} 的別名", value=names_db.get(target_stock, ""))
        
        if st.button("💾 儲存別名", use_container_width=True):
            names_db[target_stock] = new_name
            save_names(names_db)
            st.success(f"已將 {target_stock} 命名為 {new_name}")
            st.rerun()
            
        st.write("---")
        # ... (其餘新增股票、刪除股票邏輯同前)