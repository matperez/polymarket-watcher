"""CLI for polymarket-watcher API: list, add, remove, update watched markets; summary."""

import argparse
import json
import os
import sys

import httpx

DEFAULT_API_URL = "http://localhost:8080"


def _get_base_url(api_url: str | None) -> str:
    return (api_url or os.environ.get("WATCHER_API_URL") or DEFAULT_API_URL).rstrip("/")


def _cmd_list(base_url: str) -> int:
    r = httpx.get(f"{base_url}/watched", timeout=30.0)
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data, indent=2))
    return 0


def _cmd_add(
    base_url: str,
    condition_id: str,
    token_id_yes: str,
    slug: str | None,
) -> int:
    body = {"condition_id": condition_id, "token_id_yes": token_id_yes}
    if slug is not None:
        body["slug"] = slug
    r = httpx.post(f"{base_url}/watched", json=body, timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def _cmd_remove(base_url: str, condition_id: str) -> int:
    r = httpx.delete(f"{base_url}/watched/{condition_id}", timeout=30.0)
    r.raise_for_status()
    return 0


def _cmd_update(base_url: str, condition_id: str, slug: str | None) -> int:
    body = {} if slug is None else {"slug": slug}
    r = httpx.put(f"{base_url}/watched/{condition_id}", json=body, timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def _cmd_summary(base_url: str, condition_id: str) -> int:
    r = httpx.get(f"{base_url}/watched/{condition_id}/summary", timeout=30.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="polymarket-watcher-cli",
        description="Manage watched markets via polymarket-watcher API",
    )
    parser.add_argument(
        "--api",
        metavar="URL",
        default=None,
        help=f"API base URL (default: WATCHER_API_URL or {DEFAULT_API_URL})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all watched markets")

    add_p = sub.add_parser("add", help="Add a watched market")
    add_p.add_argument("condition_id", help="Condition ID (e.g. 0x...)")
    add_p.add_argument("token_id_yes", help="Token ID for YES outcome")
    add_p.add_argument("--slug", default=None, help="Optional slug label")

    remove_p = sub.add_parser("remove", help="Remove a watched market")
    remove_p.add_argument("condition_id", help="Condition ID to remove")

    update_p = sub.add_parser("update", help="Update a watched market (e.g. slug)")
    update_p.add_argument("condition_id", help="Condition ID to update")
    update_p.add_argument("--slug", default=None, help="New slug")

    summary_p = sub.add_parser("summary", help="Get summary for a market")
    summary_p.add_argument("condition_id", help="Condition ID")

    args = parser.parse_args()
    base_url = _get_base_url(args.api)

    try:
        if args.command == "list":
            return _cmd_list(base_url)
        if args.command == "add":
            return _cmd_add(
                base_url,
                args.condition_id,
                args.token_id_yes,
                getattr(args, "slug", None),
            )
        if args.command == "remove":
            return _cmd_remove(base_url, args.condition_id)
        if args.command == "update":
            return _cmd_update(
                base_url,
                args.condition_id,
                getattr(args, "slug", None),
            )
        if args.command == "summary":
            return _cmd_summary(base_url, args.condition_id)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}", file=sys.stderr)
        if e.response.text:
            print(e.response.text, file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request error: {e}", file=sys.stderr)
        return 1
    return 0
