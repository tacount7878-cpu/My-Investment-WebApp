import streamlit as st
import pandas as pd
import yfinance as yf
import xlsxwriter
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
import os

# ==========================================================
# 0) 初始資料設定 (V7.1 - 包含 006208 等最新變動)
# ==========================================================
DEFAULT_HOLDINGS = [
    # 台股
    {"Symbol": "0050.TW",   "Name": "元大台灣50",        "Type": "股票",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 1568276,   "Shares": 30000.0,    "GroupKey": "0050/006208 (大盤)"},
    {"Symbol": "006208.TW", "Name": "富邦台50",          "Type": "股票",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 344534,    "Shares": 2873.0,     "GroupKey": "0050/006208 (大盤)"},
    {"Symbol": "2330.TW",   "Name": "台積電",            "Type": "股票",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 200939,    "Shares": 140.0,      "GroupKey": "2330 (台積電)"},
    {"Symbol": "00679B.TW", "Name": "元大美債20年",      "Type": "債券",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 300412,    "Shares": 11236.0,    "GroupKey": "台股債券 (美債+投等)"},
    {"Symbol": "00719B.TW", "Name": "元大美債1-3年",     "Type": "債券",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 427779,    "Shares": 14371.0,    "GroupKey": "台股債券 (美債+投等)"},
    {"Symbol": "00720B.TW", "Name": "元大投資級公司債",  "Type": "債券",   "Region": "台股", "Platform": "元大(台股)",       "Account": "TWD帳戶",     "Currency": "TWD", "Cost": 299979,    "Shares": 8875.0,     "GroupKey": "台股債券 (美債+投等)"},
    
    # 複委託 (美股/全球) - 注意 SGOV 已清空
    {"Symbol": "VT",        "Name": "Vanguard全球",      "Type": "股票",   "Region": "全球", "Platform": "元大複委託(美股)", "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 18551.05,  "Shares": 139.0,      "GroupKey": "VT/VWRA (全球股票)"},
    {"Symbol": "SGOV",      "Name": "iShares短債",        "Type": "債券",   "Region": "美股", "Platform": "元大複委託(美股)", "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 0.00,      "Shares": 0.0,        "GroupKey": "SGOV (美國短債)"},
    {"Symbol": "TSLA",      "Name": "特斯拉(台)",         "Type": "股票",   "Region": "美股", "Platform": "元大複委託(美股)", "Account": "TWD帳戶",     "Currency": "USD", "Cost": 4244.50,   "Shares": 10.0,       "GroupKey": "TSLA (特斯拉)"},
    {"Symbol": "GOOGL",     "Name": "字母公司(台)",       "Type": "股票",   "Region": "美股", "Platform": "元大複委託(美股)", "Account": "TWD帳戶",     "Currency": "USD", "Cost": 8040.35,   "Shares": 34.0,       "GroupKey": "Google (Alphabet)"},
    {"Symbol": "TSLA",      "Name": "特斯拉",             "Type": "股票",   "Region": "美股", "Platform": "元大複委託(美股)", "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 889.14,    "Shares": 3.0,        "GroupKey": "TSLA (特斯拉)"},
    {"Symbol": "GOOGL",     "Name": "字母公司",           "Type": "股票",   "Region": "美股", "Platform": "元大複委託(美股)", "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 580.25,    "Shares": 2.0,        "GroupKey": "Google (Alphabet)"},
    
    # 海外券商 (IBKR/Firstrade)
    {"Symbol": "VWRA.L",    "Name": "VWRA全球股票",       "Type": "股票",   "Region": "全球", "Platform": "IBKR",            "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 42564.20,  "Shares": 249.17,     "GroupKey": "VT/VWRA (全球股票)"},
    {"Symbol": "IBKR",      "Name": "盈透證券",           "Type": "股票",   "Region": "美股", "Platform": "IBKR",            "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 247.00,    "Shares": 3.84,       "GroupKey": "IBKR (盈透證券)"},
    {"Symbol": "TSLA",      "Name": "特斯拉(FT)",         "Type": "股票",   "Region": "美股", "Platform": "Firstrade(FT)",    "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 2468.00,   "Shares": 5.55,       "GroupKey": "TSLA (特斯拉)"},
    {"Symbol": "GOOG",      "Name": "字母公司(FT)",       "Type": "股票",   "Region": "美股", "Platform": "Firstrade(FT)",    "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 1438.00,   "Shares": 4.57,       "GroupKey": "Google (Alphabet)"},
    {"Symbol": "VTI",       "Name": "美國大盤(FT)",       "Type": "股票",   "Region": "美股", "Platform": "Firstrade(FT)",    "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 1224.00,   "Shares": 3.65,       "GroupKey": "VTI (美國大盤)"},
    {"Symbol": "SGOV",      "Name": "短債現金(FT)",       "Type": "債券",   "Region": "美股", "Platform": "Firstrade(FT)",    "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 1000.00,   "Shares": 9.95,       "GroupKey": "SGOV (美國短債)"},
    
    # 加密貨幣
    {"Symbol": "BTC-USD",   "Name": "比特幣",             "Type": "虛擬幣", "Region": "加密", "Platform": "錢包",             "Account": "USD外幣帳戶", "Currency": "USD", "Cost": 0.00,      "Shares": 0.058469,   "GroupKey": "Bitcoin (比特幣)"},
]

# 預設現金與貸款 (依照截圖 image_2231d3.png 更新)
DEFAULT_SETTINGS = {
    "Cash_TWD": 0,          
    "Cash_USD": 3148.49,    
    "Loan_TWD": 1529264,    
}

# 檔案名稱設定
DATA_FILE = "my_holdings_data.csv"
SETTINGS_FILE = "my_settings.csv"
HISTORY_FILE = "my_networth_history.csv"

st.set_page_config(page_title="My Smart Dashboard", page_icon="💰", layout="wide")

# ==========================================================
# 1) 資料讀寫函數
# ==========================================================
def load_data():
    # 讀取持倉
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
    else:
        df = pd.DataFrame(DEFAULT_HOLDINGS)
        df.to_csv(DATA_FILE, index=False)
    
    # 讀取設定(現金/貸款)
    if os.path.exists(SETTINGS_FILE):
        settings = pd.read_csv(SETTINGS_FILE).iloc[0].to_dict()
    else:
        settings = DEFAULT_SETTINGS
        pd.DataFrame([settings]).to_csv(SETTINGS_FILE, index=False)

    # 讀取歷史淨值
    if os.path.exists(HISTORY_FILE):
        history_df = pd.read_csv(HISTORY_FILE)
    else:
        history_df = pd.DataFrame(columns=["Date", "NetWorth"])
        
    return df, settings, history_df

def save_data(df, settings_dict):
    df.to_csv(DATA_FILE, index=False)
    pd.DataFrame([settings_dict]).to_csv(SETTINGS_FILE, index=False)
    st.toast("✅ 持倉與設定已更新！")

def save_history(net_worth):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_record = pd.DataFrame([{"Date": date_str, "NetWorth": int(net_worth)}])
    
    if os.path.exists(HISTORY_FILE):
        new_record.to_csv(HISTORY_FILE, mode='a', header=False, index=False)
    else:
        new_record.to_csv(HISTORY_FILE, index=False)
    st.toast(f"✅ 已紀錄今日淨值：${int(net_worth):,}")

# ==========================================================
# 2) 抓取股價
# ==========================================================
@st.cache_data(ttl=300)
def fetch_live_prices(symbols):
    # 去除重複並加入匯率
    symbols_to_fetch = list(set(symbols)) + ["TWD=X"]
    
    try:
        tickers = yf.Tickers(" ".join(symbols_to_fetch))
        usd_twd_rate = tickers.tickers["TWD=X"].history(period="1d")['Close'].iloc[-1]
    except:
        usd_twd_rate = 32.50 # 備用匯率
    
    prices = {}
    for sym in symbols:
        try:
            p = tickers.tickers[sym].history(period="1d")['Close'].iloc[-1]
            prices[sym] = p
        except:
            prices[sym] = 0.0
            
    return prices, usd_twd_rate

# ==========================================================
# 3) Excel 生成邏輯
# ==========================================================
def generate_excel(df, settings, prices, usd_rate, net_worth):
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"strings_to_formulas": False})
    
    # 樣式
    header_fmt = workbook.add_format({"bold": True, "align": "center", "bg_color": "#1F4E78", "font_color": "white", "border": 1})
    input_fmt = workbook.add_format({"align": "center", "bg_color": "#FFF2CC", "border": 1})
    price_fmt = workbook.add_format({"num_format": "#,##0.00", "align": "center", "bg_color": "#E2EFDA", "font_color": "#375623", "bold": True, "border": 1})
    calc_fmt = workbook.add_format({"num_format": "#,##0", "bg_color": "#F2F2F2", "border": 1})
    networth_fmt = workbook.add_format({"num_format": "#,##0", "bold": True, "font_size": 16, "align": "center", "border": 2, "bg_color": "#E2EFDA"})

    ws = workbook.add_worksheet("資產戰情室")
    ws.set_column("A:A", 20); ws.set_column("B:C", 15)

    ws.write("A1", "美元匯率", header_fmt); ws.write("A2", usd_rate, input_fmt)
    ws.write("C1", "現金(TWD)", header_fmt); ws.write("C2", settings["Cash_TWD"], input_fmt)
    ws.write("E1", "現金(USD)", header_fmt); ws.write("E2", settings["Cash_USD"], input_fmt)
    ws.write("G1", "貸款", header_fmt); ws.write("G2", settings["Loan_TWD"], input_fmt)
    ws.write("K1", "資產總淨值", header_fmt); ws.write("K2", net_worth, networth_fmt)

    cols = ["Symbol", "Name", "Type", "Region", "Platform", "Shares", "Cost", "Price", "MarketValue(TWD)"]
    for c, h in enumerate(cols):
        ws.write(4, c, h, header_fmt)

    r = 5
    for idx, row in df.iterrows():
        sym = row["Symbol"]
        shares = row["Shares"]
        price = prices.get(sym, 0)
        
        if row["Currency"] == "USD":
            mv_twd = price * shares * usd_rate
        else:
            mv_twd = price * shares

        ws.write(r, 0, sym, input_fmt)
        ws.write(r, 1, row["Name"], input_fmt)
        ws.write(r, 2, row["Type"], input_fmt)
        ws.write(r, 3, row["Region"], input_fmt)
        ws.write(r, 4, row["Platform"], input_fmt)
        ws.write(r, 5, shares, calc_fmt)
        ws.write(r, 6, row["Cost"], calc_fmt)
        ws.write(r, 7, price, price_fmt)
        ws.write(r, 8, mv_twd, calc_fmt)
        r += 1

    workbook.close()
    return output.getvalue()

# ==========================================================
# 4) 主程式 UI
# ==========================================================
def main():
    st.title("💰 Zhang's Smart Dashboard V7.1")
    
    # 1. 載入資料
    df, settings, history_df = load_data()

    # 2. 側邊欄：設定
    with st.sidebar:
        st.header("⚙️ 帳戶設定")
        new_cash_twd = st.number_input("TWD 現金總額", value=int(settings["Cash_TWD"]), step=1000)
        new_cash_usd = st.number_input("USD 現金總額", value=float(settings["Cash_USD"]), step=100.0)
        new_loan = st.number_input("目前貸款金額", value=int(settings["Loan_TWD"]), step=10000)
        
        if st.button("更新設定"):
            settings["Cash_TWD"] = new_cash_twd
            settings["Cash_USD"] = new_cash_usd
            settings["Loan_TWD"] = new_loan
            save_data(df, settings)
            st.rerun()

    # 3. 抓取股價
    symbols_list = df["Symbol"].tolist()
    with st.spinner('連線報價中...'):
        live_prices, usd_rate = fetch_live_prices(symbols_list)

    # 4. 計算市值
    def calc_mv_twd(row):
        p = live_prices.get(row["Symbol"], 0)
        if row["Currency"] == "USD":
            return p * row["Shares"] * usd_rate
        else:
            return p * row["Shares"]

    df["Price"] = df["Symbol"].map(live_prices).fillna(0)
    df["MarketValueTWD"] = df.apply(calc_mv_twd, axis=1)

    total_stock_val = df["MarketValueTWD"].sum()
    total_cash_val = settings["Cash_TWD"] + (settings["Cash_USD"] * usd_rate)
    net_worth = total_cash_val + total_stock_val - settings["Loan_TWD"]

    # --- 頂部按鈕區 ---
    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        if st.button("📝 紀錄今日淨值"):
            save_history(net_worth)
            st.rerun()

    # --- 分頁 ---
    tab1, tab2, tab3 = st.tabs(["📊 資產戰情室 (含圖表)", "📝 資料管理", "📥 報表下載"])

    # === Tab 1: 戰情室 ===
    with tab1:
        # 1. 關鍵數字
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("資產總淨值 (TWD)", f"${net_worth:,.0f}", delta=None)
        c2.metric("證券總市值", f"${total_stock_val:,.0f}")
        c3.metric("貸款餘額", f"${settings['Loan_TWD']:,.0f}", delta_color="inverse")
        c4.metric("美元匯率", f"{usd_rate:.2f}")

        st.markdown("---")
        
        # 2. 歷史折線圖
        if not history_df.empty:
            st.subheader("📈 資產總淨值歷史折線圖")
            fig_line = px.line(history_df, x="Date", y="NetWorth", markers=True)
            fig_line.update_layout(yaxis_title="TWD", xaxis_title="時間")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("尚無歷史紀錄，請點擊上方「紀錄今日淨值」按鈕開始紀錄。")

        st.markdown("---")

        # 3. 矩形樹狀圖 (Treemap)
        # 建立分類欄位
        def get_chart_group(row):
            if row['Region'] == '台股' and row['Type'] == '股票': return '台股'
            if row['Region'] == '台股' and row['Type'] == '債券': return '債券' 
            if row['Region'] == '全球': return '全球ETF'
            if row['Region'] == '美股' and row['Type'] == '股票': return '美股'
            if row['Region'] == '美股' and row['Type'] == '債券': return '美債'
            if row['Region'] == '加密': return '加密貨幣'
            return '其他'
        
        df['ChartGroup'] = df.apply(get_chart_group, axis=1)

        st.subheader("🗺️ 持股權重 (依市值)")
        fig_tree = px.treemap(
            df,
            path=['ChartGroup', 'Symbol'],
            values='MarketValueTWD',
            color='MarketValueTWD',
            color_continuous_scale='RdBu',
            hover_data=['Name', 'Price'],
        )
        st.plotly_chart(fig_tree, use_container_width=True)

        # 4. 圓餅圖 (地區 & 資產)
        col_pie1, col_pie2 = st.columns(2)
        with col_pie1:
            st.subheader("🌍 投資地區分佈")
            fig_region = px.pie(df, values='MarketValueTWD', names='Region', hole=0.0)
            st.plotly_chart(fig_region, use_container_width=True)

        with col_pie2:
            st.subheader("📊 持倉佔比 (合併後)")
            fig_group = px.pie(df, values='MarketValueTWD', names='GroupKey', hole=0.4)
            st.plotly_chart(fig_group, use_container_width=True)

    # === Tab 2: 資料管理 ===
    with tab2:
        st.info("💡 在這裡修改股數或成本，記得按下方「儲存修改」")
        
        edit_cols = ["Symbol", "Name", "Type", "Region", "Platform", "Account", "Currency", "Cost", "Shares", "GroupKey"]
        
        edited_df = st.data_editor(
            df[edit_cols], 
            num_rows="dynamic",
            use_container_width=True,
            height=600,
            column_config={
                "Cost": st.column_config.NumberColumn("總成本", format="$%d"),
                "Shares": st.column_config.NumberColumn("股數", format="%.4f"),
            }
        )

        if st.button("💾 儲存修改 (Sync)"):
            save_data(edited_df, settings)
            st.success("資料已更新！")
            st.rerun()

    # === Tab 3: 下載 ===
    with tab3:
        st.subheader("匯出 Excel")
        excel_data = generate_excel(df, settings, live_prices, usd_rate, net_worth)
        st.download_button(
            label="下載 Excel (V7.1_Live)",
            data=excel_data,
            file_name=f"Smart_Dashboard_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()