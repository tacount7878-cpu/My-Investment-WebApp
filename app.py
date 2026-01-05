import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yfinance as yf
import pandas as pd
import os
from datetime import datetime, time
import pytz # 處理時區

# ==========================================
# 0. 基礎設定與檔案路徑
# ==========================================
# 設定網頁標題與自訂選單文字
st.set_page_config(
    page_title="投資戰情室", 
    layout="wide",
    menu_items={
        'Get Help': 'https://www.google.com',
        'Report a bug': "https://www.google.com",
        'About': "# 這是您的私人資產戰情室"
    }
)

DATA_FILE = "data/trades.csv"
FINANCE_FILE = "data/financials.csv" # 新增：用來存現金與貸款

# 確保 data 資料夾存在
if not os.path.exists("data"):
    os.makedirs("data")

# 預設的財務數據 (如果檔案不存在)
DEFAULT_FINANCIALS = {
    "loan": 0.0,            # 目前貸款
    "cash_account": 0.0,    # 帳戶現金
    "cash_settlement": 0.0, # 交割中現金
    "cash_usd": 0.0         # 美元現金
}

# ==========================================
# 1. 工具函式：讀寫財務數據 & 市場時間
# ==========================================
def load_financials():
    if os.path.exists(FINANCE_FILE):
        try:
            df = pd.read_csv(FINANCE_FILE)
            # 轉成字典方便使用
            return df.set_index('category')['amount'].to_dict()
        except:
            return DEFAULT_FINANCIALS
    else:
        return DEFAULT_FINANCIALS

def save_financials(data_dict):
    df = pd.DataFrame(list(data_dict.items()), columns=['category', 'amount'])
    df.to_csv(FINANCE_FILE, index=False)

def check_market_status():
    """檢查各國股市開盤狀態"""
    utc_now = datetime.now(pytz.utc)
    
    # 定義時區
    tw_tz = pytz.timezone('Asia/Taipei')
    us_tz = pytz.timezone('US/Eastern')
    uk_tz = pytz.timezone('Europe/London') # VWRA 在倫敦

    # 轉換時間
    tw_time = utc_now.astimezone(tw_tz)
    us_time = utc_now.astimezone(us_tz)
    uk_time = utc_now.astimezone(uk_tz)

    # 判斷開盤 (簡化邏輯：週一至週五，特定時段，不含國定假日判斷)
    def is_open(current_time, start_h, start_m, end_h, end_m):
        if current_time.weekday() >= 5: # 週六週日
            return False, "休市 (週末)"
        # 轉成 minutes 比較比較方便
        curr_min = current_time.hour * 60 + current_time.minute
        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m
        
        if start_min <= curr_min <= end_min:
            return True, "開盤中 🟢"
        else:
            return False, "已收盤 🔴"

    # 美股 (09:30 - 16:00)
    us_open, us_msg = is_open(us_time, 9, 30, 16, 0)
    # 英股 (08:00 - 16:30)
    uk_open, uk_msg = is_open(uk_time, 8, 0, 16, 30)

    return {
        "tw_str": tw_time.strftime("%Y/%m/%d %H:%M:%S"),
        "us_status": us_msg,
        "us_time_str": us_time.strftime("%H:%M"),
        "uk_status": uk_msg,
        "uk_time_str": uk_time.strftime("%H:%M")
    }

# ==========================================
# 2. 核心數據：初始持倉 (基期)
# ==========================================
INITIAL_ASSETS = [
    {"code": "0050.TW", "cost": 52.28, "qty": 30000, "currency": "TWD"},
    {"code": "006208.TW", "cost": 114.56, "qty": 4623, "currency": "TWD"},
    {"code": "2330.TW", "cost": 1435.28, "qty": 140, "currency": "TWD"},
    {"code": "00679B.TW", "cost": 26.74, "qty": 11236, "currency": "TWD"},
    {"code": "00719B.TW", "cost": 29.77, "qty": 14371, "currency": "TWD"},
    {"code": "00720B.TW", "cost": 33.80, "qty": 8875, "currency": "TWD"},
    {"code": "VT", "cost": 133.46, "qty": 139, "currency": "USD"},
    {"code": "SGOV", "cost": 100.53, "qty": 81.00, "currency": "USD"}, 
    {"code": "TSLA", "cost": 296.38, "qty": 3.00, "currency": "USD"}, 
    {"code": "GOOGL", "cost": 290.13, "qty": 2.00, "currency": "USD"}, 
    {"code": "GOOGL", "cost": 236.48, "qty": 34.00, "currency": "USD"}, 
    {"code": "TSLA", "cost": 424.45, "qty": 10.00, "currency": "USD"}, 
    {"code": "VWRA.L", "cost": 169.84, "qty": 144.0206, "currency": "USD"},
    {"code": "IBKR", "cost": 64.37, "qty": 3.8374, "currency": "USD"},
    {"code": "TSLA", "cost": 445.04, "qty": 5.5456, "currency": "USD"}, 
    {"code": "GOOG", "cost": 314.35, "qty": 4.5746, "currency": "USD"}, 
    {"code": "VTI", "cost": 334.91, "qty": 3.6547, "currency": "USD"}, 
    {"code": "SGOV", "cost": 100.54, "qty": 9.9463, "currency": "USD"}, 
    {"code": "BTC-USD", "cost": 0.00, "qty": 0.0477, "currency": "USD"},
]

# ==========================================
# 3. 讀取設定與驗證
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
# 4. 主程式邏輯
# ==========================================
if st.session_state["authentication_status"]:
    authenticator.logout('登出系統', 'sidebar')
    
    # 載入財務數據
    fin_data = load_financials()
    market_info = check_market_status()

    # --- A. 側邊欄 (資訊與匯率) ---
    with st.sidebar:
        st.header("🌍 市場戰情")
        st.caption(f"台灣時間: {market_info['tw_str']}")
        
        # 匯率
        usd_rate = 32.5 
        try:
            usd_ticker = yf.Ticker("USDTWD=X")
            usd_rate = usd_ticker.fast_info['last_price']
            st.metric("🇺🇸 美金匯率", f"{usd_rate:.2f}")
        except:
            st.warning("匯率連線失敗")

        st.divider()
        
        # 市場狀態
        st.markdown(f"**🇺🇸 美股 (NYSE/NAS)**")
        st.text(f"{market_info['us_status']} ({market_info['us_time_str']} ET)")
        
        st.markdown(f"**🇬🇧 英股 (VWRA)**")
        st.text(f"{market_info['uk_status']} ({market_info['uk_time_str']} UK)")

    st.title(f"📊 {st.session_state['name']} 的資產總管")

    # --- B. 財務設定區 (可收合) ---
    # 這裡讓使用者輸入貸款與現金，數據會即時影響總資產
    with st.expander("💰 現金與貸款設定 (點擊展開修改)", expanded=False):
        with st.form("financial_form"):
            c1, c2, c3, c4 = st.columns(4)
            # 填入預設值
            in_loan = c1.number_input("目前貸款 (TWD)", value=fin_data.get('loan', 0.0), step=10000.0)
            in_cash_acc = c2.number_input("帳戶現金 (TWD)", value=fin_data.get('cash_account', 0.0), step=1000.0)
            in_cash_set = c3.number_input("交割中現金 (TWD)", value=fin_data.get('cash_settlement', 0.0), step=1000.0)
            in_cash_usd = c4.number_input("美元現金 (USD)", value=fin_data.get('cash_usd', 0.0), step=10.0)
            
            if st.form_submit_button("💾 更新財務數據"):
                new_fin = {
                    "loan": in_loan,
                    "cash_account": in_cash_acc,
                    "cash_settlement": in_cash_set,
                    "cash_usd": in_cash_usd
                }
                save_financials(new_fin)
                st.success("財務數據已更新！")
                st.rerun()

    # --- C. 核心邏輯：計算股票現值 ---
    # 1. 初始資產建檔
    portfolio = {} 
    for item in INITIAL_ASSETS:
        code = item['code']
        if code not in portfolio:
            portfolio[code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': item['currency']}
        portfolio[code]['qty'] += item['qty']
        portfolio[code]['total_cost'] += item['cost'] * item['qty']

    # 2. 交易回放
    if os.path.exists(DATA_FILE):
        df_trades = pd.read_csv(DATA_FILE)
        if not df_trades.empty:
            # 代號校正
            df_trades["代號"] = df_trades["代號"].astype(str).apply(
                lambda x: x + ".TW" if x.isdigit() and len(x) == 4 else x.upper()
            )
            df_trades["股數"] = pd.to_numeric(df_trades["股數"])
            df_trades["價格"] = pd.to_numeric(df_trades["價格"])
            
            for index, row in df_trades.iterrows():
                t_code = row['代號']
                t_action = row['動作']
                t_qty = row['股數']
                t_price = row['價格']
                
                if t_code not in portfolio:
                    portfolio[t_code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': 'TWD'}

                if portfolio[t_code]['qty'] > 0:
                    current_avg_cost = portfolio[t_code]['total_cost'] / portfolio[t_code]['qty']
                else:
                    current_avg_cost = 0

                if t_action == '買入':
                    portfolio[t_code]['qty'] += t_qty
                    portfolio[t_code]['total_cost'] += t_price * t_qty
                elif t_action == '賣出':
                    if portfolio[t_code]['qty'] > 0:
                        cost_to_remove = current_avg_cost * t_qty
                        portfolio[t_code]['qty'] -= t_qty
                        portfolio[t_code]['total_cost'] -= cost_to_remove

    # 3. 計算股票總市值
    total_stock_value_twd = 0
    display_rows = []
    
    # 進度條
    active_assets = [(k, v) for k, v in portfolio.items() if v['qty'] > 0.0001]
    
    if len(active_assets) > 0:
        # 這裡不顯示進度條文字以免畫面跳動，改用 spinner
        # 如果需要進度條可加回來
        pass

    for code, data in active_assets:
        qty = data['qty']
        avg_cost = data['total_cost'] / qty if qty > 0 else 0
        currency = data['currency']
        
        try:
            ticker = yf.Ticker(code)
            current_price = ticker.fast_info['last_price']
        except:
            current_price = avg_cost 
        
        rate = usd_rate if currency == "USD" else 1
        market_value_twd = qty * current_price * rate
        profit_twd = (current_price - avg_cost) * qty * rate
        roi = ((current_price - avg_cost) / avg_cost) * 100 if avg_cost > 0 else 0

        total_stock_value_twd += market_value_twd

        display_rows.append({
            "代號": code,
            "持股數": qty,
            "幣別": currency,
            "平均成本": avg_cost,
            "現價": current_price,
            "市值 (TWD)": market_value_twd,
            "未實現損益 (TWD)": profit_twd,
            "報酬率 %": roi
        })

    # --- D. 總資產計算 (股票 + 現金 - 貸款) ---
    # 讀取最新的財務輸入
    fin_loan = fin_data.get('loan', 0.0)
    fin_cash_acc = fin_data.get('cash_account', 0.0)
    fin_cash_set = fin_data.get('cash_settlement', 0.0)
    fin_cash_usd = fin_data.get('cash_usd', 0.0)
    
    # 美元現金轉台幣
    fin_cash_usd_twd = fin_cash_usd * usd_rate

    # 總淨值公式
    total_net_worth = (total_stock_value_twd + fin_cash_acc + fin_cash_set + fin_cash_usd_twd) - fin_loan

    # --- E. 儀表板顯示 ---
    st.divider()
    
    # 第一排：核心總覽
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 總淨資產 (TWD)", f"${total_net_worth:,.0f}", help="股票市值 + 所有現金 - 貸款")
    m2.metric("📉 目前貸款", f"${fin_loan:,.0f}", delta_color="inverse")
    m3.metric("💵 台幣總現金", f"${(fin_cash_acc + fin_cash_set):,.0f}", help="帳戶現金 + 交割中現金")
    m4.metric("🇺🇸 美元現金 (約台幣)", f"${fin_cash_usd_twd:,.0f}", f"{fin_cash_usd:,.2f} USD")

    # 第二排：投資績效
    st.markdown("---")
    k1, k2, k3 = st.columns(3)
    k1.metric("📈 股票總市值", f"${total_stock_value_twd:,.0f}")
    
    # 總成本估算
    total_stock_cost = sum([r['平均成本'] * r['持股數'] * (usd_rate if r['幣別']=='USD' else 1) for r in display_rows])
    total_profit = total_stock_value_twd - total_stock_cost
    k2.metric("🎉 股票未實現損益", f"${total_profit:,.0f}", delta_color="normal")
    
    total_roi = (total_profit / total_stock_cost * 100) if total_stock_cost > 0 else 0
    k3.metric("🚀 總投資報酬率", f"{total_roi:.2f}%")

    # --- F. 詳細表格與記帳 ---
    st.subheader("📊 資產庫存明細")
    df_display = pd.DataFrame(display_rows)
    if not df_display.empty:
        st.dataframe(
            df_display,
            use_container_width=True,
            column_config={
                "平均成本": st.column_config.NumberColumn(format="%.2f"),
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "市值 (TWD)": st.column_config.ProgressColumn(format="$%d", min_value=0, max_value=max(df_display["市值 (TWD)"])),
                "未實現損益 (TWD)": st.column_config.NumberColumn(format="$%d"),
                "報酬率 %": st.column_config.NumberColumn(format="%.2f %%")
            },
            hide_index=True
        )

    st.divider()
    with st.expander("➕ 新增股票交易紀錄"):
        with st.form("trade_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            t_date = c1.date_input("日期", value=datetime.now())
            t_code = c2.text_input("股票代號", placeholder="006208")
            t_action = c3.selectbox("動作", ["買入", "賣出"])
            t_price = c4.number_input("成交價格", min_value=0.0, step=0.01, value=None)
            t_qty = st.number_input("成交股數", min_value=0.0, step=0.001, value=None)
            
            if st.form_submit_button("儲存紀錄"):
                if not t_code or t_price is None or t_qty is None:
                    st.error("❌ 資料不完整")
                else:
                    final_code = t_code
                    if t_code.isdigit() and len(t_code) == 4:
                        final_code = t_code + ".TW"
                    else:
                        final_code = t_code.upper()

                    new_data = pd.DataFrame([{
                        "日期": t_date, "代號": final_code, "動作": t_action,
                        "價格": t_price, "股數": t_qty,
                        "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }])
                    if not os.path.isfile(DATA_FILE):
                        new_data.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    else:
                        new_data.to_csv(DATA_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
                    st.success(f"✅ 已記錄 {final_code}")
                    st.rerun()

    if os.path.exists(DATA_FILE):
        with st.expander("📋 歷史交易管理 (可編輯)"):
            df_hist = pd.read_csv(DATA_FILE)
            if not df_hist.empty:
                df_hist["代號"] = df_hist["代號"].astype(str)
                df_hist["日期"] = pd.to_datetime(df_hist["日期"]).dt.date
                edited_df = st.data_editor(df_hist, num_rows="dynamic", use_container_width=True, key="history")
                if st.button("💾 儲存歷史修改"):
                    edited_df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    st.success("已儲存")
                    st.rerun()

# 登入失敗處理
elif st.session_state["authentication_status"] is False:
    st.error('帳號或密碼錯誤')
elif st.session_state["authentication_status"] is None:
    st.warning('請輸入帳號密碼進入系統')