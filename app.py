import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import re

# ==========================================================
# 1. 系統設定 & 登入驗證
# ==========================================================
st.set_page_config(page_title="Zhang's Smart Cloud Dashboard V24.1", page_icon="💰", layout="wide")

def check_login():
    if st.session_state.get("logged_in", False):
        return True
    st.markdown("## 🔐 戰情室登入系統 (V24.1)")
    with st.form("login_form"):
        u = st.text_input("帳號")
        p = st.text_input("密碼", type="password")
        if st.form_submit_button("登入"):
            if "credentials" in st.secrets:
                if u == st.secrets["credentials"]["username"] and p == st.secrets["credentials"]["password"]:
                    st.session_state["logged_in"] = True
                    st.success("登入成功！")
                    st.rerun()
            st.error("❌ 帳號/密碼錯誤")
    return False

if not check_login():
    st.stop()

# ==========================================================
# 2. 自動分類與初始資料
# ==========================================================
SYMBOL_MAP = {
    "0050.TW": {"組合": "0050/006208 (大盤)", "地區": "台股", "類別": "股票"},
    "006208.TW": {"組合": "0050/006208 (大盤)", "地區": "台股", "類別": "股票"},
    "2330.TW": {"組合": "2330 (台積電)", "地區": "台股", "類別": "股票"},
    "00679B.TWO": {"組合": "台股債券 (美債+投等)", "地區": "台股", "類別": "債券"},
    "00719B.TWO": {"組合": "台股債券 (美債+投等)", "地區": "台股", "類別": "債券"},
    "00720B.TWO": {"組合": "台股債券 (美債+投等)", "地區": "台股", "類別": "債券"},
    "VT": {"組合": "VT/VWRA (全球股票)", "地區": "全球", "類別": "股票"},
    "VWRA.L": {"組合": "VT/VWRA (全球股票)", "地區": "全球", "類別": "股票"},
    "TSLA": {"組合": "TSLA (特斯拉)", "地區": "美股", "類別": "股票"},
    "GOOGL": {"組合": "Google (Alphabet)", "地區": "美股", "類別": "股票"},
    "GOOG": {"組合": "Google (Alphabet)", "地區": "美股", "類別": "股票"},
    "VTI": {"組合": "VTI (美國大盤)", "地區": "美股", "類別": "股票"},
    "SGOV": {"組合": "SGOV (美國短債)", "地區": "美股", "類別": "債券"},
    "IBKR": {"組合": "IBKR (盈透證券)", "地區": "美股", "類別": "股票"},
    "BTC-USD": {"組合": "Bitcoin (比特幣)", "地區": "加密", "類別": "虛擬幣"},
}

def get_mapping(sym):
    return SYMBOL_MAP.get(sym, {"組合": "其他", "地區": "未知", "類別": "股票"})

def normalize_symbol(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.upper()

    if any(s.endswith(x) for x in [".TW", ".TWO", ".L"]) or s.endswith("-USD"):
        return s

    if s.isdigit():
        return f"{s}.TW"

    if re.fullmatch(r"[0-9]{4,6}[A-Z]?", s):
        if s + ".TW" in SYMBOL_MAP:
            return s + ".TW"
        if s + ".TWO" in SYMBOL_MAP:
            return s + ".TWO"
        return s + ".TW"

    return s

def infer_currency(sym: str) -> str:
    if sym.endswith(".TW") or sym.endswith(".TWO"):
        return "TWD"
    return "USD"

def extract_tag_from_name(name: str) -> str:
    if not name:
        return ""
    m = re.search(r"\(([^()]+)\)", name)
    if m:
        return m.group(1).strip()
    m = re.search(r"（([^（）]+)）", name)
    if m:
        return m.group(1).strip()
    return ""

def build_quick_choices_from_logs(df_l: pd.DataFrame):
    if df_l is None or df_l.empty or "股票代號" not in df_l.columns:
        return []

    seen = set()
    items = []

    for _, r in df_l.iterrows():
        sym = normalize_symbol(str(r.get("股票代號", "")).strip())
        if not sym or sym.lower() == "nan":
            continue

        name = str(r.get("名稱", "")).strip()
        platform = str(r.get("平台", "")).strip()
        account = str(r.get("帳戶類型", "")).strip()
        currency = str(r.get("幣別", "")).strip().upper() or infer_currency(sym)

        tag = extract_tag_from_name(name)
        label = f"{sym} ({tag})" if tag else sym

        key = (label, sym, platform, account, currency, name)
        if key in seen:
            continue
        seen.add(key)
        items.append((label, sym, platform, account, currency, name))

    return sorted(items, key=lambda x: x[0])

# 19 欄位標準格式（以你提供的初始值為準）
INITIAL_DATA = [
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "元大台灣50", "0050.TW", "", "", "", 30000, 0, 0, 1568276, 1568276, 1568276, "", "", ""],
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "富邦台50", "006208.TW", "", "", "", 1435, 0, 0, 187473, 187473, 187473, "", "", ""],
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "台積電", "2330.TW", "", "", "", 199, 0, 0, 301915, 301915, 301915, "", "", ""],
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "元大美債20年", "00679B.TWO", "", "", "", 11236, 0, 0, 300412, 300412, 300412, "", "", ""],
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "元大美債1-3", "00719B.TWO", "", "", "", 14371, 0, 0, 427779, 427779, 427779, "", "", ""],
    ["2026/01/01", "初始匯入", "元大(台股)", "TWD帳戶", "TWD", "投資級公司債", "00720B.TWO", "", "", "", 8875, 0, 0, 299979, 299979, 299979, "", "", ""],
    ["2026/01/01", "初始匯入", "元大複委託(美股)", "USD外幣帳戶", "USD", "Vanguard全球", "VT", "", "", "", 139, 0, 0, 18551.05, 18551.05, 18551.05, "", "", ""],
    ["2026/01/01", "初始匯入", "元大複委託(美股)", "USD外幣帳戶", "USD", "特斯拉(元大)", "TSLA", "", "", "", 10, 0, 0, 4244.50, 4244.50, 4244.50, "", "", ""],
    ["2026/01/01", "初始匯入", "元大複委託(美股)", "USD外幣帳戶", "USD", "Alphabet(元大)", "GOOGL", "", "", "", 34, 0, 0, 8040.35, 8040.35, 8040.35, "", "", ""],
    ["2026/01/01", "初始匯入", "元大複委託(美股)", "USD外幣帳戶", "USD", "特斯拉(外幣)", "TSLA", "", "", "", 3, 0, 0, 889.14, 889.14, 889.14, "", "", ""],
    ["2026/01/01", "初始匯入", "元大複委託(美股)", "USD外幣帳戶", "USD", "Alphabet(外幣)", "GOOGL", "", "", "", 2, 0, 0, 580.25, 580.25, 580.25, "", "", ""],
    ["2026/01/01", "初始匯入", "IBKR", "USD外幣帳戶", "USD", "VWRA全球", "VWRA.L", "", "", "", 249.17, 0, 0, 42564.20, 42564.20, 42564.20, "", "", ""],
    ["2026/01/01", "初始匯入", "IBKR", "USD外幣帳戶", "USD", "盈透證券", "IBKR", "", "", "", 3.84, 0, 0, 247.00, 247.00, 247.00, "", "", ""],
    ["2026/01/01", "初始匯入", "Firstrade(FT)", "USD外幣帳戶", "USD", "特斯拉(FT)", "TSLA", "", "", "", 6.52253, 0, 0, 2899.99, 2899.99, 2899.99, "", "", ""],
    ["2026/01/01", "初始匯入", "Firstrade(FT)", "USD外幣帳戶", "USD", "Alphabet(FT)", "GOOG", "", "", "", 4.5746, 0, 0, 1438.00, 1438.00, 1438.00, "", "", ""],
    ["2026/01/01", "初始匯入", "Firstrade(FT)", "USD外幣帳戶", "USD", "美國大盤(FT)", "VTI", "", "", "", 3.65, 0, 0, 1224.00, 1224.00, 1224.00, "", "", ""],
    ["2026/01/01", "初始匯入", "錢包", "USD外幣帳戶", "USD", "比特幣", "BTC-USD", "", "", "", 0.0764, 0, 0, 1763.68, 1763.68, 1763.68, "", "", ""],
]

conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================================
# 3. 核心運算引擎 (銀行存摺模式)
# ==========================================================
def rebuild_data():
    df_l = conn.read(worksheet="trade_logs", ttl=0)
    if df_l.empty:
        init_df = pd.DataFrame(INITIAL_DATA, columns=conn.read(worksheet="trade_logs", header=0).columns)
        init_df["建立時間"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.update(worksheet="trade_logs", data=init_df)
        df_l = init_df
        st.toast("✅ 已執行初始匯入！")

    df_s = conn.read(worksheet="settings", ttl=0, header=None)

    inventory = {}

    def clean(x):
        try:
            return float(str(x).replace(",", ""))
        except:
            return 0.0

    for _, row in df_l.iterrows():
        sym = str(row.get("股票代號", "")).strip()
        if not sym or sym.lower() == "nan":
            continue
        sym = normalize_symbol(sym)

        if sym not in inventory:
            inventory[sym] = {
                "shares": 0.0,
                "cost": 0.0,
                "currency": str(row.get("幣別", "")).strip().upper() or infer_currency(sym),
                "name": (str(row.get("名稱", "")).strip() or sym)
            }

        q_b = clean(row.get("買入股數", 0))
        q_s = clean(row.get("賣出股數", 0))

        row_cost_field = clean(row.get("成本(原幣)※賣出需填", 0))
        buy_price = clean(row.get("買入價格", 0))

        if q_b > 0:
            buy_cost = row_cost_field if row_cost_field > 0 else (buy_price * q_b)
            inventory[sym]["shares"] += q_b
            inventory[sym]["cost"] += buy_cost

        if q_s > 0:
            avg = inventory[sym]["cost"] / inventory[sym]["shares"] if inventory[sym]["shares"] > 0 else 0.0
            sell_cost = row_cost_field if row_cost_field > 0 else (avg * q_s)
            inventory[sym]["shares"] = max(0.0, inventory[sym]["shares"] - q_s)
            inventory[sym]["cost"] = max(0.0, inventory[sym]["cost"] - sell_cost)

    symbols = list(inventory.keys())
    prices, rate = {}, 31.5
    if symbols:
        try:
            t = yf.Tickers(" ".join(symbols + ["TWD=X"]))
            hist_r = t.tickers["TWD=X"].history(period="1d")
            if not hist_r.empty:
                rate = hist_r["Close"].iloc[-1]
            for s in symbols:
                h = t.tickers[s].history(period="1d")
                prices[s] = h["Close"].iloc[-1] if not h.empty else 0
        except:
            pass

    holdings_rows = []
    total_stock_twd = 0.0
    for s, d in inventory.items():
        if d["shares"] <= 0.001:
            continue
        now_p = prices.get(s, 0.0)
        m = get_mapping(s)
        mv_org = d["shares"] * now_p
        mv_twd = mv_org * (rate if d["currency"] == "USD" else 1.0)
        total_stock_twd += mv_twd

        holdings_rows.append({
            "投資組合": m["組合"],
            "代號": s,
            "名稱": d["name"],
            "資產類別": m["類別"],
            "投資地區": m["地區"],
            "幣別": d["currency"],
            "持有股數": d["shares"],
            "平均成本(原幣)": d["cost"] / d["shares"] if d["shares"] > 0 else 0.0,
            "目前市價(原幣)": now_p,
            "總成本(原幣)": d["cost"],
            "總市值(原幣)": mv_org,
            "未實現損益(原幣)": mv_org - d["cost"],
            "報酬率": (mv_org - d["cost"]) / d["cost"] if d["cost"] > 0 else 0.0,
            "匯率": rate if d["currency"] == "USD" else 1.0,
            "總市值(TWD)": mv_twd,
            "未實現損益(TWD)": (mv_org - d["cost"]) * (rate if d["currency"] == "USD" else 1.0),
        })

    df_h = pd.DataFrame(holdings_rows)
    if not df_h.empty:
        conn.update(worksheet="holdings", data=df_h)

    s_dict = {}
    for _, r in df_s.iterrows():
        try:
            s_dict[str(r[0]).strip()] = float(str(r[1]).replace(",", ""))
        except:
            pass

    nw = (
        s_dict.get("目前帳戶現金(TWD)", 0.0)
        + s_dict.get("交割中現金(TWD)", 0.0)
        + (s_dict.get("美元現金(USD)", 0.0) * rate)
        + total_stock_twd
    ) - s_dict.get("目前貸款金額(TWD)", 0.0)

    return df_h, df_l, s_dict, nw, rate, symbols

# ==========================================================
# 4. 主程式介面
# ==========================================================
with st.sidebar:
    st.info("👤 User: admin")
    st.divider()
    if st.button("🚀 更新市價"):
        st.cache_data.clear()
        st.success("市價同步中...")
        st.rerun()
    if st.button("📈 紀錄淨資產"):
        st.session_state["trigger_record"] = True
        st.rerun()
    st.divider()
    if st.button("🔒 登出"):
        st.session_state["logged_in"] = False
        st.rerun()

df_h, df_l, settings, net_worth, rate, all_symbols = rebuild_data()

if st.session_state.get("flash_msg"):
    st.success(st.session_state["flash_msg"])
    st.session_state["flash_msg"] = ""

if st.session_state.get("trigger_record"):
    df_hist = conn.read(worksheet="net_worth_history", ttl=0)
    nr = pd.DataFrame([[datetime.now().strftime("%Y/%m/%d %H:%M"), net_worth]],
                      columns=["時間", "資產總淨值(TWD)"])
    df_hist = pd.concat([df_hist, nr], ignore_index=True)
    conn.update(worksheet="net_worth_history", data=df_hist)
    st.success(f"✅ 已紀錄: ${net_worth:,.0f}")
    del st.session_state["trigger_record"]

m1, m2, m3 = st.columns(3)
m1.metric("資產總淨值", f"${net_worth:,.0f}")
stock_val = df_h["總市值(TWD)"].sum() if not df_h.empty else 0
m2.metric("證券總市值", f"${stock_val:,.0f}")
m3.metric("美金匯率", f"{rate:.2f}")

st.divider()

NAVS = ["📊 視覺化分析", "➕ 新增交易", "📝 交易紀錄 & 績效", "⚙️ 資金設定"]
if "nav_choice" not in st.session_state:
    st.session_state["nav_choice"] = NAVS[0]
if "pending_nav" in st.session_state:
    st.session_state["nav_choice"] = st.session_state.pop("pending_nav")

nav = st.radio("", NAVS, horizontal=True, key="nav_choice")

if nav == "📊 視覺化分析":
    try:
        df_hist = conn.read(worksheet="net_worth_history", ttl=0)
        if not df_hist.empty:
            st.plotly_chart(px.line(df_hist, x="時間", y="資產總淨值(TWD)",
                                    title="淨值走勢", markers=True),
                            use_container_width=True)
    except:
        st.info("尚無歷史紀錄")

    if not df_h.empty:
        st.plotly_chart(px.treemap(df_h, path=["投資地區", "代號"], values="總市值(TWD)",
                                   title="持股分佈樹狀圖"),
                        use_container_width=True)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.pie(df_h, values="總市值(TWD)", names="投資地區",
                                   title="地區佔比", hole=0.4),
                            use_container_width=True)
        with c2:
            st.plotly_chart(px.pie(df_h, values="總市值(TWD)", names="投資組合",
                                   title="組合佔比", hole=0.4),
                            use_container_width=True)

elif nav == "➕ 新增交易":
    st.subheader("➕ 新增交易（賣出：必填成本；應收付可手填；送出即自動算損益/報酬率）")

    def parse_num(s: str, field_name: str, allow_zero: bool = False) -> float:
        s = (s or "").strip()
        if s == "":
            return float("nan")
        try:
            v = float(s.replace(",", ""))
        except:
            raise ValueError(f"{field_name} 格式錯誤")
        if (not allow_zero) and (v <= 0):
            raise ValueError(f"{field_name} 必須大於 0")
        if allow_zero and (v < 0):
            raise ValueError(f"{field_name} 不可為負數")
        return v

    REQUIRED_COLS = [
        "日期","交易類型","平台","帳戶類型","幣別","名稱","股票代號",
        "買入價格","買入股數","賣出價格","賣出股數",
        "手續費","交易稅","價金(原幣)",
        "成本(原幣)※賣出需填",
        "應收付(原幣)","損益(原幣)","報酬率",
        "建立時間"
    ]
    for c in REQUIRED_COLS:
        if c not in df_l.columns:
            df_l[c] = ""

    with st.form("add_trade", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d_date = c1.date_input("日期", datetime.now())
        d_type = c2.selectbox("類型", ["買入", "賣出"])

        quick_items = [("（不選）", "", "", "", "", "")] + build_quick_choices_from_logs(df_l)
        c3, c4 = st.columns(2)
        quick_pick = c3.selectbox("快速選擇（可不選）", options=quick_items, format_func=lambda x: x[0])
        d_sym_raw = c4.text_input("代號（如 TSLA, 2330, 2330.TW）", value="")

        d_sym_raw = d_sym_raw.strip() if d_sym_raw else ""
        d_sym = normalize_symbol(d_sym_raw) if d_sym_raw else quick_pick[1]

        auto_platform = quick_pick[2]
        auto_account = quick_pick[3]
        auto_currency = quick_pick[4] or (infer_currency(d_sym) if d_sym else "")
        auto_name = quick_pick[5]

        d_name = st.text_input("名稱（選填）", value="")

        if d_sym:
            st.caption(f"系統代號：{d_sym}（賣出/抓價用此代號）｜平台：{auto_platform or '—'}｜帳戶：{auto_account or '—'}")

        c5, c6 = st.columns(2)
        s_price = c5.text_input("價格 (原幣)", value="", placeholder="例如 1700 或 1700.5")
        s_shares = c6.text_input("股數", value="", placeholder="例如 100 或 6.52253")

        c7, c8 = st.columns(2)
        s_fee = c7.text_input("手續費", value="", placeholder="可空白=0")
        s_tax = c8.text_input("交易稅", value="", placeholder="可空白=0")

        s_sell_cost = st.text_input(
            "成本(原幣)※賣出需填（買入可留空）",
            value="",
            placeholder="賣出必填，用於計算損益/報酬率"
        )

        s_net = st.text_input(
            "應收付(原幣)（可手填；留空=系統自算）",
            value="",
            placeholder="留空：買入=價金+手續費；賣出=價金-手續費-交易稅"
        )

        submitted = st.form_submit_button("送出交易")
        if submitted:
            try:
                if not d_sym:
                    st.error("請輸入代號")
                    st.stop()

                d_price = parse_num(s_price, "價格", allow_zero=False)
                d_shares = parse_num(s_shares, "股數", allow_zero=False)

                d_fee = 0.0 if (s_fee or "").strip() == "" else parse_num(s_fee, "手續費", allow_zero=True)
                d_tax = 0.0 if (s_tax or "").strip() == "" else parse_num(s_tax, "交易稅", allow_zero=True)

                currency = auto_currency if auto_currency else infer_currency(d_sym)
                name_final = d_name.strip() if d_name.strip() else (auto_name if auto_name else d_sym)

                gross = float(d_price) * float(d_shares)

                # 應收付：可手填；留空=系統自算
                if (s_net or "").strip() != "":
                    net_receivable = parse_num(s_net, "應收付(原幣)", allow_zero=True)
                else:
                    net_receivable = (gross + float(d_fee)) if d_type == "買入" else (gross - float(d_fee) - float(d_tax))

                # 賣出：成本必填，且 ROI 存「百分比數值」（例如 61.3483 代表 61.3483%）
                sell_cost_to_write = ""
                profit = ""
                roi_pct = ""
                if d_type == "賣出":
                    if (s_sell_cost or "").strip() == "":
                        st.error("賣出時必須填『成本(原幣)※賣出需填』，否則無法計算損益/報酬率。")
                        st.stop()
                    sell_cost_to_write = parse_num(s_sell_cost, "成本(原幣)", allow_zero=False)

                    profit = float(net_receivable) - float(sell_cost_to_write)
                    roi_pct = (profit / float(sell_cost_to_write) * 100.0) if float(sell_cost_to_write) > 0 else 0.0

                row_data = {col: "" for col in df_l.columns}
                row_data.update({
                    "日期": d_date.strftime("%Y/%m/%d"),
                    "交易類型": d_type,
                    "平台": auto_platform,
                    "帳戶類型": auto_account,
                    "股票代號": d_sym,
                    "名稱": name_final,
                    "幣別": currency,

                    "買入價格": float(d_price) if d_type == "買入" else "",
                    "買入股數": float(d_shares) if d_type == "買入" else "",
                    "賣出價格": float(d_price) if d_type == "賣出" else "",
                    "賣出股數": float(d_shares) if d_type == "賣出" else "",

                    "手續費": float(d_fee),
                    "交易稅": float(d_tax),
                    "價金(原幣)": float(gross),

                    "成本(原幣)※賣出需填": float(sell_cost_to_write) if d_type == "賣出" else "",
                    "應收付(原幣)": float(net_receivable),

                    "損益(原幣)": float(profit) if d_type == "賣出" else "",
                    "報酬率": float(roi_pct) if d_type == "賣出" else "",

                    "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                df_new = pd.DataFrame([row_data], columns=df_l.columns)
                df_l2 = pd.concat([df_l, df_new], ignore_index=True)
                conn.update(worksheet="trade_logs", data=df_l2)

                rebuild_data()

                extra = f"｜應收付:{net_receivable:,.4f}"
                if d_type == "賣出":
                    extra += f"｜損益:{profit:,.4f}｜報酬率:{roi_pct:.2f}%"

                st.session_state["pending_nav"] = "➕ 新增交易"
                st.session_state["flash_msg"] = f"✅ 已寫入交易：{d_type} {d_sym} {float(d_shares)} 股 @ {float(d_price)}{extra}"
                st.cache_data.clear()
                st.rerun()

            except ValueError as e:
                st.error(str(e))

elif nav == "📝 交易紀錄 & 績效":
    st.dataframe(df_l, use_container_width=True)

elif nav == "⚙️ 資金設定":
    c1, c2 = st.columns(2)
    v_twd = c1.number_input("TWD 現金", value=settings.get("目前帳戶現金(TWD)", 0))
    v_set = c1.number_input("交割中現金", value=settings.get("交割中現金(TWD)", 0))
    v_usd = c2.number_input("USD 現金", value=settings.get("美元現金(USD)", 0))
    v_loan = c2.number_input("貸款金額", value=settings.get("目前貸款金額(TWD)", 0))

    if st.button("💾 儲存設定"):
        new_s = pd.DataFrame([
            ["目前帳戶現金(TWD)", v_twd],
            ["交割中現金(TWD)", v_set],
            ["美元現金(USD)", v_usd],
            ["目前貸款金額(TWD)", v_loan]
        ])
        conn.update(worksheet="settings", data=new_s)
        st.session_state["pending_nav"] = "⚙️ 資金設定"
        st.session_state["flash_msg"] = "✅ 設定已更新！"
        st.cache_data.clear()
        st.rerun()
