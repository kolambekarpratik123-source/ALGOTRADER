"""Algotrader Streamlit dashboard — monitor trades, run backtests, view live quotes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from dashboard.runner import is_engine_running, start_engine, stop_engine
from src.backtest.engine import BacktestEngine
from src.config import Settings
from src.data import create_data_provider
from src.data.mock_provider import SEED_PRICES
from src.storage.state import (
    load_backtest_results,
    load_state,
    load_trades,
    save_backtest_results,
    save_state,
)
from src.strategies.registry import get_strategy, list_strategies

# ──────────────────────────────────────────
#  FULL BSE / NSE COMPANY CATALOGUE
# ──────────────────────────────────────────
ALL_SYMBOLS = sorted(SEED_PRICES.keys())

# ──────────────────────────────────────────
#  PAGE CONFIG & GLOBAL CSS
# ──────────────────────────────────────────
st.set_page_config(
    page_title="Algotrader Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Import fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

    /* Root & background */
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp {
        background: linear-gradient(135deg, #0a0e1a 0%, #0d1526 50%, #111827 100%);
        color: #e2e8f0;
    }

    /* Remove Streamlit default top padding — reclaim vertical space */
    .block-container { padding-top: 0.6rem !important; padding-bottom: 0.5rem !important; }
    /* Keep header minimal so native sidebar button stays accessible */
    header[data-testid="stHeader"] { background: transparent !important; height: 2.2rem !important; }

    /* Sidebar — narrow & compact */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        border-right: 1px solid rgba(99,102,241,0.2);
        min-width: 240px !important;
        max-width: 280px !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 { color: #818cf8; }
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }

    /* ── Slim header bar ── */
    .dashboard-header {
        background: linear-gradient(90deg, rgba(99,102,241,0.18) 0%, rgba(139,92,246,0.1) 100%);
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 10px;
        padding: 8px 20px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }
    .dashboard-header h1 {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 700;
        background: linear-gradient(90deg, #818cf8, #a78bfa, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        white-space: nowrap;
    }
    .dashboard-header p {
        margin: 0;
        color: #64748b;
        font-size: 0.75rem;
        white-space: nowrap;
    }

    /* ── Compact KPI grid (4 across) ── */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin-bottom: 8px;
    }
    .kpi-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.85) 0%, rgba(15,23,42,0.9) 100%);
        border: 1px solid rgba(99,102,241,0.2);
        border-radius: 10px;
        padding: 10px 14px;
        transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
        backdrop-filter: blur(8px);
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        border-color: rgba(99,102,241,0.5);
        box-shadow: 0 6px 20px rgba(99,102,241,0.15);
    }
    .kpi-label { font-size: 0.65rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
    .kpi-value { font-size: 1.15rem; font-weight: 700; color: #e2e8f0; margin-top: 3px; font-family: 'JetBrains Mono', monospace; }
    .kpi-value.positive { color: #34d399; }
    .kpi-value.negative { color: #f87171; }
    .kpi-value.neutral  { color: #818cf8; }

    /* Engine status badge */
    .engine-running {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.4);
        color: #34d399; border-radius: 20px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;
    }
    .engine-stopped {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.4);
        color: #f87171; border-radius: 20px; padding: 4px 12px; font-size: 0.75rem; font-weight: 600;
    }
    .pulse { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.5;transform:scale(1.3)} }

    /* ── Compact section headers ── */
    .section-header {
        font-size: 0.7rem; font-weight: 700; color: #818cf8;
        text-transform: uppercase; letter-spacing: 1.5px;
        border-bottom: 1px solid rgba(99,102,241,0.2);
        padding-bottom: 4px; margin: 8px 0 6px 0;
    }

    /* Tabs — compact */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(15,23,42,0.5);
        border-radius: 10px;
        padding: 3px;
        border: 1px solid rgba(99,102,241,0.15);
        margin-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 7px;
        color: #64748b;
        font-weight: 500;
        font-size: 0.82rem;
        padding: 5px 14px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.3)) !important;
        color: #818cf8 !important;
    }

    /* Dataframe */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    .stDataFrame table { font-size: 0.78rem !important; }

    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.82rem;
        padding: 4px 12px !important;
        transition: all 0.2s;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        border: none;
        color: white;
        box-shadow: 0 3px 12px rgba(99,102,241,0.3);
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 5px 18px rgba(99,102,241,0.5);
        transform: translateY(-1px);
    }

    /* Metrics */
    [data-testid="stMetric"] { background: transparent; }
    [data-testid="stMetricLabel"] { color: #64748b !important; font-size: 0.65rem !important; text-transform: uppercase; letter-spacing: 0.8px; }
    [data-testid="stMetricValue"] { color: #e2e8f0 !important; font-family: 'JetBrains Mono', monospace; font-size: 1rem !important; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 3px; }

    /* Element spacing reduction */
    div[data-testid="stVerticalBlock"] > div { padding-bottom: 0.2rem !important; }
    div[data-testid="column"] { padding: 0 6px !important; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────
#  LOAD DATA
# ──────────────────────────────────────────
settings = Settings()
state = load_state()
trades = load_trades()
backtest = load_backtest_results()

# ──────────────────────────────────────────
#  HEADER
# ──────────────────────────────────────────
mode_badge = (
    '<span style="background:rgba(99,102,241,0.2);border:1px solid #818cf8;color:#818cf8;padding:3px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;">📄 PAPER TRADING (MOCK)</span>'
    if settings.trading_mode.value == "paper"
    else '<span style="background:rgba(52,211,153,0.2);border:1px solid #34d399;color:#34d399;padding:3px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;">🚀 KITE LIVE TRADING</span>'
)

st.markdown(f"""
<div class="dashboard-header">
    <div style="display:flex;align-items:center;gap:12px;">
        <h1>📈 Algotrader Pro</h1>
        {mode_badge}
    </div>
    <p>BSE · NSE · Real-time trading engine · Multi-strategy</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────
#  SIDEBAR TOGGLE BUTTON (components.html)
# ──────────────────────────────────────────
components.html("""
<style>
#sb-toggle {
    position: fixed;
    top: 8px;
    left: 8px;
    z-index: 999999;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border: none;
    border-radius: 8px;
    color: white;
    font-size: 1.2rem;
    width: 36px;
    height: 36px;
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(99,102,241,0.45);
    transition: box-shadow 0.2s, transform 0.2s;
    line-height: 36px;
    text-align: center;
    padding: 0;
}
#sb-toggle:hover { box-shadow: 0 6px 22px rgba(99,102,241,0.65); transform: scale(1.08); }
</style>
<button id="sb-toggle" title="Toggle sidebar">☰</button>
<script>
document.getElementById('sb-toggle').addEventListener('click', function() {
    var d = window.parent.document;
    var selectors = [
        '[data-testid="stSidebarCollapseButton"] button',
        '[data-testid="stSidebarCollapseButton"]',
        '[data-testid="collapsedControl"] button',
        '[data-testid="collapsedControl"]',
        'button[aria-label="Close sidebar"]',
        'button[aria-label="Open sidebar"]',
        'button[aria-label="Collapse sidebar"]',
        'button[aria-label="Expand sidebar"]'
    ];
    for (var i = 0; i < selectors.length; i++) {
        var btn = d.querySelector(selectors[i]);
        if (btn) { btn.click(); return; }
    }
    var sb = d.querySelector('section[data-testid="stSidebar"]');
    if (sb) {
        if (sb.getAttribute('aria-expanded') === 'false' || sb.style.display === 'none') {
            sb.style.display = '';
            sb.style.transform = 'none';
            sb.setAttribute('aria-expanded', 'true');
        } else {
            sb.style.transform = 'translateX(-100%)';
            sb.setAttribute('aria-expanded', 'false');
        }
    }
});
</script>
""", height=0)

# ──────────────────────────────────────────
#  SIDEBAR
# ──────────────────────────────────────────
with st.sidebar:

    # ── TRADING PARAMETERS ──────────────────
    st.markdown('<div class="section-header">💰 Trading Parameters</div>', unsafe_allow_html=True)

    user_capital = st.number_input(
        "Capital (Rs.)",
        min_value=1000,
        max_value=100_000_000,
        value=int(settings.initial_capital),
        step=5000,
        help="Total capital you are deploying",
    )
    profit_target_pct = st.slider(
        "Profit Target %",
        min_value=1, max_value=200, value=10, step=1,
        help="Return you are aiming for on your capital",
    )
    risk_pct = st.slider(
        "Risk Capacity %",
        min_value=1, max_value=50, value=int(settings.max_daily_loss_pct), step=1,
        help="Maximum loss you can tolerate (of your capital)",
    )

    profit_target_rs = user_capital * profit_target_pct / 100
    max_loss_rs = user_capital * risk_pct / 100
    reward_risk = profit_target_rs / max_loss_rs if max_loss_rs else 0

    tp_color = "#34d399"
    sl_color = "#f87171"
    st.markdown(f"""
    <div style="background:rgba(15,23,42,0.7);border:1px solid rgba(99,102,241,0.2);border-radius:10px;padding:10px 14px;margin:6px 0;">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <span style="color:#64748b;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.8px;">Target Profit</span>
        <span style="color:{tp_color};font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.85rem;">+Rs.{profit_target_rs:,.0f}</span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <span style="color:#64748b;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.8px;">Max Allowed Loss</span>
        <span style="color:{sl_color};font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.85rem;">-Rs.{max_loss_rs:,.0f}</span>
      </div>
      <div style="display:flex;justify-content:space-between;">
        <span style="color:#64748b;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.8px;">Reward : Risk</span>
        <span style="color:#818cf8;font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.85rem;">{reward_risk:.1f}x</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    settings.initial_capital = float(user_capital)
    settings.max_daily_loss_pct = float(risk_pct)

    st.divider()

    # ── KITE ZERODHA CONNECT ────────────────
    st.markdown('<div class="section-header">🔗 Kite Zerodha</div>', unsafe_allow_html=True)

    kite_ok = bool(settings.kite_api_key and settings.kite_access_token)
    if kite_ok:
        st.markdown('<span class="engine-running"><span class="pulse"></span> KITE CONNECTED</span>', unsafe_allow_html=True)
        st.caption(f"API Key: {settings.kite_api_key[:6]}****")
        if st.button("🔌 Disconnect / Change Keys", use_container_width=True):
            st.session_state["show_kite_form"] = True
    else:
        st.markdown('<span class="engine-stopped"><span class="pulse"></span> NOT CONNECTED</span>', unsafe_allow_html=True)
        st.session_state.setdefault("show_kite_form", True)

    if st.session_state.get("show_kite_form", not kite_ok):
        with st.expander("🔑 Enter Kite Credentials", expanded=True):
            k_api_key = st.text_input("API Key", value=settings.kite_api_key, type="default", key="k_api_key")
            k_api_secret = st.text_input("API Secret", value=settings.kite_api_secret, type="password", key="k_api_secret")

            if k_api_key:
                login_url = f"https://kite.trade/connect/login?api_key={k_api_key}&v=3"
                st.markdown(
                    f'<a href="{login_url}" target="_blank" style="display:block;text-align:center;'
                    f'background:linear-gradient(135deg,#6366f1,#8b5cf6);color:white;border-radius:8px;'
                    f'padding:6px 0;font-size:0.8rem;font-weight:600;text-decoration:none;margin:6px 0;">'
                    f'🌐 Step 1: Login to Kite</a>',
                    unsafe_allow_html=True,
                )
                st.caption("After login, copy the `request_token` from the redirect URL.")

            k_request_token = st.text_input("Request Token (from redirect URL)", key="k_request_token", placeholder="Paste here after login")

            if st.button("⚡ Generate Access Token & Connect", type="primary", use_container_width=True):
                if not k_api_key or not k_api_secret or not k_request_token:
                    st.error("Fill in all fields above first.")
                else:
                    try:
                        from kiteconnect import KiteConnect
                        kc = KiteConnect(api_key=k_api_key)
                        data = kc.generate_session(k_request_token, api_secret=k_api_secret)
                        access_token = data["access_token"]

                        env_path = Path(__file__).resolve().parent.parent / ".env"
                        env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

                        def _set_env(text, key, val):
                            import re
                            pattern = rf"^{key}=.*$"
                            repl = f"{key}={val}"
                            if re.search(pattern, text, re.MULTILINE):
                                return re.sub(pattern, repl, text, flags=re.MULTILINE)
                            return text + f"\n{repl}"

                        env_text = _set_env(env_text, "KITE_API_KEY", k_api_key)
                        env_text = _set_env(env_text, "KITE_API_SECRET", k_api_secret)
                        env_text = _set_env(env_text, "KITE_ACCESS_TOKEN", access_token)
                        env_text = _set_env(env_text, "TRADING_MODE", "live")
                        env_path.write_text(env_text, encoding="utf-8")

                        st.success("✅ Connected! Access token saved. Refreshing...")
                        st.session_state["show_kite_form"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Connection failed: {e}")

    st.divider()

    # ── TRADING MODE & EXCHANGE SELECTOR ───
    st.markdown('<div class="section-header">⚙️ Trading Mode & Exchange</div>', unsafe_allow_html=True)

    mode_options = ["📄 Paper Trading (Mock Data)", "🚀 Live Trading (Zerodha Kite)"]
    current_mode_idx = 0 if settings.trading_mode.value == "paper" else 1

    chosen_mode = st.radio(
        "Select Execution Mode",
        options=mode_options,
        index=current_mode_idx,
        help="Paper Trading uses virtual cash and simulated market ticks. Live Trading connects to Zerodha Kite.",
    )

    target_mode = "paper" if "Paper" in chosen_mode else "live"
    if target_mode != settings.trading_mode.value:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        def _update_env(text, key, val):
            import re
            pattern = rf"^{key}=.*$"
            repl = f"{key}={val}"
            if re.search(pattern, text, re.MULTILINE):
                return re.sub(pattern, repl, text, flags=re.MULTILINE)
            return text + f"\n{repl}"
        env_text = _update_env(env_text, "TRADING_MODE", target_mode)
        env_path.write_text(env_text, encoding="utf-8")
        st.toast(f"Switched mode to {target_mode.upper()}!", icon="🔄")
        st.rerun()

    col_ex1, col_ex2 = st.columns(2)
    col_ex1.metric("Current Mode", settings.trading_mode.value.upper())
    chosen_ex = col_ex2.selectbox(
        "Exchange",
        options=["BSE", "NSE"],
        index=0 if settings.exchange.value == "BSE" else 1,
    )
    if chosen_ex != settings.exchange.value:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        def _update_env(text, key, val):
            import re
            pattern = rf"^{key}=.*$"
            repl = f"{key}={val}"
            if re.search(pattern, text, re.MULTILINE):
                return re.sub(pattern, repl, text, flags=re.MULTILINE)
            return text + f"\n{repl}"
        env_text = _update_env(env_text, "EXCHANGE", chosen_ex)
        env_path.write_text(env_text, encoding="utf-8")
        st.rerun()

    st.divider()

    # ── WATCHLIST MANAGER ────────────────────
    st.markdown('<div class="section-header">📋 Watchlist</div>', unsafe_allow_html=True)
    current_watchlist = list(settings.symbols)

    selected_from_list = st.multiselect(
        "Select companies",
        options=ALL_SYMBOLS,
        default=[s for s in current_watchlist if s in ALL_SYMBOLS],
        help="Pick from 150+ BSE/NSE companies",
    )

    custom_input = st.text_input(
        "Add custom symbol",
        placeholder="e.g. IRFC, DIXON, NIFTY50",
        help="Type any BSE/NSE ticker and press Enter",
    )

    custom_symbols = [s.strip().upper() for s in custom_input.split(",") if s.strip()]
    watchlist = list(dict.fromkeys(selected_from_list + custom_symbols))

    if watchlist:
        st.caption(f"**{len(watchlist)} symbols:** {', '.join(watchlist[:8])}{'...' if len(watchlist)>8 else ''}")
    else:
        st.warning("Add at least one symbol to your watchlist.")

    st.divider()

    # ── ENGINE CONTROL ───────────────────────
    st.markdown('<div class="section-header">🚀 Engine Control</div>', unsafe_allow_html=True)
    running = is_engine_running()

    if running:
        st.markdown('<span class="engine-running"><span class="pulse"></span> ENGINE RUNNING</span>', unsafe_allow_html=True)
        st.write("")
        if st.button("⏹ Stop Engine", type="secondary", use_container_width=True):
            if stop_engine():
                st.success("Engine stopped.")
                st.rerun()
    else:
        st.markdown('<span class="engine-stopped"><span class="pulse"></span> ENGINE STOPPED</span>', unsafe_allow_html=True)
        st.write("")
        run_strategy = st.selectbox(
            "Strategy",
            list_strategies(),
            index=list_strategies().index(settings.strategy) if settings.strategy in list_strategies() else 0,
            key="run_strategy",
        )
        run_interval = st.number_input("Cycle interval (s)", min_value=1, max_value=3600, value=5, step=1)

        if st.button("▶ Start Engine", type="primary", use_container_width=True):
            if watchlist:
                settings.watchlist = ",".join(watchlist)
            if start_engine(settings, run_strategy, int(run_interval)):
                st.success("Engine started!")
                st.rerun()
            else:
                st.error("Failed to start engine.")

    st.divider()
    auto_refresh = st.checkbox("⟳ Auto-refresh (5s)", value=True)

    st.divider()

    # ── BACKTEST CONTROLS ───────────────────
    st.markdown('<div class="section-header">🔬 Backtest</div>', unsafe_allow_html=True)
    bt_strategy = st.selectbox("Strategy##bt", list_strategies(), index=list_strategies().index(settings.strategy) if settings.strategy in list_strategies() else 0)
    bt_all_syms = watchlist if watchlist else settings.symbols
    bt_symbol = st.selectbox("Symbol##bt", bt_all_syms)
    bt_candles = st.slider("Candles", 100, 500, 200)

    if st.button("Run Backtest", type="primary", use_container_width=True):
        with st.spinner("Running backtest…"):
            async def _fetch():
                provider = create_data_provider(
                    settings.trading_mode.value,
                    settings.kite_api_key,
                    settings.kite_access_token,
                )
                await provider.connect()
                data = await provider.get_candles(bt_symbol, settings.exchange.value, count=bt_candles)
                await provider.disconnect()
                return data

            candles = asyncio.run(_fetch())
            if len(candles) >= 30:
                strat = get_strategy(bt_strategy)
                result = BacktestEngine(settings, strat).run(bt_symbol, candles)
                save_backtest_results(result.to_dict())
                st.success(f"Return: {result.total_return_pct:+.2f}% | Trades: {result.total_trades}")
                st.rerun()
            else:
                st.error("Not enough data.")

# ──────────────────────────────────────────
#  TOP KPI BAR
# ──────────────────────────────────────────
portfolio_val = state.get("portfolio_value", settings.initial_capital)
cash = state.get("cash", settings.initial_capital)
daily_pnl = state.get("daily_pnl", 0.0)
positions_list = state.get("positions", [])
positions_count = len(positions_list)
total_trades_done = len(trades)

pnl_class = "positive" if daily_pnl > 0 else ("negative" if daily_pnl < 0 else "neutral")
pnl_sign = "+" if daily_pnl >= 0 else ""

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">Portfolio Value</div>
        <div class="kpi-value neutral">Rs.{portfolio_val:,.2f}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Cash Available</div>
        <div class="kpi-value neutral">Rs.{cash:,.2f}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Daily P&L</div>
        <div class="kpi-value {pnl_class}">Rs.{pnl_sign}{daily_pnl:,.2f}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Positions · Trades</div>
        <div class="kpi-value neutral">{positions_count} &nbsp;·&nbsp; {total_trades_done}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────
#  MAIN TABS
# ──────────────────────────────────────────
tab_trading, tab_backtest, tab_quotes = st.tabs([
    "📊 Trading — Positions & Log", "🔬 Backtest Results", "💹 Live Quotes"
])

# ══════════════════════════════════════════
#  TAB 1 — COMBINED POSITIONS + TRADE LOG
# ══════════════════════════════════════════
with tab_trading:

    # ── FULL WIDTH: Open Positions table ──
    st.markdown('<div class="section-header">📂 Open Positions</div>', unsafe_allow_html=True)
    if state.get("updated_at"):
        st.caption(f"Last sync: {state['updated_at']}")

    if positions_list:
        pos_df = pd.DataFrame(positions_list)
        if "unrealized_pnl" in pos_df.columns:
            total_unrealized = pos_df["unrealized_pnl"].sum()
            sign = "+" if total_unrealized >= 0 else ""
            color = "#34d399" if total_unrealized >= 0 else "#f87171"
            st.markdown(
                f'<p style="font-size:0.95rem;font-weight:700;color:{color};font-family:JetBrains Mono,monospace;margin:0 0 4px 0;">'
                f'Unrealized P&L: {sign}Rs.{total_unrealized:,.2f}</p>',
                unsafe_allow_html=True,
            )
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions yet. Start the engine to begin paper trading.", icon="📭")

    # ── TWO COLUMNS: Unrealized P&L chart | Realized P&L charts ──
    left_col, right_col = st.columns([1, 2], gap="large")

    with left_col:
        if positions_list and "unrealized_pnl" in pd.DataFrame(positions_list).columns:
            pos_df2 = pd.DataFrame(positions_list)
            fig_pos = go.Figure(go.Bar(
                x=pos_df2.get("symbol", pos_df2.index),
                y=pos_df2["unrealized_pnl"],
                marker_color=["#34d399" if v >= 0 else "#f87171" for v in pos_df2["unrealized_pnl"]],
                text=[f"Rs.{v:+,.0f}" for v in pos_df2["unrealized_pnl"]],
                textposition="outside",
            ))
            fig_pos.update_layout(
                title="Unrealized P&L per Position",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94a3b8", title_font_color="#818cf8",
                xaxis=dict(showgrid=False, color="#64748b"),
                yaxis=dict(showgrid=True, gridcolor="rgba(99,102,241,0.1)", color="#64748b"),
                margin=dict(t=36, b=8, l=8, r=8), height=180,
            )
            st.plotly_chart(fig_pos, use_container_width=True)
        else:
            st.empty()

    with right_col:
        st.markdown('<div class="section-header">📊 P&L Summary</div>', unsafe_allow_html=True)

        if trades:
            df = pd.DataFrame(trades)

            def _style_action(val):
                if val == "BUY":
                    return "color: #34d399; font-weight: 700;"
                elif val == "SELL":
                    return "color: #f87171; font-weight: 700;"
                return ""

            def _style_pnl(val):
                try:
                    v = float(val)
                    return "color: #34d399; font-weight: 700;" if v > 0 else ("color: #f87171; font-weight: 700;" if v < 0 else "")
                except Exception:
                    return ""

            if "pnl" in df.columns:
                sells = df[df["action"] == "SELL"]
                if not sells.empty:
                    total_pnl = sells["pnl"].sum()
                    win_trades = (sells["pnl"] > 0).sum()
                    loss_trades = (sells["pnl"] <= 0).sum()
                    win_rate = win_trades / len(sells) * 100 if len(sells) > 0 else 0

                    m1, m2, m3 = st.columns(3)
                    pnl_delta = f"+Rs.{total_pnl:,.0f}" if total_pnl >= 0 else f"Rs.{total_pnl:,.0f}"
                    m1.metric("Realized P&L", pnl_delta)
                    m2.metric("Win Rate", f"{win_rate:.1f}%")
                    m3.metric("W / L Trades", f"{win_trades} / {loss_trades}")

                    sells_sorted = sells.copy().reset_index(drop=True)
                    sells_sorted["cumulative_pnl"] = sells_sorted["pnl"].cumsum()

                    # Cumulative P&L line chart
                    fig_pnl = go.Figure()
                    fig_pnl.add_trace(go.Scatter(
                        x=sells_sorted.index + 1,
                        y=sells_sorted["cumulative_pnl"],
                        mode="lines+markers",
                        line=dict(color="#818cf8", width=2),
                        marker=dict(
                            color=["#34d399" if v >= 0 else "#f87171" for v in sells_sorted["pnl"]],
                            size=7,
                        ),
                        fill="tozeroy",
                        fillcolor="rgba(99,102,241,0.08)",
                        name="Cumulative P&L",
                    ))
                    fig_pnl.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.2)")
                    fig_pnl.update_layout(
                        title="Cumulative Realized P&L",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#94a3b8", title_font_color="#818cf8",
                        xaxis=dict(title="Trade #", showgrid=False, color="#64748b"),
                        yaxis=dict(title="Rs.", showgrid=True, gridcolor="rgba(99,102,241,0.1)", color="#64748b"),
                        margin=dict(t=36, b=8, l=8, r=8), height=200,
                    )
                    st.plotly_chart(fig_pnl, use_container_width=True)

                    # Per-trade P&L bar
                    fig_bar = go.Figure(go.Bar(
                        x=sells_sorted.index + 1,
                        y=sells_sorted["pnl"],
                        marker_color=["#34d399" if p > 0 else "#f87171" for p in sells_sorted["pnl"]],
                        text=[f"Rs.{p:+,.0f}" for p in sells_sorted["pnl"]],
                        textposition="outside",
                        name="Trade P&L",
                    ))
                    fig_bar.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.2)")
                    fig_bar.update_layout(
                        title="Per-Trade P&L",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="#94a3b8", title_font_color="#818cf8",
                        xaxis=dict(title="Trade #", showgrid=False, color="#64748b"),
                        yaxis=dict(title="Rs.", showgrid=True, gridcolor="rgba(99,102,241,0.1)", color="#64748b"),
                        margin=dict(t=36, b=8, l=8, r=8), height=180,
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No trades yet. Start the engine to see P&L charts.", icon="📉")

    # ══════════════════════════════════════════
    # FULL-WIDTH TRADE LOG
    # ══════════════════════════════════════════
    st.markdown('<div class="section-header" style="margin-top:10px;">📋 Full Trade Log</div>', unsafe_allow_html=True)

    if trades:
        df_full = pd.DataFrame(trades)

        def _style_action2(val):
            if val == "BUY":
                return "color: #34d399; font-weight: 700;"
            elif val == "SELL":
                return "color: #f87171; font-weight: 700;"
            return ""

        def _style_pnl2(val):
            try:
                v = float(val)
                return "color: #34d399; font-weight: 700;" if v > 0 else ("color: #f87171; font-weight: 700;" if v < 0 else "")
            except Exception:
                return ""

        styled_full = df_full.style
        if "action" in df_full.columns:
            styled_full = styled_full.map(_style_action2, subset=["action"])
        if "pnl" in df_full.columns:
            styled_full = styled_full.map(_style_pnl2, subset=["pnl"])

        st.dataframe(styled_full, use_container_width=True, hide_index=True, height=280)
    else:
        st.info("No trades executed yet. Start the engine to see your trade history here.", icon="📉")

# ══════════════════════════════════════════
#  TAB 2 — BACKTEST
# ══════════════════════════════════════════
with tab_backtest:
    st.subheader("Backtest Results")
    backtest_data = load_backtest_results()
    if backtest_data:
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.metric("Return", f"{backtest_data.get('total_return_pct', 0):+.2f}%")
        bc2.metric("Win Rate", f"{backtest_data.get('win_rate', 0):.1f}%")
        bc3.metric("Max Drawdown", f"{backtest_data.get('max_drawdown_pct', 0):.2f}%")
        bc4.metric("Sharpe", f"{backtest_data.get('sharpe_ratio', 0):.2f}")

        equity = backtest_data.get("equity_curve", [])
        if equity:
            eq_df = pd.DataFrame(equity)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=eq_df["time"], y=eq_df["equity"], mode="lines", name="Equity",
                line=dict(color="#818cf8", width=2), fill="tozeroy",
                fillcolor="rgba(99,102,241,0.08)",
            ))
            fig.update_layout(
                title=f"Equity Curve — {backtest_data.get('symbol', '')}",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94a3b8", title_font_color="#818cf8",
                xaxis=dict(showgrid=False, color="#64748b"),
                yaxis=dict(title="Rs.", showgrid=True, gridcolor="rgba(99,102,241,0.1)", color="#64748b"),
                margin=dict(t=40, b=10, l=10, r=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        bt_trades = backtest_data.get("trades", [])
        if bt_trades:
            st.dataframe(pd.DataFrame(bt_trades), use_container_width=True)
    else:
        st.info("Run a backtest from the sidebar.", icon="🔬")

# ══════════════════════════════════════════
#  TAB 3 — LIVE QUOTES
# ══════════════════════════════════════════
with tab_quotes:
    st.markdown('<div class="section-header">💹 Live Quotes</div>', unsafe_allow_html=True)
    quotes_data = state.get("quotes", {})

    q_symbols = watchlist if watchlist else settings.symbols
    if st.button("⟳ Refresh Quotes", type="primary"):
        with st.spinner("Fetching live quotes…"):
            async def _refresh():
                provider = create_data_provider(
                    settings.trading_mode.value,
                    settings.kite_api_key,
                    settings.kite_access_token,
                )
                await provider.connect()
                res = {}
                for sym in q_symbols:
                    q = await provider.get_quote(sym, settings.exchange.value)
                    if q:
                        res[sym] = {"ltp": q.ltp, "volume": q.volume, "time": q.timestamp.isoformat()}
                await provider.disconnect()
                return res

            quotes_data = asyncio.run(_refresh())
            if quotes_data:
                state["quotes"] = quotes_data
                save_state(state)
                st.rerun()

    if quotes_data:
        rows = []
        for s, d in quotes_data.items():
            ltp = d["ltp"]
            rows.append({
                "Symbol": s,
                "LTP (Rs.)": f"{ltp:,.2f}",
                "Volume": f"{d['volume']:,}",
                "Time": d["time"],
            })
        q_df = pd.DataFrame(rows)
        st.dataframe(q_df, use_container_width=True, hide_index=True)

        ltp_vals = [d["ltp"] for d in quotes_data.values()]
        syms = list(quotes_data.keys())
        fig_q = go.Figure(go.Bar(
            x=syms, y=ltp_vals,
            marker=dict(
                color=ltp_vals,
                colorscale="Viridis",
                showscale=False,
            ),
            text=[f"Rs.{v:,.0f}" for v in ltp_vals],
            textposition="outside",
        ))
        fig_q.update_layout(
            title="Last Traded Price Comparison",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#94a3b8", title_font_color="#818cf8",
            xaxis=dict(showgrid=False, color="#64748b", tickangle=-35),
            yaxis=dict(showgrid=True, gridcolor="rgba(99,102,241,0.1)", color="#64748b", title="Rs."),
            margin=dict(t=40, b=60, l=10, r=10),
        )
        st.plotly_chart(fig_q, use_container_width=True)
    else:
        st.info("No quotes loaded. Click 'Refresh Quotes' or start the engine.", icon="💹")

# ──────────────────────────────────────────
#  AUTO-REFRESH
# ──────────────────────────────────────────
if auto_refresh:
    time.sleep(5)
    st.rerun()
