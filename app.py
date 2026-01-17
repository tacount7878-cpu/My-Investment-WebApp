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
    st.markdown("## 🔐 翔翔系統登入")
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

# ✅ 台股債券：地區佔比與 Treemap 都要獨立顯示
TAIWAN_BOND_SYMBOLS = {"00679B.TWO", "00719B.TWO", "00720B.TWO"}

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

# ✅ trade_logs 欄位（含：市值(新台幣)）
TRADELOG_COLS = [
    "日期","交易類型","平台","帳戶類型","幣別","名稱","股票代號",
    "買入價格","買入股數","賣出價格","賣出股數",
    "手續費","交易稅","價金(原幣)",
    "成本(原幣)※賣出需填",
    "應收付(原幣)","損益(原幣)","市值(新台幣)","報酬率",
    "建立時間"
]

# ✅ 初始值（用 dict 方式，避免欄位變動造成長度不符）
INITIAL_DATA = [
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"元大台灣50","股票代號":"0050.TW","買入價格":"","買入股數":30000,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":1568276,"成本(原幣)※賣出需填":"","應收付(原幣)":1568276,"損益(原幣)":"","市值(新台幣)":1568276,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"富邦台50","股票代號":"006208.TW","買入價格":"","買入股數":1435,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":187473,"成本(原幣)※賣出需填":"","應收付(原幣)":187473,"損益(原幣)":"","市值(新台幣)":187473,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"台積電","股票代號":"2330.TW","買入價格":"","買入股數":199,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":301915,"成本(原幣)※賣出需填":"","應收付(原幣)":301915,"損益(原幣)":"","市值(新台幣)":301915,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"元大美債20年","股票代號":"00679B.TWO","買入價格":"","買入股數":11236,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":300412,"成本(原幣)※賣出需填":"","應收付(原幣)":300412,"損益(原幣)":"","市值(新台幣)":300412,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"元大美債1-3","股票代號":"00719B.TWO","買入價格":"","買入股數":14371,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":427779,"成本(原幣)※賣出需填":"","應收付(原幣)":427779,"損益(原幣)":"","市值(新台幣)":427779,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大(台股)","帳戶類型":"TWD帳戶","幣別":"TWD","名稱":"投資級公司債","股票代號":"00720B.TWO","買入價格":"","買入股數":8875,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":299979,"成本(原幣)※賣出需填":"","應收付(原幣)":299979,"損益(原幣)":"","市值(新台幣)":299979,"報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大複委託(美股)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"Vanguard全球","股票代號":"VT","買入價格":"","買入股數":139,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":18551.05,"成本(原幣)※賣出需填":"","應收付(原幣)":18551.05,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大複委託(美股)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"特斯拉(元大)","股票代號":"TSLA","買入價格":"","買入股數":10,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":4244.50,"成本(原幣)※賣出需填":"","應收付(原幣)":4244.50,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大複委託(美股)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"Alphabet(元大)","股票代號":"GOOGL","買入價格":"","買入股數":34,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":8040.35,"成本(原幣)※賣出需填":"","應收付(原幣)":8040.35,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大複委託(美股)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"特斯拉(外幣)","股票代號":"TSLA","買入價格":"","買入股數":3,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":889.14,"成本(原幣)※賣出需填":"","應收付(原幣)":889.14,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"元大複委託(美股)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"Alphabet(外幣)","股票代號":"GOOGL","買入價格":"","買入股數":2,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":580.25,"成本(原幣)※賣出需填":"","應收付(原幣)":580.25,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"IBKR","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"VWRA全球","股票代號":"VWRA.L","買入價格":"","買入股數":249.17,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":42564.20,"成本(原幣)※賣出需填":"","應收付(原幣)":42564.20,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"IBKR","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"盈透證券","股票代號":"IBKR","買入價格":"","買入股數":3.84,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":247.00,"成本(原幣)※賣出需填":"","應收付(原幣)":247.00,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"Firstrade(FT)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"特斯拉(FT)","股票代號":"TSLA","買入價格":"","買入股數":6.52253,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":2899.99,"成本(原幣)※賣出需填":"","應收付(原幣)":2899.99,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"Firstrade(FT)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"Alphabet(FT)","股票代號":"GOOG","買入價格":"","買入股數":4.5746,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":1438.00,"成本(原幣)※賣出需填":"","應收付(原幣)":1438.00,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"Firstrade(FT)","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"美國大盤(FT)","股票代號":"VTI","買入價格":"","買入股數":3.65,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":1224.00,"成本(原幣)※賣出需填":"","應收付(原幣)":1224.00,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
    {"日期":"2026/01/01","交易類型":"初始匯入","平台":"錢包","帳戶類型":"USD外幣帳戶","幣別":"USD","名稱":"比特幣","股票代號":"BTC-USD","買入價格":"","買入股數":0.0764,"賣出價格":"","賣出股數":"","手續費":0,"交易稅":0,"價金(原幣)":1763.68,"成本(原幣)※賣出需填":"","應收付(原幣)":1763.68,"損益(原幣)":"","市值(新台幣)":"","報酬率":"","建立時間":""},
]

conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================================
# 3. 核心運算引擎 (銀行存摺模式)
# ==========================================================
def rebuild_data():
    df_l = conn.read(worksheet="trade_logs", ttl=0)

    # ✅ 先取匯率（初始化 trade_logs 時也可用）
    rate_init = 31.5
    try:
        tfx = yf.Tickers("TWD=X")
        hist_r = tfx.tickers["TWD=X"].history(period="1d")
        if not hist_r.empty:
            rate_init = float(hist_r["Close"].iloc[-1])
    except:
        pass

    # ✅ 若 trade_logs 空的：寫入初始匯入
    if df_l.empty:
        # 用 Sheet 現有欄位（若沒有就用 TRADELOG_COLS）
        template = conn.read(worksheet="trade_logs", header=0, ttl=0)
        cols = list(template.columns) if (template is not None and len(template.columns) > 0) else TRADELOG_COLS

        init_df = pd.DataFrame([{c: "" for c in cols} for _ in range(len(INITIAL_DATA))])

        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for i, row in enumerate(INITIAL_DATA):
            for k, v in row.items():
                if k in init_df.columns:
                    init_df.at[i, k] = v
            if "建立時間" in init_df.columns:
                init_df.at[i, "建立時間"] = now_ts

            # ✅ 補「市值(新台幣)」：TWD 直接填；USD 用匯率換算（初始化時用 rate_init）
            if "市值(新台幣)" in init_df.columns:
                cur = str(init_df.at[i, "幣別"]).strip().upper() if "幣別" in init_df.columns else ""
                net_org = init_df.at[i, "應收付(原幣)"] if "應收付(原幣)" in init_df.columns else ""
                try:
                    net_org_f = float(str(net_org).replace(",", "")) if str(net_org).strip() != "" else 0.0
                except:
                    net_org_f = 0.0
                init_df.at[i, "市值(新台幣)"] = net_org_f * (rate_init if cur == "USD" else 1.0)

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

    # ✅ inventory 依「代號」聚合（現階段版本）
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
                rate = float(hist_r["Close"].iloc[-1])
            for s in symbols:
                h = t.tickers[s].history(period="1d")
                prices[s] = float(h["Close"].iloc[-1]) if not h.empty else 0.0
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
            # ✅ 報酬率：直接存百分比數值（例如 12.34 = 12.34%）
            "報酬率": ((mv_org - d["cost"]) / d["cost"] * 100.0) if d["cost"] > 0 else 0.0,
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

# ======================================================
# ✅ Top Metrics：資產 / 市值 / 匯率 + 淨現金流 / 已實現損益（基準起始值 + 快照後增量）
# 你的 Excel 最新值當 baseline，不再把舊 trade_logs 重複加總
# 增量只算：建立時間 > baseline_snapshot_ts 的新交易
# baseline_snapshot_ts 會寫入 settings，確保重啟也不會跑掉
# ======================================================

# ✅ 你最新給的 baseline（固定起點）
BASE_NET_CASHFLOW_TWD = 414_528.0
BASE_REALIZED_PNL_TWD = 218_122.0
BASE_REALIZED_ROI_PCT = 21.99  # 21.99%

# 用 baseline 損益與 ROI 反推 baseline 已實現成本（避免 % 直接相加）
BASE_REALIZED_COST_TWD = (BASE_REALIZED_PNL_TWD / (BASE_REALIZED_ROI_PCT / 100.0)) if BASE_REALIZED_ROI_PCT != 0 else 0.0

# ✅ 你 Excel 這塊通常是「只算股票已實現」；要全算就改 False
REALIZED_STOCKS_ONLY = True

def _f(x):
    try:
        s = str(x).strip()
        if s == "" or s.lower() in {"none", "nan"}:
            return 0.0
        return float(s.replace(",", ""))
    except:
        return 0.0

# ======================================================
# ✅ baseline snapshot time：寫入 settings（只寫一次）
# Key: baseline_snapshot_ts
# ======================================================
def _read_settings_dict(df_s: pd.DataFrame) -> dict:
    d = {}
    if df_s is None or df_s.empty:
        return d
    for _, r in df_s.iterrows():
        try:
            k = str(r[0]).strip()
            v = str(r[1]).strip()
            d[k] = v
        except:
            pass
    return d

def _save_setting_key(df_s: pd.DataFrame, key: str, value: str):
    # df_s 是 settings（header=None）
    if df_s is None or df_s.empty:
        new_s = pd.DataFrame([[key, value]])
    else:
        tmp = df_s.copy()
        sd = _read_settings_dict(tmp)
        sd[key] = value
        new_s = pd.DataFrame([[k, sd[k]] for k in sd.keys()])
    conn.update(worksheet="settings", data=new_s)

df_s_now = conn.read(worksheet="settings", ttl=0, header=None)
s_dict_raw = _read_settings_dict(df_s_now)

# 只在第一次設定 baseline 時寫入（之後不要動它）
if "baseline_snapshot_ts" not in s_dict_raw or str(s_dict_raw.get("baseline_snapshot_ts", "")).strip() == "":
    baseline_snapshot_ts = datetime.now()
    _save_setting_key(df_s_now, "baseline_snapshot_ts", baseline_snapshot_ts.strftime("%Y-%m-%d %H:%M:%S"))
else:
    try:
        baseline_snapshot_ts = datetime.strptime(str(s_dict_raw["baseline_snapshot_ts"]).strip(), "%Y-%m-%d %H:%M:%S")
    except:
        baseline_snapshot_ts = datetime.now()
        _save_setting_key(df_s_now, "baseline_snapshot_ts", baseline_snapshot_ts.strftime("%Y-%m-%d %H:%M:%S"))

# ======================================================
# ✅ 增量：只算「baseline_snapshot_ts 之後」的新交易
# ======================================================
net_cashflow_delta_twd = 0.0
realized_pnl_delta_twd = 0.0
realized_cost_delta_twd = 0.0

if df_l is not None and not df_l.empty:
    for _, r in df_l.iterrows():
        ttype = str(r.get("交易類型", "")).strip()
        if ttype not in ("買入", "賣出"):
            continue

        # 用建立時間切分增量（沒有建立時間就當作舊資料，不算增量）
        bt = str(r.get("建立時間", "")).strip()
        if bt == "" or bt.lower() in {"none", "nan"}:
            continue
        try:
            row_ts = datetime.strptime(bt, "%Y-%m-%d %H:%M:%S")
        except:
            continue

        if row_ts <= baseline_snapshot_ts:
            continue  # ✅ baseline 以前的不算增量

        sym = normalize_symbol(str(r.get("股票代號", "")).strip())
        cur = str(r.get("幣別", "")).strip().upper() or infer_currency(sym)
        fx = rate if cur == "USD" else 1.0

        net_org = _f(r.get("應收付(原幣)", 0))
        net_twd = net_org * fx

        # 淨現金流：買入(負)、賣出(正)
        if ttype == "買入":
            net_cashflow_delta_twd -= net_twd
        else:
            net_cashflow_delta_twd += net_twd

            # 已實現：只統計賣出
            if REALIZED_STOCKS_ONLY and get_mapping(sym).get("類別") != "股票":
                continue

            sell_cost_org = _f(r.get("成本(原幣)※賣出需填", 0))
            profit_org = _f(r.get("損益(原幣)", 0))
            if profit_org == 0.0:
                profit_org = (net_org - sell_cost_org)

            realized_pnl_delta_twd += profit_org * fx
            realized_cost_delta_twd += sell_cost_org * fx

# ======================================================
# ✅ 最終顯示：baseline + 增量
# ======================================================
net_cashflow_total_twd = BASE_NET_CASHFLOW_TWD + net_cashflow_delta_twd
realized_pnl_total_twd = BASE_REALIZED_PNL_TWD + realized_pnl_delta_twd
realized_cost_total_twd = BASE_REALIZED_COST_TWD + realized_cost_delta_twd
realized_roi_total_pct = (realized_pnl_total_twd / realized_cost_total_twd * 100.0) if realized_cost_total_twd > 0 else 0.0

# 第一排：資產 / 市值 / 匯率
m1, m2, m3 = st.columns(3)
m1.metric("資產總淨值", f"${net_worth:,.0f}")
stock_val = df_h["總市值(TWD)"].sum() if (df_h is not None and not df_h.empty) else 0
m2.metric("證券總市值", f"${stock_val:,.0f}")
m3.metric("美金匯率", f"{rate:.2f}")

# 第二排：淨現金流 / 已實現損益（基準 + 快照後增量）
m4, m5, m6 = st.columns(3)
m4.metric("淨現金流(TWD)（正=錢回收、負=支出）", f"{net_cashflow_total_twd:,.0f}")
m5.metric("已實現總損益(TWD)", f"{realized_pnl_total_twd:,.0f}")
m6.metric("已實現總損益(%)", f"{realized_roi_total_pct:.2f}%")

st.divider()

NAVS = ["📊 視覺化分析", "➕ 新增交易", "📝 交易紀錄 & 績效", "⚙️ 資金設定"]
if "nav_choice" not in st.session_state:
    st.session_state["nav_choice"] = NAVS[0]
if "pending_nav" in st.session_state:
    st.session_state["nav_choice"] = st.session_state.pop("pending_nav")

nav = st.radio("", NAVS, horizontal=True, key="nav_choice")

# ==========================================================
# 5. 各頁面
# ==========================================================
if nav == "📊 視覺化分析":
    try:
        df_hist = conn.read(worksheet="net_worth_history", ttl=0)
        if not df_hist.empty:
            df_hist2 = df_hist.copy()
            df_hist2["時間_dt"] = pd.to_datetime(df_hist2["時間"], errors="coerce")
            df_hist2 = df_hist2.dropna(subset=["時間_dt"]).sort_values("時間_dt")

            fig = px.line(df_hist2, x="時間_dt", y="資產總淨值(TWD)", title="淨值走勢", markers=True)
            fig.update_xaxes(tickformat="%Y/%m/%d")  # ✅ 只顯示年月日
            st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("尚無歷史紀錄")

    if not df_h.empty:
        # ✅ Treemap：台股債券獨立分出來（不同顏色）
        df_tree = df_h.copy()
        df_tree["樹狀圖分類"] = df_tree.apply(
            lambda r: "台股債券"
            if str(r.get("代號", "")).strip() in TAIWAN_BOND_SYMBOLS
            else str(r.get("投資地區", "")).strip(),
            axis=1
        )

        st.plotly_chart(
            px.treemap(
                df_tree,
                path=["樹狀圖分類", "代號"],
                values="總市值(TWD)",
                title="持股分佈樹狀圖"
            ),
            use_container_width=True
        )

        c1, c2 = st.columns(2)
        with c1:
            # ✅ 地區佔比：台股債券獨立出來
            df_region = df_h.copy()
            df_region["地區佔比分類"] = df_region.apply(
                lambda r: "台股債券"
                if str(r.get("代號", "")).strip() in TAIWAN_BOND_SYMBOLS
                else str(r.get("投資地區", "")).strip(),
                axis=1
            )
            st.plotly_chart(
                px.pie(df_region, values="總市值(TWD)", names="地區佔比分類", title="地區佔比", hole=0.4),
                use_container_width=True
            )

        with c2:
            st.plotly_chart(
                px.pie(df_h, values="總市值(TWD)", names="投資組合", title="組合佔比", hole=0.4),
                use_container_width=True
            )

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

    # ✅ 確保欄位存在（含：市值(新台幣)）
    for c in TRADELOG_COLS:
        if c not in df_l.columns:
            df_l[c] = ""

    with st.form("add_trade", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d_date = c1.date_input("日期", datetime.now())
        d_type = c2.selectbox("類型", ["買入", "賣出"])

        # ✅ 快速選擇：加一個「新增股票」
        quick_items = [
            ("➕ 新增股票（手動輸入代號）", "__NEW__", "", "", "", ""),
            ("（不選）", "", "", "", "", "")
        ] + build_quick_choices_from_logs(df_l)

        c3, c4 = st.columns(2)
        quick_pick = c3.selectbox("快速選擇（可不選）", options=quick_items, format_func=lambda x: x[0])
        d_sym_raw = c4.text_input("代號（如 TSLA, 2330, 2330.TW）", value="")

        d_sym_raw = d_sym_raw.strip() if d_sym_raw else ""
        if quick_pick[1] == "__NEW__":
            d_sym = normalize_symbol(d_sym_raw) if d_sym_raw else ""
            auto_platform = ""
            auto_account = ""
            auto_currency = infer_currency(d_sym) if d_sym else ""
            auto_name = ""
        else:
            d_sym = normalize_symbol(d_sym_raw) if d_sym_raw else quick_pick[1]
            auto_platform = quick_pick[2]
            auto_account = quick_pick[3]
            auto_currency = quick_pick[4] or (infer_currency(d_sym) if d_sym else "")
            auto_name = quick_pick[5]

        # ✅ 平台/帳戶/幣別：允許你手動改（新股票時就靠這三個）
        cP1, cP2, cP3 = st.columns(3)
        platform_in = cP1.text_input("平台（可留空）", value=auto_platform)
        account_in = cP2.text_input("帳戶類型（可留空）", value=auto_account)
        currency_in = cP3.selectbox("幣別", options=["TWD", "USD"], index=(0 if (auto_currency or "TWD") == "TWD" else 1))

        d_name = st.text_input("名稱（選填）", value="")

        if d_sym:
            st.caption(f"系統代號：{d_sym}（賣出/抓價用此代號）｜平台：{platform_in or '—'}｜帳戶：{account_in or '—'}｜幣別：{currency_in}")

        c5, c6 = st.columns(2)
        s_price = c5.text_input("價格 (原幣)", value="", placeholder="例如 1700 或 1700.5")
        s_shares = c6.text_input("股數", value="", placeholder="例如 100 或 6.52253（台股可整數）")

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

                currency = currency_in
                name_final = d_name.strip() if d_name.strip() else (auto_name if auto_name else d_sym)

                gross = float(d_price) * float(d_shares)

                # 應收付：可手填；留空=系統自算
                if (s_net or "").strip() != "":
                    net_receivable = parse_num(s_net, "應收付(原幣)", allow_zero=True)
                else:
                    net_receivable = (gross + float(d_fee)) if d_type == "買入" else (gross - float(d_fee) - float(d_tax))

                # ✅ 市值(新台幣)：直接把「應收付(原幣)」換算成 TWD（TWD=原值，USD=乘匯率）
                mv_twd_trade = float(net_receivable) * (rate if currency == "USD" else 1.0)

                # 賣出：成本必填，且 ROI 存「百分比數值」
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
                    "平台": platform_in,
                    "帳戶類型": account_in,
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
                    "市值(新台幣)": float(mv_twd_trade),
                    "報酬率": float(roi_pct) if d_type == "賣出" else "",

                    "建立時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                df_new = pd.DataFrame([row_data], columns=df_l.columns)
                df_l2 = pd.concat([df_l, df_new], ignore_index=True)
                conn.update(worksheet="trade_logs", data=df_l2)

                # 重算 holdings
                rebuild_data()

                extra = f"｜應收付:{net_receivable:,.4f}｜市值(TWD):{mv_twd_trade:,.0f}"
                if d_type == "賣出":
                    extra += f"｜損益:{profit:,.4f}｜報酬率:{roi_pct:.2f}%"

                st.session_state["pending_nav"] = "➕ 新增交易"
                st.session_state["flash_msg"] = f"✅ 已寫入交易：{d_type} {d_sym} {float(d_shares)} 股 @ {float(d_price)}{extra}"
                st.cache_data.clear()
                st.rerun()

            except ValueError as e:
                st.error(str(e))

elif nav == "📝 交易紀錄 & 績效":
    # ✅ 顯示格式：
    # - TWD 金額：不顯示小數
    # - 台股股數：不顯示小數
    # - 美股/美金：保留小數
    df_view = df_l.copy()

    money_cols = [
        "手續費", "交易稅", "價金(原幣)",
        "成本(原幣)※賣出需填", "應收付(原幣)", "損益(原幣)", "市值(新台幣)"
    ]
    share_cols = ["買入股數", "賣出股數"]

    def is_tw_symbol(sym: str) -> bool:
        s = normalize_symbol(str(sym).strip())
        return s.endswith(".TW") or s.endswith(".TWO")

    # 轉數值（失敗就 NaN）
    for c in money_cols + share_cols + ["報酬率"]:
        if c in df_view.columns:
            df_view[c] = pd.to_numeric(df_view[c], errors="coerce")

    # 先做必要 round：TWD 金額整數、台股股數整數
    if "幣別" in df_view.columns:
        mask_twd = df_view["幣別"].astype(str).str.upper().eq("TWD")
        for c in money_cols:
            if c in df_view.columns:
                df_view.loc[mask_twd, c] = df_view.loc[mask_twd, c].round(0)

    if "股票代號" in df_view.columns:
        mask_tw = df_view["股票代號"].apply(is_tw_symbol)
        for c in share_cols:
            if c in df_view.columns:
                df_view.loc[mask_tw, c] = df_view.loc[mask_tw, c].round(0)

    # 格式化：整數顯示無小數；非整數顯示小數
    def fmt_num(v):
        if pd.isna(v):
            return ""
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v)):,}"
        return f"{v:,.4f}"

    def fmt_share(v):
        if pd.isna(v):
            return ""
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v)):,}"
        return f"{v:,.5f}"

    def fmt_roi(v):
        if pd.isna(v):
            return ""
        return f"{v:.2f}%"

    fmt = {}
    for c in money_cols:
        if c in df_view.columns:
            fmt[c] = fmt_num
    for c in share_cols:
        if c in df_view.columns:
            fmt[c] = fmt_share
    if "報酬率" in df_view.columns:
        fmt["報酬率"] = fmt_roi

    st.dataframe(df_view.style.format(fmt), use_container_width=True)

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
