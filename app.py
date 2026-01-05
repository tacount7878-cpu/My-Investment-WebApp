import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import pytz
import plotly.express as px # 新增繪圖工具

# ==========================================
# 0. 基礎設定
# ==========================================
st.set_page_config(
    page_title="投資戰情室", 
    layout="wide",
    menu_items={'About': "# 這是您的私人資產戰情室"}
)

DATA_FILE = "data/trades.csv"
FINANCE_FILE = "data/financials.csv"

if not os.path.exists("data"):
    os.makedirs("data")

DEFAULT_FINANCIALS = {"loan": 0.0, "cash_account": 0.0, "cash_settlement": 0.0, "cash_usd": 0.0}

# ==========================================
# 1. 工具函式
# ==========================================
def load_financials():
    if os.path.exists(FINANCE_FILE):
        try:
            df = pd.read_csv(FINANCE_FILE)
            return df.set_index('category')['amount'].to_dict()
        except:
            return DEFAULT_FINANCIALS
    return DEFAULT_FINANCIALS

def save_financials(data_dict):
    df = pd.DataFrame(list(data_dict.items()), columns=['category', 'amount'])
    df.to_csv(FINANCE_FILE, index=False)

def check_market_status():
    utc_now = datetime.now(pytz.utc)
    # 定義時區
    tw_tz = pytz.timezone('Asia/Taipei')
    us_tz = pytz.timezone('US/Eastern')
    uk_tz = pytz.timezone('Europe/London')

    tw_time = utc_now.astimezone(tw_tz)
    us_time = utc_now.astimezone(us_tz)
    uk_time = utc_now.astimezone(uk_tz)

    def is_open(current_time, start_h, start_m, end_h, end_m):
        if current_time.weekday() >= 5: return False, "休市 (週末)"
        curr_min = current_time.hour * 60 + current_time.minute
        if (start_h * 60 + start_m) <= curr_min <= (end_h * 60 + end_m):
            return True, "🟢 開盤中"
        return False, "🔴 已收盤"

    us_open, us_msg = is_open(us_time, 9, 30, 16, 0)
    uk_open, uk_msg = is_open(uk_time, 8, 0, 16, 30)

    return {
        "tw_str": tw_time.strftime("%Y/%m/%d %H:%M:%S"),
        "us_status": us_msg, "us_time_str": us_time.strftime("%H:%M"),
        "uk_status": uk_msg, "uk_time_str": uk_time.strftime("%H:%M")
    }

# ==========================================
# 2. 初始資產
# ==========================================
INITIAL_ASSETS = [
    {"code": "0050.TW", "cost": 52.28, "qty": 30000, "currency": "TWD", "type": "台股"},
    {"code": "006208.TW", "cost": 114.56, "qty": 4623, "currency": "TWD", "type": "台股"},
    {"code": "2330.TW", "cost": 1435.28, "qty": 140, "currency": "TWD", "type": "台股"},
    {"code": "00679B.TW", "cost": 26.74, "qty": 11236, "currency": "TWD", "type": "債券"},
    {"code": "00719B.TW", "cost": 29.77, "qty": 14371, "currency": "TWD", "type": "債券"},
    {"code": "00720B.TW", "cost": 33.80, "qty": 8875, "currency": "TWD", "type": "債券"},
    {"code": "VT", "cost": 133.46, "qty": 139, "currency": "USD", "type": "全球ETF"},
    {"code": "SGOV", "cost": 100.53, "qty": 81.00, "currency": "USD", "type": "美債"},
    {"code": "TSLA", "cost": 296.38, "qty": 3.00, "currency": "USD", "type": "美股"},
    {"code": "GOOGL", "cost": 290.13, "qty": 2.00, "currency": "USD", "type": "美股"},
    {"code": "GOOGL", "cost": 236.48, "qty": 34.00, "currency": "USD", "type": "美股"},
    {"code": "TSLA", "cost": 424.45, "qty": 10.00, "currency": "USD", "type": "美股"},
    {"code": "VWRA.L", "cost": 169.84, "qty": 144.0206, "currency": "USD", "type": "全球ETF"},
    {"code": "IBKR", "cost": 64.37, "qty": 3.8374, "currency": "USD", "type": "美股"},
    {"code": "TSLA", "cost": 445.04, "qty": 5.5456, "currency": "USD", "type": "美股"},
    {"code": "GOOG", "cost": 314.35, "qty": 4.5746, "currency": "USD", "type": "美股"},
    {"code": "VTI", "cost": 334.91, "qty": 3.6547, "currency": "USD", "type": "美股ETF"},
    {"code": "SGOV", "cost": 100.54, "qty": 9.9463, "currency": "USD", "type": "美債"},
    {"code": "BTC-USD", "cost": 0.00, "qty": 0.0477, "currency": "USD", "type": "加密貨幣"},
]

# ==========================================
# 3. 驗證登入
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
# 4. 主程式
# ==========================================
if st.session_state["authentication_status"]:
    authenticator.logout('登出系統', 'sidebar')
    fin_data = load_financials()
    market_info = check_market_status()

    # --- 側邊欄 ---
    with st.sidebar:
        st.header("🌍 市場戰情")
        st.caption(f"TW 時間: {market_info['tw_str']}")
        
        usd_rate = 32.5 
        try:
            usd_ticker = yf.Ticker("USDTWD=X")
            usd_rate = usd_ticker.fast_info['last_price']
            st.metric("🇺🇸 美金匯率", f"{usd_rate:.2f}")
        except:
            st.warning("匯率連線失敗")

        st.divider()
        st.markdown(f"**🇺🇸 美股**: {market_info['us_status']} ({market_info['us_time_str']})")
        st.markdown(f"**🇬🇧 英股**: {market_info['uk_status']} ({market_info['uk_time_str']})")

    st.title(f"📊 {st.session_state['name']} 的資產總管")

    # --- 財務設定 ---
    with st.expander("💰 現金與貸款設定", expanded=False):
        with st.form("financial_form"):
            c1, c2, c3, c4 = st.columns(4)
            in_loan = c1.number_input("目前貸款 (TWD)", value=fin_data.get('loan', 0.0), step=10000.0)
            in_cash_acc = c2.number_input("帳戶現金 (TWD)", value=fin_data.get('cash_account', 0.0), step=1000.0)
            in_cash_set = c3.number_input("交割中現金 (TWD)", value=fin_data.get('cash_settlement', 0.0), step=1000.0)
            in_cash_usd = c4.number_input("美元現金 (USD)", value=fin_data.get('cash_usd', 0.0), step=10.0)
            
            if st.form_submit_button("💾 更新財務數據"):
                save_financials({"loan": in_loan, "cash_account": in_cash_acc, "cash_settlement": in_cash_set, "cash_usd": in_cash_usd})
                st.success("更新成功")
                st.rerun()

    # --- 計算邏輯 ---
    portfolio = {} 
    for item in INITIAL_ASSETS:
        code = item['code']
        if code not in portfolio:
            # 預設類別邏輯 (如果初始資料沒寫 type，簡單判斷一下)
            asset_type = item.get('type', '股票')
            portfolio[code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': item['currency'], 'type': asset_type}
        portfolio[code]['qty'] += item['qty']
        portfolio[code]['total_cost'] += item['cost'] * item['qty']

    if os.path.exists(DATA_FILE):
        df_trades = pd.read_csv(DATA_FILE)
        if not df_trades.empty:
            df_trades["代號"] = df_trades["代號"].astype(str).apply(lambda x: x + ".TW" if x.isdigit() and len(x) == 4 else x.upper())
            df_trades["股數"] = pd.to_numeric(df_trades["股數"])
            df_trades["價格"] = pd.to_numeric(df_trades["價格"])
            
            for index, row in df_trades.iterrows():
                t_code = row['代號']
                t_action = row['動作']
                t_qty = row['股數']
                t_price = row['價格']
                
                if t_code not in portfolio:
                    portfolio[t_code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': 'TWD', 'type': '新倉'}

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

    total_stock_value_twd = 0
    display_rows = []
    
    # 用來畫圖的資料
    chart_data = []

    active_assets = [(k, v) for k, v in portfolio.items() if v['qty'] > 0.0001]
    
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

        # 收集畫圖資料
        chart_data.append({
            "Asset": code,
            "Value": market_value_twd,
            "Type": data['type'], # 使用資產類別
            "Currency": currency
        })

    fin_loan = fin_data.get('loan', 0.0)
    fin_cash_acc = fin_data.get('cash_account', 0.0)
    fin_cash_set = fin_data.get('cash_settlement', 0.0)
    fin_cash_usd = fin_data.get('cash_usd', 0.0)
    fin_cash_usd_twd = fin_cash_usd * usd_rate
    total_cash_twd = fin_cash_acc + fin_cash_set + fin_cash_usd_twd

    total_net_worth = (total_stock_value_twd + total_cash_twd) - fin_loan

    # --- 儀表板 ---
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 總淨資產", f"${total_net_worth:,.0f}")
    m2.metric("📉 總負債", f"${fin_loan:,.0f}", delta_color="inverse")
    m3.metric("💵 總現金", f"${total_cash_twd:,.0f}")
    m4.metric("📈 股票市值", f"${total_stock_value_twd:,.0f}")

    # --- ★★★ 視覺化圖表區 (Visuals) ★★★ ---
    st.divider()
    st.subheader("🎨 資產視覺化分析")
    
    # 準備資料：加上現金部位，讓圓餅圖更完整
    if total_cash_twd > 0:
        chart_data.append({"Asset": "現金", "Value": total_cash_twd, "Type": "現金", "Currency": "TWD"})
    
    df_chart = pd.DataFrame(chart_data)

    if not df_chart.empty:
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("##### 🍰 資產配置 (依類別)")
            # 圓餅圖：顯示 台股/美股/債券/現金 的比例
            fig_pie = px.pie(df_chart, values='Value', names='Type', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with c2:
            st.markdown("##### 🗺️ 持股權重 (依市值)")
            # 樹狀圖：顯示每一支股票的大小塊，股票越大塊代表錢越多
            # 過濾掉現金，只看投資部位
            df_invest = df_chart[df_chart['Type'] != '現金']
            fig_tree = px.treemap(df_invest, path=['Type', 'Asset'], values='Value',
                                  color='Value', color_continuous_scale='RdBu')
            st.plotly_chart(fig_tree, use_container_width=True)

    # --- 表格與記帳 ---
    st.divider()
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

    with st.expander("➕ 新增交易紀錄"):
        with st.form("trade_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            t_date = c1.date_input("日期", value=datetime.now())
            t_code = c2.text_input("股票代號", placeholder="006208")
            t_action = c3.selectbox("動作", ["買入", "賣出"])
            t_price = c4.number_input("成交價格", min_value=0.0, step=0.01, value=None)
            t_qty = st.number_input("成交股數", min_value=0.0, step=0.001, value=None)
            
            if st.form_submit_button("儲存"):
                if t_code and t_price and t_qty:
                    final_code = t_code + ".TW" if t_code.isdigit() and len(t_code) == 4 else t_code.upper()
                    new_data = pd.DataFrame([{"日期": t_date, "代號": final_code, "動作": t_action, "價格": t_price, "股數": t_qty, "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                    mode = 'a' if os.path.isfile(DATA_FILE) else 'w'
                    header = not os.path.isfile(DATA_FILE)
                    new_data.to_csv(DATA_FILE, mode=mode, header=header, index=False, encoding='utf-8-sig')
                    st.success(f"✅ 已記錄 {final_code}")
                    st.rerun()

    if os.path.exists(DATA_FILE):
        with st.expander("📋 歷史交易 (可編輯)"):
            df_hist = pd.read_csv(DATA_FILE)
            if not df_hist.empty:
                df_hist["代號"] = df_hist["代號"].astype(str)
                df_hist["日期"] = pd.to_datetime(df_hist["日期"]).dt.date
                edited_df = st.data_editor(df_hist, num_rows="dynamic", use_container_width=True, key="history")
                if st.button("💾 儲存歷史"):
                    edited_df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    st.rerun()

elif st.session_state["authentication_status"] is False:
    st.error('帳號或密碼錯誤')
elif st.session_state["authentication_status"] is None:
    st.warning('請輸入帳號密碼進入系統')