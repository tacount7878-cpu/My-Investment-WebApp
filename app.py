import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# ==========================================================
# 1. 基礎設定 & 登入邏輯 (讀取 secrets.toml)
# ==========================================================
st.set_page_config(page_title="Zhang's Smart Cloud Dashboard", page_icon="💰", layout="wide")

def check_login():
    if st.session_state.get("logged_in", False):
        return True

    st.markdown("## 🔐 戰情室登入系統")
    with st.form("login_form"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submit = st.form_submit_button("登入")
        if submit:
            try:
                correct_user = st.secrets["credentials"]["username"]
                correct_pass = st.secrets["credentials"]["password"]
                if username == correct_user and password == correct_pass:
                    st.session_state["logged_in"] = True
                    st.success("登入成功！")
                    st.rerun()
                else:
                    st.error("❌ 帳號或密碼錯誤")
            except:
                st.error("⚠️ 尚未設定 secrets.toml，請檢查設定檔！")
    return False

if not check_login():
    st.stop()

# ==========================================================
# 2. 主程式開始 (登入後可見)
# ==========================================================
with st.sidebar:
    st.info(f"👤 User: {st.secrets['credentials']['username']}")
    st.divider()
    if st.button("🚀 手動更新數據"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if st.button("🔒 登出"):
        st.session_state["logged_in"] = False
        st.rerun()

conn = st.connection("gsheets", type=GSheetsConnection)
SHEET_HOLDINGS, SHEET_LOGS = "holdings", "trade_logs"
SHEET_SETTINGS, SHEET_HISTORY = "settings", "net_worth_history"

def load_all_data(force_reload=False):
    ttl_val = 0 if force_reload else 10
    return conn.read(worksheet=SHEET_HOLDINGS, ttl=ttl_val), conn.read(worksheet=SHEET_SETTINGS, ttl=ttl_val, header=None), \
           conn.read(worksheet=SHEET_HISTORY, ttl=ttl_val), conn.read(worksheet=SHEET_LOGS, ttl=ttl_val)

def parse_settings(df):
    s = {"loan": 1529264.0, "cash_usd": 3148.49, "cash_twd": 0.0, "settle_twd": 0.0}
    if df.empty: return s
    m = {"目前帳戶現金(TWD)": "cash_twd", "交割中現金(TWD)": "settle_twd", "美元現金(USD)": "cash_usd", "目前貸款金額(TWD)": "loan"}
    for _, r in df.iterrows():
        if str(r[0]).strip() in m: s[m[str(r[0]).strip()]] = float(str(r[1]).replace(',', ''))
    return s

@st.cache_data(ttl=300)
def fetch_market_data(syms):
    if not syms: return {}, 31.60
    t = yf.Tickers(" ".join(list(set(syms)) + ["TWD=X"]))
    r = t.tickers["TWD=X"].history(period="1d")['Close'].iloc[-1]
    p = {s: t.tickers[s].history(period="1d")['Close'].iloc[-1] if not t.tickers[s].history(period="1d").empty else 0.0 for s in syms}
    return p, r

def main():
    st.title("💰 翔翔的雲端投資戰情室 V21.0")
    nav = st.radio("", ["📊 視覺化分析", "➕ 新增交易", "📝 交易紀錄 & 績效", "⚙️ 資金設定"], horizontal=True, label_visibility="collapsed")
    df_h, df_s, df_his, df_l = load_all_data(st.session_state.pop("force_reload", False))
    settings = parse_settings(df_s)
    prices, rate = fetch_market_data(df_h["Yahoo代號(Symbol)"].tolist() if not df_h.empty else [])
    stock_mv = (df_h.apply(lambda r: prices.get(r["Yahoo代號(Symbol)"], 0) * float(str(r["持有股數"]).replace(',', '')) * (rate if r["幣別"] == "USD" else 1), axis=1).sum()) if not df_h.empty else 0
    net = (settings["cash_twd"] + settings["settle_twd"] + (settings["cash_usd"] * rate) + stock_mv) - settings["loan"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("資產總淨值", f"${net:,.0f}"); c2.metric("證券總市值", f"${stock_mv:,.0f}"); c3.metric("貸款餘額", f"${settings['loan']:,.0f}"); c4.metric("美元匯率", f"{rate:.2f}")

    if nav == "📊 視覺化分析":
        if not df_his.empty: st.plotly_chart(px.line(df_his, x=df_his.columns[0], y=df_his.columns[1], title="資產淨值走勢"), use_container_width=True)
    elif nav == "➕ 新增交易":
        st.subheader("➕ 新增交易紀錄")
        with st.form("t_form", clear_on_submit=True):
            if st.form_submit_button("送出交易"):
                st.session_state["force_reload"] = True; st.rerun()

if __name__ == "__main__": main()