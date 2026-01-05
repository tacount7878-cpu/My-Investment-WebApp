import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yfinance as yf

# 頁面配置
st.set_page_config(page_title="投資戰情室", layout="wide")

# 1. 讀取設定檔 (加上 utf-8 確保中文不亂碼)
with open('config.yaml', encoding='utf-8') as file:
    config = yaml.load(file, Loader=SafeLoader)

# 2. 設定驗證功能
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# 3. 顯示登入頁面 (新版語法：不用指定 'main'，它會自動處理)
authenticator.login()

# 檢查登入狀態
if st.session_state["authentication_status"]:
    # 登入成功
    authenticator.logout('登出系統', 'sidebar')
    st.title(f"📈 {st.session_state['name']} 的資產戰情室")
    
    # 抓取即時匯率
    with st.spinner('正在同步全球匯率...'):
        usd_ticker = yf.Ticker("USDTWD=X")
        usd_rate = usd_ticker.fast_info['last_price']
        st.metric("當前美金匯率 (USD/TWD)", f"{usd_rate:.2f}")
    
    st.success("✅ 系統已連線。您可以開始記錄買賣或查看資產分佈。")

elif st.session_state["authentication_status"] is False:
    st.error('帳號或密碼錯誤')
elif st.session_state["authentication_status"] is None:
    st.warning('請輸入帳號密碼進入系統')