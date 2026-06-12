import streamlit as st
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# ===================================================
# 🔑 系統密碼與 API / 雲端資料庫設定
# ===================================================
MY_PRIVATE_PASSWORD = "36333948"  #
FINMIND_TOKEN ="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiMzQzNTY4MTIiLCJlbWFpbCI6IngxMjN5ejg3QGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjB9.X3YH2qYzM84f3iJeD0vendPFoUP7nvrONOyXvkfDdWQ"  #

# ⚠️ 請把這邊替換成你 Google 試算表的「完整共用網址」
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1omZOMuXSG70iUC8gN5eCFuoLHnU6JnZsJ-PnKLVtneY/edit?usp=sharing"

st.set_page_config(page_title="個人化智慧看盤系統 v18.0 (雲端同步版)", layout="wide") #

if "authenticated" not in st.session_state: #
    st.session_state.authenticated = False #

# 1. 密碼鎖 #
if not st.session_state.authenticated: #
    st.markdown("<h3 style='text-align: center; margin-top: 50px;'>🔒 歡迎來到個人看盤戰情室 (v18.0)</h3>", unsafe_allow_html=True) #
    st.write("---") #
    col1, col2, col3 = st.columns([1, 2, 1]) #
    with col2: #
        input_password = st.text_input("請輸入管理員密碼", type="password", placeholder="輸入密碼...", key="login_pwd") #
        if st.button("確認解鎖 🔓", use_container_width=True): #
            if input_password == MY_PRIVATE_PASSWORD: #
                st.session_state.authenticated = True #
                st.rerun() #
            else:  #
                st.error("❌ 密碼錯誤") #
    st.stop() #

# ===================================================
# ☁️ 2. Google Sheets 雲端資料庫連線中樞
# ===================================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_system_data_from_cloud():
    """從 Google Sheets 讀取整張表，並轉換為原系統相容格式"""
    try:
        # ttl=0 代表即時讀取，不快取名單結構
        df = conn.read(spreadsheet=GSHEET_URL, worksheet="工作表1", ttl=0)
        
        # 過濾空白列與不小心抓到的標頭列
        if df.empty:
            return {}, {}, {}
            
        df = df.dropna(subset=["stock_id"])
        
        watchlist = {}
        names = {}
        backup = {}
        
        for _, row in df.iterrows():
            sid = str(row["stock_id"]).strip().upper()
            if not sid or sid == "NAN" or sid == "STOCK_ID" or "必填" in sid:
                continue
                
            # A. 還原庫存清單格式
            watchlist[sid] = {
                "type": str(row["type"]).strip() if pd.notna(row["type"]) else "觀察中 (尚未買進)",
                "cost": float(row["cost"]) if pd.notna(row["cost"]) else 0.0,
                "qty": int(row["qty"]) if pd.notna(row["qty"]) else 0
            }
            # B. 還原中文名稱
            if pd.notna(row["stock_name"]) and str(row["stock_name"]).strip():
                names[sid] = str(row["stock_name"]).strip()
            # C. 還原手動備援區
            backup[sid] = {
                "net_buy_5d": int(row["net_buy_5d"]) if pd.notna(row["net_buy_5d"]) else 0,
                "rev_6ma": float(row["rev_6ma"]) if pd.notna(row["rev_6ma"]) else 0.0,
                "rev_12ma": float(row["rev_12ma"]) if pd.notna(row["rev_12ma"]) else 0.0,
                "pe": float(row["pe"]) if pd.notna(row["pe"]) else 0.0,
                "yield": float(row["yield"]) if pd.notna(row["yield"]) else 0.0
            }
            
        return watchlist, names, backup
    except Exception as e:
        st.error(f"🚨 讀取雲端資料表失敗，請檢查權限或 Secrets 設定。錯誤原因: {e}")
        return {}, {}, {}

def save_system_data_to_cloud(watchlist, names, backup):
    """將目前的狀態整合，覆寫回 Google Sheets"""
    try:
        # 收集所有出現過的股票代碼
        all_stocks = set(list(watchlist.keys()) + list(names.keys()) + list(backup.keys()))
        rows = []
        for sid in all_stocks:
            w_item = watchlist.get(sid, {"type": "觀察中 (尚未買進)", "cost": 0.0, "qty": 0})
            b_item = backup.get(sid, {"net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0, "pe": 0.0, "yield": 0.0})
            
            rows.append({
                "stock_id": sid,
                "stock_name": names.get(sid, sid),
                "type": w_item["type"],
                "cost": w_item["cost"],
                "qty": w_item["qty"],
                "pe": b_item["pe"],
                "yield": b_item["yield"],
                "net_buy_5d": b_item["net_buy_5d"],
                "rev_6ma": b_item["rev_6ma"],
                "rev_12ma": b_item["rev_12ma"]
            })
            
        new_df = pd.DataFrame(rows)
        # 覆寫雲端
        conn.update(spreadsheet=GSHEET_URL, worksheet="工作表1", data=new_df)
        return True
    except Exception as e:
        st.error(f"🚨 同步寫入雲端失敗: {e}")
        return False

# 初始化載入雲端資料庫
if "watchlist" not in st.session_state:
    st.session_state.watchlist, names_db, backup_db = load_system_data_from_cloud()
else:
    _, names_db, backup_db = load_system_data_from_cloud()


# 3. 🚀 FinMind 核心引擎
@st.cache_data(ttl=3600)  # 快取 1 小時，大幅節省 API 額度
def fetch_clean_stock_data(ticker_symbol, token): #
    clean_id = ticker_symbol.replace(".TW", "").replace(".TWO", "") #
    price_start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d") #
    val_start_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d") #
    url = "https://api.finmindtrade.com/api/v4/data" #
    
    try: #
        # --- A. 抓取台股日線圖 --- #
        res_price = requests.get(url, params={ #
            "dataset": "TaiwanStockPrice", #
            "data_id": clean_id, #
            "start_date": price_start_date, #
            "token": token #
        }, timeout=10) #
        
        price_data = res_price.json() #
        if price_data.get("msg") != "success" or not price_data.get("data"): #
            return None, {}, "無法從 FinMind 取得股價，請確認代碼或 API 額度。" #
            
        df_price = pd.DataFrame(price_data["data"]) #
        df_price.rename(columns={'close': 'Close', 'date': 'Date', 'max': 'High', 'min': 'Low', 'open': 'Open'}, inplace=True) #
        df_price['Date'] = pd.to_datetime(df_price['Date']) #
        df_price.set_index('Date', inplace=True) #
        
        # --- B. 抓取本益比與殖利率 --- #
        res_val = requests.get(url, params={ #
            "dataset": "TaiwanStockPER", #
            "data_id": clean_id, #
            "start_date": val_start_date, #
            "token": token #
        }, timeout=10) #
        
        val_data_json = res_val.json() #
        pe, yield_pct = None, None #
        
        if val_data_json.get("msg") == "success" and val_data_json.get("data"): #
            df_val = pd.DataFrame(val_data_json["data"]) #
            if not df_val.empty: #
                latest_val = df_val.iloc[-1] #
                pe = latest_val.get("PE_ratio") #
                yield_pct = latest_val.get("dividend_yield") #
        
        return df_price, {"pe": pe, "yield": yield_pct}, "OK" #
    except Exception as e: #
        return None, {}, f"連線異常: {str(e)}" #

def get_display_name(ticker): #
    return names_db.get(ticker, ticker) #

# ===================================================
# 📊 介面啟動與主選單
# ===================================================
st.title("📊 個人化智慧看盤系統 v18.0") #
st.caption("🚀 全面導入 FinMind API │ ☁️ Google Sheets 雲端即時同步 │ 👑 穩定高速版") #

if st.button("🔄 強制清除股價快取 (抓取最新盤後資料)"): #
    st.cache_data.clear() #
    st.rerun() #

main_tab, control_tab = st.tabs(["核心戰情", "設定後台"]) #

# ===================================================
# 🟢 核心戰情分頁
# ===================================================
with main_tab: #
    if not st.session_state.watchlist: #
        st.info("💡 目前系統內沒有股票。請切換到「設定後台」新增股票或同步 Google Sheets！") #
    elif FINMIND_TOKEN == "請在這裡貼上你的_FinMind_Token": #
        st.error("🚨 系統偵測到你尚未設定 FinMind Token！請先至程式碼中貼上你的 Token。") #
    else: #
        ma_strategy = st.radio("買點策略", ["波段操作 (20MA)", "長線大底 (60MA)"], horizontal=True, key="ma_strat_180") #
        st.write("---") #
        
        for ticker_symbol, item in st.session_state.watchlist.items(): #
            stock_name = get_display_name(ticker_symbol) #
            
            # 🚀 呼叫全新的 FinMind 引擎
            hist, val_data, status = fetch_clean_stock_data(ticker_symbol, FINMIND_TOKEN) #
            b_item = backup_db.get(ticker_symbol, {"net_buy_5d": 0, "rev_6ma": 0.0, "rev_12ma": 0.0, "pe": 0.0, "yield": 0.0}) #
            
            if hist is None: #
                st.warning(f"⚠️ 暫時無法取得 【{stock_name} ({ticker_symbol})】 的即時股價資料。已切換為純備援顯示。原因：{status}") #
                continue #

            # 綜合數據 (手動大於 0 絕對優先採用)
            pe = b_item.get("pe", 0.0) if b_item.get("pe", 0.0) > 0 else (val_data.get("pe") if pd.notna(val_data.get("pe")) else 0.0) #
            yield_pct = b_item.get("yield", 0.0) if b_item.get("yield", 0.0) > 0 else (val_data.get("yield") if pd.notna(val_data.get("yield")) else 0.0) #
            
            net_buy_5d = b_item.get("net_buy_5d", 0) #
            rev_6ma = b_item.get("rev_6ma", 0.0) #
            rev_12ma = b_item.get("rev_12ma", 0.0) #

            # 狀態燈號計算
            if pe == 0: #
                pe_status, pe_color = "不適用 (ETF/未填寫)", "⚪" #
            else: #
                pe_status = f"便宜 ({pe:.1f})" if pe < 12 else (f"合理 ({pe:.1f})" if pe <= 20 else f"昂貴 ({pe:.1f})") #
                pe_color = "🟢" if pe < 12 else ("🟡" if pe <= 20 else "🔴") #
            
            if yield_pct == 0: #
                yield_status, yield_color = "無配息", "⚪" #
            else: #
                yield_status = f"高殖利率 ({yield_pct:.2f}%)" if yield_pct >= 4.5 else f"一般 ({yield_pct:.2f}%)" #
                yield_color = "🟢" if yield_pct >= 4.5 else "🟡" #
            
            if rev_6ma == 0 and rev_12ma == 0: #
                rev_status = "⚪ 不適用 (ETF/無營收)" #
            elif rev_6ma >= rev_12ma: #
                rev_status = f"🟢 多頭 (6MA {rev_6ma:,.2f} > 12MA {rev_12ma:,.2f})" #
            else: #
                rev_status = f"🔴 衰退 (6MA {rev_6ma:,.2f} < 12MA {rev_12ma:,.2f})" #
            
            if net_buy_5d > 1500: #
                chips_status = f"🟢 主力大買 (+{net_buy_5d}張)" #
            elif net_buy_5d < -1500: #
                chips_status = f"🔴 主力大賣 ({net_buy_5d}張)" #
            else: #
                chips_status = f"🟡 籌碼震盪 ({net_buy_5d}張)" #

            # 移動停損監控
            price = float(hist['Close'].iloc[-1]) #
            historical_max = float(hist['Close'].max()) #
            stop_base = max(item["cost"], historical_max) #
            trailing_stop_line = stop_base * 0.90 #
            
            if price > trailing_stop_line: #
                drop_needed = ((price - trailing_stop_line) / price) * 100 #
                stop_light, hold_action, hold_color = f"🍏 安全 (再跌 {drop_needed:.1f}% 止損)", "續抱安全區", "🍏" #
            else: #
                drop_broken = ((trailing_stop_line - price) / trailing_stop_line) * 100 #
                stop_light, hold_action, hold_color = f"🔴 破線 (超限 {drop_broken:.1f}%)", "🚨 觸發移動停損！請執行賣出紀律！", "🔴" #

            # 均線計算
            hist['MA20'] = hist['Close'].rolling(window=20).mean() #
            hist['MA60'] = hist['Close'].rolling(window=60).mean() #
            target_ma = hist['MA20'].iloc[-1] if "20MA" in ma_strategy else hist['MA60'].iloc[-1] #
            ma_label = "20MA" if "20MA" in ma_strategy else "60MA" #
            buy_range_str = f"{target_ma:.2f} ~ {target_ma * 1.05:.2f}" if pd.notna(target_ma) else "資料天數不足" #
            
            if item["type"] == "已持股": #
                pnl = (price - item["cost"]) * item["qty"] #
                roi = (pnl / (item["cost"] * item["qty"]) * 100) if item["cost"] > 0 else 0 #
                pnl_str = f"{pnl:,.0f} 元 ({roi:+.1f}%)" #
            else: #
                pnl_str, hold_action, stop_light, hold_color = "—", "觀察中", "—", "⚪" #
                
            # 卡片展開
            with st.expander(f"📈 {stock_name} ({ticker_symbol}) ｜ 現價: 🌐 {price:.2f} ｜ 🛑 {hold_color} {hold_action}"): #
                if item["type"] == "已持股": #
                    st.markdown("### 🛑 移動停損即時監控數據") #
                    col1, col2, col3 = st.columns(3) #
                    col1.metric("⛰ *半年最高價*", f"{historical_max:.2f} 元") #
                    col2.metric("🎯 *停損賣出線*", f"{trailing_stop_line:.2f} 元") #
                    col3.metric("🚨 *死線倒數*", stop_light) #
                    st.markdown(f"**💰 目前持股累積損益：** **{pnl_str}**") #
                    st.write("---") #
                
                st.markdown(f"**🛒 理想買入防線 ({ma_label})：** **{buy_range_str} 元**") #
                st.markdown(f"**🎯 估值區間 (P/E)：** {pe_color} {pe_status} ｜ **🛡 股息底氣：** {yield_color} {yield_status}") #
                st.markdown(f"**📈 營收趨勢判定 (6MA vs 12MA)：** {rev_status} ｜ **👤 主力籌碼：** {chips_status}") #


# ===================================================
# ⚙️ 設定後台分頁
# ===================================================
with control_tab: #
    st.markdown("### ☁️ 系統資料備份與雲端控制中樞") #
    col_bak1, col_bak2 = st.columns(2) #
    
    with col_bak1: #
        st.write("① 本地導出：打包下載當前雲端所有股票資料") #
        bundle_data = { #
            "watchlist": st.session_state.watchlist, #
            "names": names_db, #
            "backup_db": backup_db #
        } #
        json_string = json.dumps(bundle_data, ensure_ascii=False, indent=4) #
        st.download_button( #
            label="📥 點我下載【JSON 備份檔】", #
            data=json_string, #
            file_name="my_stock_cloud_backup_v18.json", #
            mime="application/json", #
            use_container_width=True #
        ) #
        
    with col_bak2: #
        st.write("② 滿血導入：上傳舊備份檔並【強制同步覆寫】到 Google Sheets") #
        uploaded_backup = st.file_uploader("📤 上傳舊 JSON 檔 (.json)", type=["json"], label_visibility="collapsed") #
        if uploaded_backup is not None: #
            try: #
                uploaded_data = json.load(uploaded_backup) #
                if "watchlist" in uploaded_data: #
                    st.session_state.watchlist = uploaded_data["watchlist"] #
                    u_names = uploaded_data.get("names", {})
                    u_backup = uploaded_data.get("backup_db", {})
                    
                    # 寫入雲端
                    if save_system_data_to_cloud(st.session_state.watchlist, u_names, u_backup):
                        st.success("✨ 成功將備份檔推送到 Google Sheets 雲端！網頁即將重整...") #
                        time.sleep(1.0) #
                        st.rerun() #
            except Exception as e: #
                st.error(f"❌ 解析或同步失敗，請確認檔案格式。原因: {e}") #
                
    st.write("---") #

    col_left, col_right = st.columns([1, 1]) #
    
    with col_left: #
        st.subheader("➕ 新增 / 編輯庫存股票") #
        new_stock = st.text_input("股票代碼 (例: 0050.TW)", key="add_code").upper().strip() #
        custom_name = st.text_input("股票中文別名 (例: 元大台灣50)", key="add_name") #
        stock_type = st.selectbox("類別", ["觀察中 (尚未買進)", "已持股"], key="add_type") #
        
        cost, qty = 0.0, 0 #
        if stock_type == "已持股": #
            cost = st.number_input("買入成本價", min_value=0.0, step=0.1, key="add_cost") #
            qty = st.number_input("持有股數", min_value=0, step=100, key="add_qty") #
            
        if st.button("💾 確認儲存股票並同步雲端", use_container_width=True): #
            if new_stock: #
                st.session_state.watchlist[new_stock] = {"type": stock_type, "cost": cost, "qty": qty} #
                if custom_name: #
                    names_db[new_stock] = custom_name #
                
                # 同步到雲端
                if save_system_data_to_cloud(st.session_state.watchlist, names_db, backup_db):
                    st.cache_data.clear() #
                    st.success(f"股票 {new_stock} 已成功寫入 Google Sheets！") #
                    time.sleep(0.5) #
                    st.rerun() #

        st.write("---") #
        
        st.subheader("🗑️ 刪除庫存股票") #
        if st.session_state.watchlist: #
            stock_to_delete = st.selectbox("請選擇要從清單移除的股票", ["-- 請選擇 --"] + list(st.session_state.watchlist.keys())) #
            if st.button("⚠️ 確認刪除", type="primary", use_container_width=True): #
                if stock_to_delete != "-- 請選擇 --" and stock_to_delete != "-- 請选择 --" and stock_to_delete in st.session_state.watchlist: #
                    del st.session_state.watchlist[stock_to_delete] #
                    if stock_to_delete in names_db:
                        del names_db[stock_to_delete]
                    if stock_to_delete in backup_db:
                        del backup_db[stock_to_delete]
                        
                    # 同步到雲端
                    if save_system_data_to_cloud(st.session_state.watchlist, names_db, backup_db):
                        st.success(f"已成功從雲端刪除 {stock_to_delete}！") #
                        time.sleep(0.5) #
                        st.rerun() #
        else: #
            st.info("目前沒有可刪除的股票。") #

    with col_right: #
        st.subheader("✍ 🛠️ 進階數據【手動備援區】") #
        if st.session_state.watchlist: #
            tgt_b = st.selectbox("選擇要備援的股票", list(st.session_state.watchlist.keys()), key="backup_tgt") #
            
            cur_b = backup_db.get(tgt_b, {}) #
            v_pe = float(cur_b.get("pe", 0.0)) #
            v_yield = float(cur_b.get("yield", 0.0)) #
            v_chip = int(cur_b.get("net_buy_5d", 0)) #
            v_6ma = float(cur_b.get("rev_6ma", 0.0)) #
            v_12ma = float(cur_b.get("rev_12ma", 0.0)) #
            
            pe_in = st.number_input("手動本益比 (PE) *若為 ETF 請填 0*", value=v_pe, key=f"pe_in_{tgt_b}") #
            y_in = st.number_input("手動殖利率 (%) *若為 ETF 請填 0*", value=v_yield, key=f"yield_in_{tgt_b}") #
            chip_in = st.number_input("近 5 日法人累積買超 (張)", value=v_chip, key=f"chip_in_{tgt_b}") #
            
            st.write("---") #
            st.markdown("#### 📈 營收數據備援") #
            rev6ma_in = st.number_input("6MA 營收水位", value=v_6ma, step=10.0, key=f"rev6__in_{tgt_b}") #
            rev12ma_in = st.number_input("12MA 營收水位", value=v_12ma, step=10.0, key=f"rev12__in_{tgt_b}") #
            
            if st.button("💾 儲存並寫入 Google Sheets", use_container_width=True, key=f"save_btn_{tgt_b}"): #
                backup_db[tgt_b] = { #
                    "net_buy_5d": chip_in,  #
                    "rev_6ma": rev6ma_in,  #
                    "rev_12ma": rev12ma_in,  #
                    "pe": pe_in,  #
                    "yield": y_in #
                } #
                
                # 同步到雲端
                if save_system_data_to_cloud(st.session_state.watchlist, names_db, backup_db):
                    st.success(f"✨ {tgt_b} 專屬數據已同步寫入雲端試算表！") #
                    time.sleep(0.5) #
                    st.rerun() #
        else: #
            st.info("請先在左側新增股票。") #