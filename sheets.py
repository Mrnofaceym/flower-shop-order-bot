"""Talks to the Google Sheet through the Apps Script web app."""
import json
import time

import aiohttp

import config

_catalog = {"items": [], "at": 0.0}


class SheetError(Exception):
    pass


async def _request(method, params=None, payload=None):
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        if method == "GET":
            resp = await s.get(config.SHEET_URL, params={**params, "secret": config.SHEET_SECRET})
        else:
            # text/plain avoids a CORS preflight on Google's side; Apps Script reads the raw body
            body = json.dumps({**payload, "secret": config.SHEET_SECRET}, ensure_ascii=False)
            resp = await s.post(config.SHEET_URL, data=body.encode(),
                                headers={"Content-Type": "text/plain; charset=utf-8"})
        async with resp:
            text = await resp.text()
    try:
        data = json.loads(text)
    except ValueError:
        raise SheetError(f"not JSON from Apps Script (HTTP {resp.status})")
    if not data.get("ok"):
        raise SheetError(data.get("error", "unknown error"))
    return data


async def catalog(force=False):
    """Products from the 'Каталог' sheet, cached for a minute."""
    if force or time.time() - _catalog["at"] > config.CATALOG_CACHE_SECONDS or not _catalog["items"]:
        data = await _request("GET", {"action": "catalog"})
        _catalog.update(items=data["items"], at=time.time())
    return _catalog["items"]


async def add_order(order: dict) -> int:
    data = await _request("POST", payload={"order": order})
    return int(data["number"])


async def statuses():
    """[{number, user, status}] for recent orders — used by the status notifier."""
    data = await _request("GET", {"action": "statuses"})
    return data["orders"]


async def user_orders(user_id: int):
    data = await _request("GET", {"action": "orders", "user": str(user_id)})
    return data["orders"]
