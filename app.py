import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# ==========================================================
# 1. 基礎設定
# ==========================================================
st.set_page_config(page_title="Zhang's Smart Cloud Dashboard", page_icon="💰", layout="wide")

with st.sidebar:
    st.header("🔄 數據同步")
    if st.button("🚀 手動更新最新數據"):
        st.cache_data.clear()
        st.rerun()
    st.divider()

conn = st.connection("gsheets", type=GSheetsConnection)

SHEET_HOLDINGS = "holdings"
SHEET_LOGS = "trade_logs"
SHEET_SETTINGS = "settings"
SHEET_HISTORY = "net_worth_history"

# ==========================================================
# 2. 資料讀取與解析
# ==========================================================
def load_all_data():
    df_holdings = conn.read(worksheet=SHEET_HOLDINGS, ttl=0)
    df_settings = conn.read(worksheet=SHEET_SETTINGS, ttl=0, header=None)
    df_history = conn.read(worksheet=SHEET_HISTORY, ttl=0)
    df_logs = conn.read(worksheet=SHEET_LOGS, ttl=0)
    return df_holdings, df_settings, df_history, df_logs

def parse_settings(df_settings):
    # 預設值
    s_dict = {"loan": 1529264.0, "cash_usd": 3148.49, "cash_twd": 0.0, "settle_twd": 0.0}
    if df_settings.empty: return s_dict
    
    key_map = {
        "目前帳戶現金(TWD)": "cash_twd",
        "交割中現金(TWD)": "settle_twd",
        "美元現金(USD)": "cash_usd",
        "目前貸款金額(TWD)": "loan"
    }
    for _, row in df_settings.iterrows():
        label = str(row[0]).strip()
        if label in key_map:
            try: s_dict[key_map[label]] = float(str(row[1]).replace(',', ''))
            except: pass
    return s_dict

@st.cache_data(ttl=300)
def fetch_market_data(symbols):
    if not symbols: return {}, 31.60
    symbols_to_fetch = list(set(symbols)) + ["TWD=X"]
    try:
        tickers = yf.Tickers(" ".join(symbols_to_fetch))
        rate = tickers.tickers["TWD=X"].history(period="1d")['Close'].iloc[-1]
    except: rate = 31.65
    
    prices = {}
    for sym in symbols:
        try:
            h = tickers.tickers[sym].history(period="1d")
            prices[sym] = h['Close'].iloc[-1] if not h.empty else 0.0
        except: prices[sym] = 0.0
    return prices, rate

# ==========================================================
# 3. 核心寫入與計算邏輯 (對齊券商明細)
# ==========================================================
def process_trade(trade_data, holdings_df, logs_df, settings):
    # 1. 抓取欄位名稱
    col_sym = "Yahoo代號(Symbol)"
    col_avg = "均價(原幣)"
    col_shares = "持有股數"
    col_cost = "成本(原幣)"
    
    symbol = trade_data["symbol"]
    is_buy = trade_data["type"] == "買入"
    
    # 2. 自動抓取均價 (賣出防呆核心)
    avg_cost_price = 0.0
    target_idx = -1
    if not holdings_df.empty:
        matches = holdings_df[holdings_df[col_sym] == symbol].index
        if not matches.empty:
            target_idx = matches[0]
            avg_cost_price = float(holdings_df.at[target_idx, col_avg] or 0)

    # 3. 計算各項金額 (對齊券商 image.png)
    qty = trade_data["shares"]
    price = trade_data["price"]
    fee = trade_data["fee"]
    tax = trade_data["tax"]
    
    val_total = price * qty # 價金
    # 應收付: 買入則是負出, 賣出則是淨收
    net_receivable = val_total - fee - tax if not is_buy else (val_total + fee)
    
    cost_basis = 0.0
    profit = ""
    roi = ""
    
    if not is_buy:
        cost_basis = avg_cost_price * qty # 持有成本
        profit = net_receivable - cost_basis # 損益
        roi = f"{(profit / cost_basis):.2%}" if cost_basis > 0 else "0%"

    # 4. 寫入 19 欄位 Log
    log_entry = {
        "日期": trade_data["date"], "交易類型": trade_data["type"], "平台": trade_data["platform"],
        "帳戶類型": trade_data["account"], "幣別": trade_data["currency"], "名稱": trade_data["name"],
        "股票代號": symbol, "賣出價格": price if not is_buy else "", "賣出股數": qty if not is_buy else "",
        "買入價格": price if is_buy else "", "買入股數": qty if is_buy else "", "手續費": fee, "交易稅": tax,
        "成本(原幣)※賣出需填": cost_basis if not is_buy else "", "價金(原幣)": val_total,
        "應收付(原幣)": net_receivable, "損益(原幣)": profit, "報酬率": roi,
        "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # 更新 Logs 並寫入雲端
    new_logs = pd.concat([logs_df, pd.DataFrame([log_entry])], ignore_index=True)
    conn.update(worksheet=SHEET_LOGS, data=new_logs)

    # 5. 更新 Holdings 庫存
    if target_idx != -1:
        curr_s = float(holdings_df.at[target_idx, col_shares] or 0)
        curr_c = float(holdings_df.at[target_idx, col_cost] or 0)
        if is_buy:
            new_s = curr_s + qty
            new_c = curr_c + val_total + fee
            holdings_df.at[target_idx, col_shares] = new_s
            holdings_df.at[target_idx, col_cost] = new_c
            holdings_df.at[target_idx, col_avg] = new_c / new_s
        else:
            holdings_df.at[target_idx, col_shares] = max(0, curr_s - qty)
            # 賣出時減少對應比例的成本
            holdings_df.at[target_idx, col_cost] = max(0, curr_c - (avg_cost_price * qty))
        
        conn.update(worksheet=SHEET_HOLDINGS, data=holdings_df)
        st.success(f"✅ 已成功紀錄並同步庫存！損益: {profit}")

# ==========================================================
# 4. 主程式 UI
# ==========================================================
def main():
    st.title("💰 翔翔的雲端投資戰情室 V12.0")
    
    df_h, df_s, df_his, df_l = load_all_data()
    settings = parse_settings(df_s)
    
    # 同步市價
    symbols = df_h["Yahoo代號(Symbol)"].tolist() if not df_h.empty else []
    prices, rate = fetch_market_data(symbols)
    
    # 計算資產
    stock_mv = 0
    if not df_h.empty:
        def calc_mv(row):
            p = prices.get(row["Yahoo代號(Symbol)"], 0)
            s = float(str(row["持有股數"]).replace(',', ''))
            mv = p * s * (rate if row["幣別"] == "USD" else 1)
            return mv
        df_h["市值(TWD)"] = df_h.apply(calc_mv, axis=1)
        stock_mv = df_h["市值(TWD)"].sum()

    # 淨值公式校正
    net_worth = (settings["cash_twd"] + settings["settle_twd"] + (settings["cash_usd"] * rate) + stock_mv) - settings["loan"]

    # 看板
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("資產總淨值", f"${net_worth:,.0f}")
    m2.metric("證券總市值", f"${stock_mv:,.0f}")
    m3.metric("貸款餘額", f"${settings['loan']:,.0f}", delta_color="inverse")
    m4.metric("美元匯率", f"{rate:.2f}")

    tab1, tab2, tab3, tab4 = st.tabs(["📊 視覺化分析", "➕ 新增交易", "📋 持倉明細", "⚙️ 資金設定"])

    with tab1:
        if not df_his.empty:
            fig = px.line(df_his, x=df_his.columns[0], y=df_his.columns[1], title="資產淨值走勢", markers=True)
            fig.update_xaxes(tickformat="%Y/%m/%d")
            st.plotly_chart(fig, use_container_width=True)
        # 矩形圖與圓餅圖 (代碼同前)
        st.plotly_chart(px.treemap(df_h, path=["投資地區", "Yahoo代號(Symbol)"], values="市值(TWD)", title="持股分佈"), use_container_width=True)

    with tab2:
        st.subheader("➕ 新增交易紀錄 (對齊券商格式)")
        with st.form("trade_form"):
            c1, c2 = st.columns(2)
            d_date = c1.date_input("日期", datetime.now())
            d_type = c2.selectbox("交易類型", ["買入", "賣出"])
            
            d_sym = st.selectbox("股票代號", symbols)
            row = df_h[df_h["Yahoo代號(Symbol)"] == d_sym].iloc[0]
            
            # 防呆預覽：抓取均價
            current_avg = float(row["均價(原幣)"] or 0)
            if d_type == "賣出":
                st.info(f"💡 防呆提醒：該標目前的持有均價為 {current_avg:.2f}")

            c3, c4 = st.columns(2)
            d_price = c3.number_input("成交價格", min_value=0.0, format="%.2f")
            d_shares = c4.number_input("成交股數", min_value=0.0)
            
            c5, c6 = st.columns(2)
            d_fee = c5.number_input("手續費", min_value=0)
            d_tax = c6.number_input("交易稅 (賣出才填)", min_value=0)
            
            if st.form_submit_button("送出交易並同步雲端"):
                trade_data = {
                    "date": d_date.strftime("%Y/%m/%d"), "type": d_type, "symbol": d_sym,
                    "name": row["標的名稱"], "platform": row["平台"], "account": row["帳戶類型"],
                    "currency": row["幣別"], "price": d_price, "shares": d_shares,
                    "fee": d_fee, "tax": d_tax
                }
                process_trade(trade_data, df_h, df_l, settings)
                st.rerun()

    with tab3:
        st.dataframe(df_h[["Yahoo代號(Symbol)", "標的名稱", "持有股數", "均價(原幣)", "市值(TWD)"]], use_container_width=True)

    with tab4:
        # 設定更新邏輯 (同前)
        pass

if __name__ == "__main__":
    main()