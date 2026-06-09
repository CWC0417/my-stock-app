import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
import time

# 🔑 系統設定
MY_PRIVATE_PASSWORD = "36333948" 
WATCHLIST_FILE = "my_watchlist_v15.json"
NAMES_FILE = "my_stock_names.json"
BACKUP_DATA_FILE = "my_stock_backup_data_v15.json"

st.set_page_config(page_title="個人化智慧看盤系統 v16.5", layout="wide")

if "authenticated" not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v16.5)</h3>", unsafe_allow_html=True)
    input_password = st.text_input("請輸入管理員密碼", type="password")
    if st.button("確認解鎖 🔓"):
        if input_password == MY_PRIVATE_PASSWORD: st.session_state.authenticated = True; st.rerun()
        else: st.error("❌ 密碼錯誤")
    st.stop()

def load_json(filepath, default_data):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f)

if "watchlist" not in st.session_state: st.session_state.watchlist = load_json(WATCHLIST_FILE, {})

# --- 介面 ---
st.title("📊 個人化智慧看盤系統 v16.5")
if st.button("🔄 強制清除股價快取"): st.cache_data.clear(); st.rerun()

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"])

with control_tab:
    st.subheader("🛠️ 股票管理與刪除")
    # 選擇股票進行刪除
    target_to_del = st.selectbox("選擇要刪除的股票", [""] + list(st.session_state.watchlist.keys()))
    if st.button("🗑️ 確認刪除此股票"):
        if target_to_del in st.session_state.watchlist:
            del st.session_state.watchlist[target_to_del]
            save_json(WATCHLIST_FILE, st.session_state.watchlist)
            st.success(f"已刪除 {target_to_del}")
            time.sleep(0.5); st.rerun()

    st.write("---")
    st.subheader("➕ 新增股票")
    new_code = st.text_input("股票代碼 (例: 2330.TW)").upper().strip()
    if st.button("💾 新增"):
        if new_code:
            st.session_state.watchlist[new_code] = {"type": "觀察中", "cost": 0, "qty": 0}
            save_json(WATCHLIST_FILE, st.session_state.watchlist)
            st.rerun()

    st.write("---")
    # 原有的備份與進階數據區域保留
    st.subheader("✍ 進階數據備援")
    # ... (此處可沿用您原來的備份代碼)