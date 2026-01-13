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
def load_all_data(force_reload: bool = False):
    """
    force_reload=True 時，ttl=0 直接讀最新（避免你剛寫入但又被 ttl=10 的快取擋住）
    """
    ttl_val = 0 if force_reload else 10
    try:
        df_holdings = conn.read(worksheet=SHEET_HOLDINGS, ttl=ttl_val)
        df_settings = conn.read(worksheet=SHEET_SETTINGS, ttl=ttl_val, header=None)
        df_history = conn.read(worksheet=SHEET_HISTORY, ttl=ttl_val)
        df_logs = conn.read(worksheet=SHEET_LOGS, ttl=ttl_val)
        return df_holdings, df_settings, df_history, df_logs
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def parse_settings(df_settings):
    s_dict = {"loan": 1529264.0, "cash_usd": 3148.49, "cash_twd": 0.0, "settle_twd": 0.0}
    if df_settings.empty:
        return s_dict
    key_map = {
        "目前帳戶現金(TWD)": "cash_twd",
        "交割中現金(TWD)": "settle_twd",
        "美元現金(USD)": "cash_usd",
        "目前貸款金額(TWD)": "loan"
    }
    for _, row in df_settings.iterrows():
        label = str(row[0]).strip()
        if label in key_map:
            try:
                s_dict[key_map[label]] = float(str(row[1]).replace(',', ''))
            except:
                pass
    return s_dict

@st.cache_data(ttl=300)
def fetch_market_data(symbols):
    if not symbols:
        return {}, 31.60
    symbols_to_fetch = list(set(symbols)) + ["TWD=X"]
    try:
        tickers = yf.Tickers(" ".join(symbols_to_fetch))
        rate = tickers.tickers["TWD=X"].history(period="1d")["Close"].iloc[-1]
    except:
        rate = 31.65
    prices = {}
    for sym in symbols:
        try:
            h = tickers.tickers[sym].history(period="1d")
            prices[sym] = h["Close"].iloc[-1] if not h.empty else 0.0
        except:
            prices[sym] = 0.0
    return prices, rate

# --- 顯示格式化工具 ---
def format_amount(val, currency):
    if pd.isna(val) or val == "":
        return ""
    try:
        v = float(val)
        if str(currency).strip().upper() == "TWD":
            return f"{v:,.0f}"
        else:
            return f"{v:,.3f}"
    except:
        return val

def format_shares(val):
    if pd.isna(val) or val == "":
        return ""
    try:
        return f"{float(val):,.3f}"
    except:
        return val

def format_roi_pct(val):
    if pd.isna(val) or val == "":
        return ""
    try:
        if isinstance(val, str) and "%" in val:
            return val
        v = float(val)
        return f"{v:.2%}"
    except:
        return val

# ==========================================================
# 3. 核心寫入與計算邏輯
# ==========================================================
def process_trade(trade_data, holdings_df, logs_df):
    col_sym = "Yahoo代號(Symbol)"
    col_avg = "均價(原幣)"
    col_shares = "持有股數"
    col_cost = "成本(原幣)"

    symbol = trade_data["symbol"]
    is_buy = trade_data["type"] == "買入"

    target_idx = -1
    if not holdings_df.empty:
        matches = holdings_df[holdings_df[col_sym] == symbol].index
        if not matches.empty:
            target_idx = matches[0]

    qty = trade_data["shares"]
    price = trade_data["price"]
    fee = trade_data["fee"]
    tax = trade_data["tax"]

    val_calculated = price * qty
    manual_principal = trade_data.get("manual_principal", 0)
    val_final = manual_principal if manual_principal > 0 else val_calculated

    manual_cost = trade_data.get("manual_cost", 0)

    net_receivable = val_final - fee - tax if not is_buy else (val_final + fee)

    cost_basis = 0.0
    profit = ""
    roi = ""

    if not is_buy:
        if manual_cost > 0:
            cost_basis = manual_cost
        else:
            avg_cost_price = 0.0
            if target_idx != -1:
                avg_cost_price = float(holdings_df.at[target_idx, col_avg] or 0)
            cost_basis = avg_cost_price * qty

        profit = net_receivable - cost_basis
        roi = f"{(profit / cost_basis):.2%}" if cost_basis > 0 else "0%"

    log_entry = {
        "日期": trade_data["date"],
        "交易類型": trade_data["type"],
        "平台": trade_data["platform"],
        "帳戶類型": trade_data["account"],
        "幣別": trade_data["currency"],
        "名稱": trade_data["name"],
        "股票代號": symbol,
        "賣出價格": price if not is_buy else "",
        "賣出股數": qty if not is_buy else "",
        "買入價格": price if is_buy else "",
        "買入股數": qty if is_buy else "",
        "手續費": fee,
        "交易稅": tax,
        "成本(原幣)※賣出需填": cost_basis if not is_buy else "",
        "價金(原幣)": val_final,
        "應收付(原幣)": net_receivable,
        "損益(原幣)": profit,
        "報酬率": roi,
        "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    new_logs = pd.concat([logs_df, pd.DataFrame([log_entry])], ignore_index=True)
    conn.update(worksheet=SHEET_LOGS, data=new_logs)

    if target_idx != -1:
        curr_s = float(holdings_df.at[target_idx, col_shares] or 0)
        curr_c = float(holdings_df.at[target_idx, col_cost] or 0)

        if is_buy:
            new_s = curr_s + qty
            new_c = curr_c + val_final + fee
            holdings_df.at[target_idx, col_shares] = new_s
            holdings_df.at[target_idx, col_cost] = new_c
            holdings_df.at[target_idx, col_avg] = new_c / new_s if new_s > 0 else 0
        else:
            holdings_df.at[target_idx, col_shares] = max(0, curr_s - qty)
            holdings_df.at[target_idx, col_cost] = max(0, curr_c - cost_basis)

        conn.update(worksheet=SHEET_HOLDINGS, data=holdings_df)

        # ✅ 用 pending_nav 兩段式導頁（避免改到 radio 的 key）
        st.session_state["pending_nav"] = "➕ 新增交易"
        st.session_state["force_reload"] = True

        if is_buy:
            st.session_state["last_trade_msg"] = f"✅ 買入成功！總支出: {net_receivable:,.0f}"
        else:
            st.session_state["last_trade_msg"] = f"✅ 賣出成功！損益: {profit:,.0f}"

        st.cache_data.clear()
    else:
        st.session_state["pending_nav"] = "➕ 新增交易"
        st.session_state["force_reload"] = True
        st.session_state["last_trade_msg"] = "⚠️ holdings 找不到該代號：已寫入 trade_logs，但未更新 holdings。"
        st.cache_data.clear()

# ==========================================================
# 4. 主程式 UI
# ==========================================================
def main():
    st.title("💰 翔翔的雲端投資戰情室 V17.2")

    NAVS = ["📊 視覺化分析", "➕ 新增交易", "📝 交易紀錄 & 績效", "⚙️ 資金設定"]

    # ✅ 兩段式導頁：在 radio 建立前套用 pending_nav
    if "nav_choice" not in st.session_state:
        st.session_state["nav_choice"] = NAVS[0]
    if "pending_nav" in st.session_state:
        target = st.session_state.pop("pending_nav")
        if target in NAVS:
            st.session_state["nav_choice"] = target

    nav = st.radio(
        label="",
        options=NAVS,
        horizontal=True,
        key="nav_choice",
        label_visibility="collapsed"
    )
    st.divider()

    force_reload = bool(st.session_state.pop("force_reload", False))

    df_h, df_s, df_his, df_l = load_all_data(force_reload=force_reload)
    settings = parse_settings(df_s)

    symbols = df_h["Yahoo代號(Symbol)"].tolist() if not df_h.empty else []
    prices, rate = fetch_market_data(symbols)

    stock_mv = 0
    if not df_h.empty:
        def calc_mv(row):
            p = prices.get(row["Yahoo代號(Symbol)"], 0)
            try:
                s = float(str(row["持有股數"]).replace(",", ""))
            except:
                s = 0.0
            mv = p * s * (rate if row["幣別"] == "USD" else 1)
            return mv, p

        res = df_h.apply(calc_mv, axis=1, result_type="expand")
        df_h["市值(TWD)"] = res[0]
        df_h["即時市價"] = res[1]
        stock_mv = df_h["市值(TWD)"].sum()

    net_worth = (settings["cash_twd"] + settings["settle_twd"] + (settings["cash_usd"] * rate) + stock_mv) - settings["loan"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("資產總淨值", f"${net_worth:,.0f}")
    m2.metric("證券總市值", f"${stock_mv:,.0f}")
    m3.metric("貸款餘額", f"${settings['loan']:,.0f}", delta_color="inverse")
    m4.metric("美元匯率", f"{rate:.2f}")

    # ======================================================
    # 📊 視覺化分析
    # ======================================================
    if nav == "📊 視覺化分析":
        if not df_his.empty:
            fig = px.line(df_his, x=df_his.columns[0], y=df_his.columns[1], title="資產淨值走勢", markers=True)
            fig.update_xaxes(tickformat="%Y/%m/%d")
            st.plotly_chart(fig, use_container_width=True)

        if not df_h.empty:
            st.plotly_chart(
                px.treemap(df_h, path=["投資地區", "Yahoo代號(Symbol)"], values="市值(TWD)", title="持股分佈"),
                use_container_width=True
            )
            c_p1, c_p2 = st.columns(2)
            with c_p1:
                if "投資地區" in df_h.columns:
                    st.plotly_chart(
                        px.pie(df_h, values="市值(TWD)", names="投資地區", title="投資地區佔比", hole=0.4),
                        use_container_width=True
                    )
            with c_p2:
                if "合併鍵(GroupKey)" in df_h.columns:
                    st.plotly_chart(
                        px.pie(df_h, values="市值(TWD)", names="合併鍵(GroupKey)", title="資產類別佔比", hole=0.4),
                        use_container_width=True
                    )

    # ======================================================
    # ➕ 新增交易
    # ======================================================
    elif nav == "➕ 新增交易":
        st.subheader("➕ 新增交易紀錄")

        # ✅ 顯示上一筆送出成功訊息（rerun 後仍在本頁）
        if st.session_state.get("last_trade_msg"):
            st.success(st.session_state["last_trade_msg"])
            st.session_state["last_trade_msg"] = ""

        with st.form("trade_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            d_date = c1.date_input("日期", datetime.now())
            d_type = c2.selectbox("交易類型", ["買入", "賣出"])

            if symbols:
                d_sym = st.selectbox("股票代號", symbols)
            else:
                d_sym = st.text_input("股票代號（目前 holdings 空）", value="")

            st.markdown("---")
            c3, c4 = st.columns(2)
            d_price = c3.number_input("成交價格 (原幣)", min_value=0.0, format="%.3f")
            d_shares = c4.number_input("成交股數", min_value=0.0, step=0.001, format="%.3f")

            st.markdown("### 🔴 精準對帳區 (買入請留0)")
            k1, k2 = st.columns(2)
            d_manual_principal = k1.number_input(
                "實際成交總金額/價金 (選填/0=系統自算)",
                min_value=0.0, value=0.0, format="%.3f",
                help="輸入0則自動使用 [價格x股數] 計算"
            )
            d_manual_cost = k2.number_input(
                "賣出持有成本 (僅賣出填寫/0=系統自算)",
                min_value=0.0, value=0.0, format="%.3f",
                help="輸入0則自動使用庫存均價計算"
            )
            st.markdown("---")

            c5, c6 = st.columns(2)
            d_fee = c5.number_input("手續費", min_value=0.0, format="%.3f")
            d_tax = c6.number_input("交易稅", min_value=0.0, format="%.3f")

            submitted = st.form_submit_button("送出交易")
            if submitted:
                if (not d_sym) or (symbols and d_sym not in symbols):
                    st.error("找不到該股票代號資料（請確認 holdings 內存在該代號）")
                elif d_shares <= 0 or d_price <= 0:
                    st.error("成交價格與股數必須大於 0")
                else:
                    row = df_h[df_h["Yahoo代號(Symbol)"] == d_sym].iloc[0]
                    trade_data = {
                        "date": d_date.strftime("%Y/%m/%d"),
                        "type": d_type,
                        "symbol": d_sym,
                        "name": row["標的名稱"],
                        "platform": row["平台"],
                        "account": row["帳戶類型"],
                        "currency": row["幣別"],
                        "price": d_price,
                        "shares": d_shares,
                        "fee": d_fee,
                        "tax": d_tax,
                        "manual_cost": d_manual_cost,
                        "manual_principal": d_manual_principal
                    }
                    process_trade(trade_data, df_h, df_l)

    # ======================================================
    # 📝 交易紀錄 & 績效
    # ======================================================
    elif nav == "📝 交易紀錄 & 績效":
        if not df_l.empty:
            df_l["損益(原幣)"] = pd.to_numeric(df_l["損益(原幣)"], errors="coerce").fillna(0)
            df_l["成本(原幣)※賣出需填"] = pd.to_numeric(df_l["成本(原幣)※賣出需填"], errors="coerce").fillna(0)

            total_pl = df_l["損益(原幣)"].sum()
            total_cost = df_l["成本(原幣)※賣出需填"].sum()
            total_roi = (total_pl / total_cost) * 100 if total_cost > 0 else 0

            k1, k2 = st.columns(2)
            k1.metric("🏆 累積已實現損益", f"${total_pl:,.0f}", delta_color="normal")
            k2.metric("📈 總報酬率", f"{total_roi:.2f}%", delta_color="normal")
            st.divider()

            df_display = df_l.copy()

            cols_money = ["賣出價格", "成本(原幣)※賣出需填", "價金(原幣)", "應收付(原幣)", "損益(原幣)"]
            for col in cols_money:
                if col in df_display.columns:
                    df_display[col] = df_display.apply(lambda x: format_amount(x[col], x.get("幣別", "USD")), axis=1)

            cols_shares = ["賣出股數", "買入股數"]
            for col in cols_shares:
                if col in df_display.columns:
                    df_display[col] = df_display.apply(lambda x: format_shares(x[col]), axis=1)

            if "報酬率" in df_display.columns:
                df_display["報酬率"] = df_display["報酬率"].apply(format_roi_pct)

            def color_roi(val):
                if isinstance(val, str) and "%" in val:
                    try:
                        v = float(val.strip("%"))
                        if v > 0:
                            return "color: red"
                        elif v < 0:
                            return "color: green"
                    except:
                        pass
                return ""

            show_cols = ["日期", "交易類型", "股票代號", "幣別", "賣出價格", "賣出股數",
                        "成本(原幣)※賣出需填", "價金(原幣)", "應收付(原幣)", "損益(原幣)", "報酬率"]
            final_cols = [c for c in show_cols if c in df_display.columns]
            st.dataframe(df_display[final_cols].style.applymap(color_roi, subset=["報酬率"]), use_container_width=True)
        else:
            st.info("尚無交易資料")

    # ======================================================
    # ⚙️ 資金設定
    # ======================================================
    elif nav == "⚙️ 資金設定":
        c1, c2 = st.columns(2)
        n_twd = c1.number_input("TWD 現金", value=settings["cash_twd"], step=1000.0, format="%.0f")
        n_settle = c1.number_input("交割中", value=settings["settle_twd"], step=1000.0, format="%.0f")
        n_usd = c2.number_input("USD 現金", value=settings["cash_usd"], step=100.0, format="%.3f")
        n_loan = c2.number_input("貸款", value=settings["loan"], step=10000.0, format="%.0f")

        if st.button("💾 儲存"):
            data = [
                ["目前帳戶現金(TWD)", n_twd],
                [None, None],
                ["交割中現金(TWD)", n_settle],
                ["美元現金(USD)", n_usd],
                [None, None],
                ["目前貸款金額(TWD)", n_loan],
                [None, None],
                ["資產總淨值", "App計算"],
            ]
            conn.update(worksheet=SHEET_SETTINGS, data=pd.DataFrame(data))

            # ✅ 不改 nav_choice（radio key），改 pending_nav
            st.session_state["pending_nav"] = "⚙️ 資金設定"
            st.session_state["force_reload"] = True
            st.rerun()

if __name__ == "__main__":
    main()
