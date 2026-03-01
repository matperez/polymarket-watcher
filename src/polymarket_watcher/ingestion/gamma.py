"""Gamma API client: fetch closed events and poll into DB."""

import json
import time
from datetime import datetime

import httpx


def _parse_end_date_ts(end_date: str | None) -> int | None:
    if not end_date:
        return None
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def _normalize_market(m: dict) -> dict:
    raw = m.get("clobTokenIds")
    if isinstance(raw, str):
        try:
            clob_ids = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            clob_ids = []
    elif isinstance(raw, list):
        clob_ids = raw
    else:
        clob_ids = []
    token_id_yes = clob_ids[0] if len(clob_ids) > 0 else None
    token_id_no = clob_ids[1] if len(clob_ids) > 1 else None
    return {
        "condition_id": m.get("conditionId") or "",
        "token_id_yes": token_id_yes,
        "token_id_no": token_id_no,
        "slug": m.get("slug") or "",
        "question": m.get("question") or "",
        "end_date_ts": _parse_end_date_ts(m.get("endDate")),
        "closed": bool(m.get("closed", False)),
    }


def _parse_events_response(data: list) -> list[dict]:
    result = []
    for ev in data:
        if not isinstance(ev, dict):
            continue
        markets = ev.get("markets") or []
        result.append({
            "id": ev.get("id"),
            "slug": ev.get("slug") or "",
            "title": ev.get("title") or "",
            "closed": bool(ev.get("closed", False)),
            "markets": [_normalize_market(m) for m in markets if isinstance(m, dict)],
        })
    return result


async def fetch_closed_events(
    base_url: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Fetch closed events from Gamma API. Returns list of events with normalized markets."""
    url = f"{base_url.rstrip('/')}/events"
    params = {"closed": "true", "limit": limit, "offset": offset}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list):
        return []
    return _parse_events_response(data)


def _fetch_closed_events_sync(base_url: str, limit: int = 100, offset: int = 0) -> list[dict]:
    url = f"{base_url.rstrip('/')}/events"
    params = {"closed": "true", "limit": limit, "offset": offset}
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    return _parse_events_response(data)


def poll_gamma_to_db(
    conn,
    base_url: str,
    limit: int = 100,
) -> int:
    """Fetch closed events and upsert markets into DB. Returns number of markets upserted."""
    events = _fetch_closed_events_sync(base_url, limit=limit)
    now_ts = int(time.time())
    n = 0
    for ev in events:
        for m in ev.get("markets") or []:
            cid = m.get("condition_id")
            if not cid:
                continue
            conn.execute(
                """INSERT INTO markets
                   (condition_id, token_id_yes, token_id_no, slug, question,
                    end_date_ts, closed, event_slug, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(condition_id) DO UPDATE SET
                   token_id_yes=excluded.token_id_yes,
                   token_id_no=excluded.token_id_no,
                   slug=excluded.slug, question=excluded.question,
                   end_date_ts=excluded.end_date_ts,
                   closed=excluded.closed, event_slug=excluded.event_slug,
                   updated_at=excluded.updated_at
                   """,
                (
                    cid,
                    m.get("token_id_yes"),
                    m.get("token_id_no"),
                    m.get("slug"),
                    m.get("question"),
                    m.get("end_date_ts"),
                    1 if m.get("closed") else 0,
                    ev.get("slug"),
                    now_ts,
                ),
            )
            n += 1
    conn.commit()
    return n
