import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os

# 設定頁面與檔案
WATCHLIST_FILE = "my_watchlist.json"
NAMES_FILE = "my_stock_names.json"

# 初始化設定 (檢查檔案是否存在)
def init_files():
    if not os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "w") as f: json.dump({"2330.TW": {"type": "已持股", "cost": 0, "qty": 0}}, f)
    if not os.path.exists(NAMES_FILE):
        with open(NAMES_FILE, "w") as f: json.dump({}, f)

init_files()

# 資料抓取與緩存 (優化版：降低對 Yahoo 的請求頻率)
@st.cache_data(ttl=600) # 快取時間拉長到 10 分鐘，避免 Too Many Requests
def get_stock_info(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")
    return hist

# 介面渲染
st.set_page_config(layout="wide")
st.title("📈 個人化智慧看盤系統")

# 使用 Tabs 來區分功能，解決 NameError 的問題
tab1, tab2 = st.tabs(["核心戰情", "設定"])

with tab1:
    st.write("這是你的股票面板...")
    # 這裡放入顯示卡片的邏輯

with tab2:
    st.write("這裡是編輯設定...")
    # 這裡放入編輯名稱的邏輯