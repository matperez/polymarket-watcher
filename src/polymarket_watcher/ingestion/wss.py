"""WebSocket client for CLOB market channel: live ticks and market_resolved."""

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable

import websockets

logger = logging.getLogger(__name__)

WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


def _subscribe_message(asset_ids: list[str]) -> dict:
    return {
        "type": "market",
        "assets_ids": asset_ids,
        "custom_feature_enabled": True,
    }


def _parse_tick(msg: dict) -> tuple[int, float, str] | None:
    """Return (t, price, event_type) or None."""
    event = msg.get("event_type") or msg.get("eventType")
    if not event:
        return None
    ts = msg.get("timestamp") or msg.get("t") or int(time.time())
    if isinstance(ts, (int, float)):
        t = int(ts)
    else:
        t = int(time.time())
    price = None
    if event == "last_trade_price":
        price = msg.get("price")
    elif event in ("best_bid_ask", "price_change"):
        bid = msg.get("best_bid") or msg.get("best_bid_ask", {}).get("best_bid")
        ask = msg.get("best_ask") or msg.get("best_bid_ask", {}).get("best_ask")
        if bid is not None and ask is not None:
            try:
                price = (float(bid) + float(ask)) / 2
            except (TypeError, ValueError):
                pass
        if price is None and "price" in msg:
            price = msg.get("price")
    if price is not None:
        try:
            return (t, float(price), event)
        except (TypeError, ValueError):
            pass
    return None


def _parse_resolved(msg: dict) -> tuple[str | None, str | None]:
    """Return (winning_asset_id, winning_outcome) e.g. ('token-yes', 'Yes')."""
    aid = msg.get("winning_asset_id") or msg.get("winningAssetId")
    out = msg.get("winning_outcome") or msg.get("winningOutcome")
    return (aid, out)


async def _ws_loop(
    asset_ids: list[str],
    token_to_condition_id: dict[str, str],
    on_tick: Callable[[str, int, float, str], None],
    on_resolved: Callable[[str, str | None], None],
    url: str = WSS_URL,
    reconnect_delay: float = 5.0,
    max_reconnect_delay: float = 300.0,
):
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(_subscribe_message(asset_ids)))
                async for raw in ws:
                    try:
                        msg = json.loads(raw) if isinstance(raw, str) else raw
                    except (json.JSONDecodeError, TypeError):
                        continue
                    event = msg.get("event_type") or msg.get("eventType")
                    if event == "market_resolved":
                        aid, out = _parse_resolved(msg)
                        if aid is not None:
                            cid = token_to_condition_id.get(aid)
                            if cid:
                                on_resolved(cid, out)
                        continue
                    tick = _parse_tick(msg)
                    if tick is None:
                        continue
                    t, price, ev = tick
                    asset_id = msg.get("asset_id") or msg.get("assetId")
                    if not asset_id and asset_ids:
                        asset_id = asset_ids[0]
                    cid = token_to_condition_id.get(asset_id) if asset_id else None
                    if cid:
                        on_tick(cid, t, price, ev)
        except Exception as e:
            logger.warning("WebSocket error %s, reconnecting in %.0fs", e, reconnect_delay)
        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)


def run_ws_in_thread(
    asset_ids: list[str],
    token_to_condition_id: dict[str, str],
    on_tick: Callable[[str, int, float, str], None],
    on_resolved: Callable[[str, str | None], None],
    url: str = WSS_URL,
) -> threading.Thread:
    """Run WebSocket loop in a daemon thread. on_tick(condition_id, t, price, event_type); on_resolved(condition_id, outcome_str)."""
    def target():
        asyncio.run(
            _ws_loop(
                asset_ids=asset_ids,
                token_to_condition_id=token_to_condition_id,
                on_tick=on_tick,
                on_resolved=on_resolved,
                url=url,
            )
        )

    th = threading.Thread(target=target, daemon=True)
    th.start()
    return th


def write_tick_to_db(conn, condition_id: str, t: int, price: float, event_type: str) -> None:
    """Insert one row into live_ticks and commit."""
    conn.execute(
        "INSERT INTO live_ticks (condition_id, t, price, event_type) VALUES (?, ?, ?, ?)",
        (condition_id, t, price, event_type),
    )
    conn.commit()


def write_resolved_to_db(conn, condition_id: str, outcome: str | None) -> None:
    """Set markets.resolution_outcome (YES/NO). Caller should commit."""
    resolution = (outcome or "").strip().upper()
    if resolution not in ("YES", "NO"):
        resolution = "YES" if outcome else None
    conn.execute(
        "UPDATE markets SET resolution_outcome = ? WHERE condition_id = ?",
        (resolution, condition_id),
    )
    conn.commit()
