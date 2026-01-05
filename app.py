import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import yfinance as yf
import pandas as pd
import os
from datetime import datetime

# ==========================================
# 0. 基礎設定與初始資產數據 (來自 Excel)
# ==========================================
st.set_page_config(page_title="投資戰情室", layout="wide")
DATA_FILE = "data/trades.csv"

# 確保 data 資料夾存在
if not os.path.exists("data"):
    os.makedirs("data")

# ★★★ 核心數據：初始持倉 (基期) ★★★
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
# 1. 讀取設定與驗證
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
# 2. 主程式邏輯
# ==========================================
if st.session_state["authentication_status"]:
    authenticator.logout('登出系統', 'sidebar')
    st.title(f"📈 {st.session_state['name']} 的資產戰情室")

    # --- A. 抓取即時匯率 ---
    usd_rate = 32.5 
    with st.sidebar:
        st.header("市場數據")
        try:
            usd_ticker = yf.Ticker("USDTWD=X")
            usd_rate = usd_ticker.fast_info['last_price']
            st.metric("美金匯率 (USD/TWD)", f"{usd_rate:.2f}")
        except:
            st.warning("匯率抓取失敗，使用預設值")

    # --- B. 核心邏輯：交易回放引擎 (Replay Engine) ---
    # 這個引擎會算出：1.目前的庫存 2.每一筆歷史交易的損益
    
    # 1. 建立初始資產庫
    # portfolio 結構: { '2330.TW': {'qty': 140, 'total_cost': 200939, 'currency': 'TWD'}, ... }
    portfolio = {} 
    
    for item in INITIAL_ASSETS:
        code = item['code']
        if code not in portfolio:
            portfolio[code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': item['currency']}
        
        portfolio[code]['qty'] += item['qty']
        portfolio[code]['total_cost'] += item['cost'] * item['qty']

    # 2. 讀取並處理交易紀錄
    history_display_data = [] # 用來顯示在下方的詳細表格

    if os.path.exists(DATA_FILE):
        df_trades = pd.read_csv(DATA_FILE)
        if not df_trades.empty:
            # ★★★ 關鍵修正 1：自動校正股票代號 ★★★
            # 把所有 "006208" (純數字且長度4) 強制轉成 "006208.TW"
            df_trades["代號"] = df_trades["代號"].astype(str).apply(
                lambda x: x + ".TW" if x.isdigit() and len(x) == 4 else x.upper()
            )
            df_trades["股數"] = pd.to_numeric(df_trades["股數"])
            df_trades["價格"] = pd.to_numeric(df_trades["價格"])
            
            # 確保按照時間順序計算
            # 這裡假設 CSV 是照順序寫入的，若不是則需 sort_values("建立時間")

            for index, row in df_trades.iterrows():
                t_code = row['代號']
                t_action = row['動作']
                t_qty = row['股數']
                t_price = row['價格']
                t_date = row['日期']
                
                # 初始化新商品 (如果初始資產沒有)
                if t_code not in portfolio:
                    portfolio[t_code] = {'qty': 0.0, 'total_cost': 0.0, 'currency': 'TWD'} # 預設 TWD, 之後可優化

                # 計算當前平均成本
                current_avg_cost = 0
                if portfolio[t_code]['qty'] > 0:
                    current_avg_cost = portfolio[t_code]['total_cost'] / portfolio[t_code]['qty']

                # --- 交易計算 ---
                realized_pnl = None
                trade_roi = None

                if t_action == '買入':
                    # 買入：增加庫存，增加總成本
                    portfolio[t_code]['qty'] += t_qty
                    portfolio[t_code]['total_cost'] += t_price * t_qty
                
                elif t_action == '賣出':
                    # 賣出：減少庫存，減少總成本 (依比例)
                    # ★★★ 關鍵修正 2：計算這一筆的報酬率 ★★★
                    if portfolio[t_code]['qty'] > 0:
                        # 損益 = (賣價 - 平均成本) * 股數
                        realized_pnl = (t_price - current_avg_cost) * t_qty
                        # 報酬率 = (賣價 - 平均成本) / 平均成本
                        if current_avg_cost > 0:
                            trade_roi = ((t_price - current_avg_cost) / current_avg_cost) * 100
                        
                        # 更新庫存 (成本依照賣出比例減少)
                        cost_to_remove = current_avg_cost * t_qty
                        portfolio[t_code]['qty'] -= t_qty
                        portfolio[t_code]['total_cost'] -= cost_to_remove
                    else:
                        # 放空或資料錯誤，暫不計算
                        pass

                # 整理這筆資料給歷史表格顯示
                history_display_data.append({
                    "日期": t_date,
                    "代號": t_code,
                    "動作": t_action,
                    "價格": t_price,
                    "股數": t_qty,
                    "損益試算 (TWD)": realized_pnl, # 僅賣出有值
                    "報酬率 %": trade_roi,       # 僅賣出有值
                    "建立時間": row.get('建立時間', '')
                })

    # --- C. 抓取現價並計算市值 (基於回放後的最終庫存) ---
    total_net_worth_twd = 0
    progress_text = "正在同步全球股價..."
    my_bar = st.progress(0, text=progress_text)
    
    display_rows = []
    
    # 將 portfolio 字典轉為列表處理
    active_assets = [(k, v) for k, v in portfolio.items() if v['qty'] > 0.0001]
    
    for i, (code, data) in enumerate(active_assets):
        qty = data['qty']
        avg_cost = data['total_cost'] / qty if qty > 0 else 0
        currency = data['currency']
        
        try:
            ticker = yf.Ticker(code)
            current_price = ticker.fast_info['last_price']
        except:
            current_price = avg_cost 
        
        # 匯率換算
        rate = usd_rate if currency == "USD" else 1
        
        market_value_twd = qty * current_price * rate
        profit_twd = (current_price - avg_cost) * qty * rate
        
        total_net_worth_twd += market_value_twd
        
        roi = ((current_price - avg_cost) / avg_cost) * 100 if avg_cost > 0 else 0

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
        my_bar.progress((i + 1) / len(active_assets), text=f"正在同步 {code}...")

    my_bar.empty()

    # --- D. 戰情室儀表板 ---
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("💰 總資產淨值 (TWD)", f"${total_net_worth_twd:,.0f}")
    
    total_cost_rough = sum([r['平均成本'] * r['持股數'] * (usd_rate if r['幣別']=='USD' else 1) for r in display_rows])
    total_profit = total_net_worth_twd - total_cost_rough
    
    col2.metric("📈 總未實現損益 (TWD)", f"${total_profit:,.0f}", delta_color="normal")
    
    total_roi = (total_profit / total_cost_rough * 100) if total_cost_rough > 0 else 0
    col3.metric("🚀 總投資報酬率", f"{total_roi:.2f}%")

    # --- E. 詳細資產表格 ---
    st.subheader("📊 資產庫存明細")
    df_display = pd.DataFrame(display_rows)
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "平均成本": st.column_config.NumberColumn(format="%.2f"),
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "市值 (TWD)": st.column_config.ProgressColumn(format="$%d", min_value=0, max_value=max(df_display["市值 (TWD)"]) if not df_display.empty else 100),
            "未實現損益 (TWD)": st.column_config.NumberColumn(format="$%d"),
            "報酬率 %": st.column_config.NumberColumn(format="%.2f %%")
        },
        hide_index=True
    )

    # --- F. 記帳區 ---
    st.divider()
    with st.expander("➕ 新增一筆交易 (iPhone 模式)", expanded=True):
        with st.form("trade_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            t_date = c1.date_input("日期", value=datetime.now())
            t_code = c2.text_input("股票代號", placeholder="例如: 006208") # 使用者打 006208 就好
            t_action = c3.selectbox("動作", ["買入", "賣出"])
            t_price = c4.number_input("成交價格", min_value=0.0, step=0.01, value=None, placeholder="輸入價格")
            t_qty = st.number_input("成交股數", min_value=0.0, step=0.001, value=None, placeholder="輸入股數")
            
            if st.form_submit_button("儲存紀錄"):
                if not t_code or t_price is None or t_qty is None:
                    st.error("❌ 資料不完整")
                else:
                    # ★★★ 自動幫使用者加上 .TW ★★★
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
                    
                    st.success(f"✅ 已記錄 {final_code} (若為賣出，請查看下方歷史報酬率)")
                    st.rerun()

    # --- G. 歷史交易 (含損益顯示) ---
    if history_display_data:
        st.divider()
        st.subheader("📋 歷史買賣流水帳 (含損益分析)")
        
        df_hist_show = pd.DataFrame(history_display_data)
        # 顯示順序反轉，最新的在最上面
        df_hist_show = df_hist_show.iloc[::-1]

        st.dataframe(
            df_hist_show,
            use_container_width=True,
            column_config={
                "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
                "價格": st.column_config.NumberColumn("價格", format="$ %.2f"),
                "股數": st.column_config.NumberColumn("股數", format="%.2f"),
                "損益試算 (TWD)": st.column_config.NumberColumn(format="$ %.0f"), # 新增欄位
                "報酬率 %": st.column_config.NumberColumn(format="%.2f %%")      # 新增欄位
            },
            hide_index=True
        )
        
        # 這裡為了簡單，我們保留一個簡單的刪除/修改介面在最下方，但不顯示損益以免混亂
        with st.expander("🛠️ 修正/刪除 原始紀錄"):
            df_raw = pd.read_csv(DATA_FILE)
            if not df_raw.empty:
                df_raw["代號"] = df_raw["代號"].astype(str)
                edited_df = st.data_editor(df_raw, num_rows="dynamic", key="editor")
                if st.button("💾 儲存修改"):
                    edited_df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
                    st.rerun()

# 登入失敗處理
elif st.session_state["authentication_status"] is False:
    st.error('帳號或密碼錯誤')
elif st.session_state["authentication_status"] is None:
    st.warning('請輸入帳號密碼進入系統')