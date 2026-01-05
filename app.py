import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yfinance as yf
import pandas as pd
import os
from datetime import datetime

# ==========================================
# 0. 基礎設定與檔案路徑
# ==========================================
st.set_page_config(page_title="投資戰情室", layout="wide")
DATA_FILE = "data/trades.csv"

# 確保 data 資料夾存在
if not os.path.exists("data"):
    os.makedirs("data")

# ==========================================
# 1. 讀取設定與驗證 (帳密系統)
# ==========================================
with open('config.yaml', encoding='utf-8') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login()

# ==========================================
# 2. 登入成功後的戰情室主畫面
# ==========================================
if st.session_state["authentication_status"]:
    # 側邊欄：登出與匯率
    authenticator.logout('登出系統', 'sidebar')
    
    st.title(f"📈 {st.session_state['name']} 的資產戰情室")

    # [功能 A] 側邊欄顯示即時匯率
    with st.sidebar:
        st.header("市場數據")
        try:
            with st.spinner('同步匯率中...'):
                usd_rate = yf.Ticker("USDTWD=X").fast_info['last_price']
                st.metric("美金匯率 (USD/TWD)", f"{usd_rate:.2f}")
        except Exception as e:
            st.error("匯率抓取失敗，請檢查網路")

    # [功能 B] 新增買賣紀錄 (收合式表單) - 優化：預設空白
    st.subheader("📝 記帳區")
    with st.expander("➕ 新增一筆交易 (iPhone 模式)", expanded=True):
        with st.form("trade_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)
            t_date = col1.date_input("日期", value=datetime.now())
            t_code = col2.text_input("股票代號", placeholder="例如: 2330.TW")
            t_action = col3.selectbox("動作", ["買入", "賣出"])
            
            # ★★★ 修改重點：加上 value=None 讓預設變空白，placeholder 提示文字 ★★★
            t_price = col4.number_input("成交價格", min_value=0.0, step=0.01, value=None, placeholder="輸入價格")
            t_qty = st.number_input("成交股數", min_value=0.0, step=0.001, value=None, placeholder="輸入股數")
            
            submit_btn = st.form_submit_button("儲存紀錄")

            if submit_btn:
                # ★★★ 防呆機制：檢查是否為 None (即使用者沒輸入) ★★★
                if not t_code:
                    st.error("❌ 請輸入股票代號！")
                elif t_price is None:
                    st.error("❌ 請輸入成交價格！")
                elif t_qty is None:
                    st.error("❌ 請輸入成交股數！")
                else:
                    # 資料完整，開始存檔
                    new_data = pd.DataFrame([{
                        "日期": t_date, 
                        "代號": t_code.upper(),
                        "動作": t_action,
                        "價格": t_price,
                        "股數": t_qty,
                        "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }])
                    
                    # 存入 CSV
                    if not os.path.isfile(DATA_FILE):
                        new_data.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    else:
                        new_data.to_csv(DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
                    
                    st.success(f"✅ 已成功記錄 {t_code} (價格: {t_price}, 股數: {t_qty})")
                    st.rerun()

    # [功能 C] 歷史紀錄管理 (可編輯/刪除模式)
    st.divider()
    st.subheader("📋 歷史交易管理 (可編輯)")
    
    if os.path.exists(DATA_FILE):
        df_history = pd.read_csv(DATA_FILE)
        
        if not df_history.empty:
            # 強制轉型，避免資料格式錯誤
            df_history["代號"] = df_history["代號"].astype(str)
            df_history["日期"] = pd.to_datetime(df_history["日期"]).dt.date

            edited_df = st.data_editor(
                df_history,
                num_rows="dynamic",
                use_container_width=True,
                key="history_editor",
                column_config={
                    "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                    "代號": st.column_config.TextColumn("代號"),
                    "動作": st.column_config.SelectboxColumn("動作", options=["買入", "賣出"]),
                    "價格": st.column_config.NumberColumn("價格", format="$ %.2f"),
                    "股數": st.column_config.NumberColumn("股數", format="%.4f"),
                    "建立時間": st.column_config.TextColumn("建立時間", disabled=True)
                }
            )

            col_save, col_hint = st.columns([1, 4])
            with col_save:
                if st.button("💾 儲存修改"):
                    edited_df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    st.success("✅ 修改已儲存！")
                    st.rerun()
            with col_hint:
                st.caption("💡 操作提示：1. 勾選左側方塊並按 Delete 可刪除。 2. 點擊表格內容可直接修改。 3. 修改完畢務必按下「儲存修改」。")
        else:
             st.info("目前尚無交易紀錄。")
    else:
        st.info("目前尚無交易紀錄，請上方新增。")

# ==========================================
# 3. 登入失敗處理
# ==========================================
elif st.session_state["authentication_status"] is False:
    st.error('帳號或密碼錯誤')
elif st.session_state["authentication_status"] is None:
    st.warning('請輸入帳號密碼進入系統')