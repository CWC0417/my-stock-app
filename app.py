# 2. 資料讀寫工具 (Google Sheets 雲端版)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet_name, default_data):
    try:
        # 讀取指定的 Google 工作表
        df = conn.read(worksheet=worksheet_name, ttl=0)
        
        # 如果是空的，回傳預設值
        if df.empty:
            return default_data
            
        # 為了配合你原本程式碼習慣的「字典 (Dictionary)」格式，我們把 DataFrame 轉回字典
        # 假設你原本的 JSON 格式是 {"2330": {...}, "2317": {...}}
        return df.to_dict(orient='index')
    except Exception:
        return default_data

def save_data(worksheet_name, data):
    # 將你的字典資料轉成 DataFrame 格式，然後覆寫回 Google 試算表
    df = pd.DataFrame.from_dict(data, orient='index')
    conn.update(worksheet=worksheet_name, data=df)

# 初始化變數：從原本的檔案名稱，改成讀取對應的 Google 工作表名稱
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_data("watchlist", {})

backup_db = load_data("backup_db", {}) 
names_db = load_data("names_db", {})