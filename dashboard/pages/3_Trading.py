"""
Trading page — place manual orders and run automated strategies.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
from pathlib import Path
from dashboard.data_helpers import get_broker_manager, load_signals, BASE_DIR

st.set_page_config(page_title="Trading", page_icon="⚡", layout="wide")
st.title("⚡ Trading")

mgr = get_broker_manager()
connected = mgr.connected_broker_names()

if not connected:
    st.warning("No brokers connected. Configure broker credentials in `.env` and restart.")
    st.stop()

tab_manual, tab_algo = st.tabs(["🖊️ Manual Order", "🤖 Strategy Execution"])

# ═══════════════════════════════════════════════════════════════════════════════
# MANUAL ORDER TAB
# ═══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.subheader("Place a Manual Order")

    # Pre-fill from signals page "Trade This" button via session state
    pre_ticker = st.session_state.get("prefill_ticker", "")
    pre_broker = st.session_state.get("prefill_broker", connected[0] if connected else "")

    col_form, col_result = st.columns([1, 1])

    with col_form:
        with st.form("manual_order_form"):
            broker    = st.selectbox("Broker",        connected,              index=connected.index(pre_broker) if pre_broker in connected else 0)
            ticker    = st.text_input("Ticker",       value=pre_ticker.upper(), help="e.g. AAPL, 2330.TW")
            side      = st.radio("Side",              ["BUY", "SELL"],         horizontal=True)
            qty       = st.number_input("Quantity",   min_value=1.0, value=100.0, step=1.0)
            order_type = st.selectbox("Order Type",   ["MARKET", "LIMIT", "STOP"])
            limit_price = st.number_input(
                "Limit / Stop Price",
                min_value=0.0, value=0.0, step=0.01,
                disabled=(order_type == "MARKET"),
                help="Required for LIMIT and STOP orders",
            )

            # Algo options depend on broker
            algo_options = ["DMA"]
            if broker == "IBKR":
                algo_options = ["DMA", "VWAP", "TWAP", "ADAPTIVE"]
            algo = st.selectbox(
                "Execution Algorithm",
                algo_options,
                help=(
                    "DMA = Direct Market Access (default)\n"
                    "VWAP/TWAP/ADAPTIVE = IBKR smart execution algos"
                ),
            )

            # Prominent warning for real money
            env_mode = os.getenv("MOOMOO_TRADE_ENV", "SIMULATE") if broker == "Moomoo" else "LIVE"
            if env_mode != "SIMULATE":
                st.warning("⚠️ This order will be sent to your **LIVE** account.", icon="⚠️")
            else:
                st.info("ℹ️ Moomoo is in SIMULATE mode — order will NOT hit real markets.")

            submitted = st.form_submit_button("🚀 Place Order", type="primary")

    with col_result:
        st.markdown("### Order Result")
        if submitted:
            if not ticker.strip():
                st.error("Ticker cannot be empty.")
            elif order_type != "MARKET" and limit_price <= 0:
                st.error(f"{order_type} order requires a valid limit/stop price.")
            else:
                with st.spinner("Sending order…"):
                    from brokers.strategies import ManualOrderExecutor
                    executor = ManualOrderExecutor(mgr)
                    intent   = executor.place(
                        broker_name = broker,
                        ticker      = ticker.strip().upper(),
                        side        = side,
                        qty         = qty,
                        order_type  = order_type,
                        limit_price = limit_price,
                        algo        = algo,
                    )

                if intent.success:
                    st.success(f"✅ Order placed! Order ID: `{intent.order_id}`")
                    st.info(intent.message)
                else:
                    st.error(f"❌ Order failed: {intent.message}")

                st.json({
                    "broker":      intent.broker,
                    "ticker":      intent.ticker,
                    "side":        intent.side,
                    "qty":         intent.qty,
                    "order_type":  intent.order_type,
                    "limit_price": intent.limit_price,
                    "algo":        intent.algo,
                    "success":     intent.success,
                    "order_id":    intent.order_id,
                    "message":     intent.message,
                })

    # Clear pre-fill state after rendering
    st.session_state.pop("prefill_ticker", None)
    st.session_state.pop("prefill_broker", None)

    st.divider()

    # ── Recent orders ─────────────────────────────────────────────────────────
    st.subheader("Recent Orders (last 7 days)")
    all_orders = []
    for name_ in connected:
        for c in mgr._clients:
            if c.name == name_:
                df = c.get_orders(days=7)
                if not df.empty:
                    df.insert(0, "broker", name_)
                    all_orders.append(df)
    if all_orders:
        orders_df = pd.concat(all_orders, ignore_index=True).sort_values("date", ascending=False)
        st.dataframe(orders_df, use_container_width=True, hide_index=True)
    else:
        st.info("No orders found in the last 7 days.")


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY EXECUTION TAB
# ═══════════════════════════════════════════════════════════════════════════════
with tab_algo:
    st.subheader("Automated Strategy Execution")

    strategy_name = st.selectbox(
        "Strategy",
        ["MeanReversion — Taiwan", "MeanReversion — US"],
        help=(
            "MeanReversion: buys signal stocks that satisfy price>MA120, RSI<35, Bias<-2%. "
            "Signals are generated by the daily scanner (master_run.py)."
        ),
    )

    market = "TW" if "Taiwan" in strategy_name else "US"
    signal_path = (
        str(BASE_DIR / "current_trending.csv")
        if market == "TW"
        else str(BASE_DIR / "data_us" / "current_trending.csv")
    )

    st.markdown("#### Parameters")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        strat_broker    = st.selectbox("Route orders to", connected, key="algo_broker")
        min_score       = st.slider("Min signal score", 0.0, 10.0, 5.0, 0.5)
        qty_per_trade   = st.number_input("Shares per trade", min_value=1.0, value=100.0, step=1.0)
    with p_col2:
        strat_order_type = st.selectbox("Order type", ["MARKET", "LIMIT"], key="algo_otype")
        strat_algo       = st.selectbox(
            "Execution algo",
            ["DMA", "VWAP", "TWAP", "ADAPTIVE"] if strat_broker == "IBKR" else ["DMA"],
            key="algo_exec",
        )
        dry_run = st.toggle("Dry run (preview only — no orders sent)", value=True)

    if not dry_run:
        st.warning(
            "⚠️ **Dry run is OFF.** Orders will be sent to your live broker account. "
            "Make sure signals are valid before executing.",
            icon="🚨",
        )

    # Preview table
    sig_df = load_signals(market)
    if sig_df.empty:
        st.warning(f"No {market} signal file found. Run `master_run.py` first to generate signals.")
    else:
        preview_df = sig_df[sig_df.get("score", 0) >= min_score][
            [c for c in ["ticker", "score", "price", "RSI", "bias", "vol_ratio", "news_sentiment"]
             if c in sig_df.columns]
        ].sort_values("score", ascending=False)

        st.markdown(f"**{len(preview_df)} stock(s) above score {min_score:.1f} — will be traded:**")
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        if st.button("▶️ Execute Strategy", type="primary", disabled=sig_df.empty):
            from brokers.strategies import MeanReversionExecutor
            executor = MeanReversionExecutor(
                manager       = mgr,
                broker_name   = strat_broker,
                min_score     = min_score,
                qty_per_trade = qty_per_trade,
                order_type    = strat_order_type,
                algo          = strat_algo,
                dry_run       = dry_run,
            )
            with st.spinner("Running strategy…"):
                intents = executor.run(signal_path)

            st.success(f"Strategy run complete — {len(intents)} intent(s) processed.")
            results_data = [
                {
                    "ticker":    i.ticker,
                    "side":      i.side,
                    "qty":       i.qty,
                    "broker":    i.broker,
                    "success":   i.success if not dry_run else "DRY RUN",
                    "order_id":  i.order_id,
                    "message":   i.message,
                }
                for i in intents
            ]
            st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)
