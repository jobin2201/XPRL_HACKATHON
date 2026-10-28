"""Shared helpers for reading public XRPL Mainnet data (no wallet, secret or XRP needed).

- polite JSON-RPC client: server failover, retries with backoff, a minimum gap between requests
- on-disk cache for ledgers so a fixed ledger range is only downloaded once
- amount / currency parsing for API v2 responses (tx_json + meta, DeliverMax, delivered_amount)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from xrpl.clients import JsonRpcClient
from xrpl.models.currencies import XRP, IssuedCurrency
from xrpl.models.requests import BookOffers, Ledger, ServerInfo

try:  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]
MAINNET_RAW = ROOT / "data" / "raw" / "mainnet"
MAINNET_PROCESSED = ROOT / "data" / "processed" / "mainnet"
CACHE = MAINNET_RAW / "cache"

SERVERS = ["https://s1.ripple.com:51234/", "https://s2.ripple.com:51234/", "https://xrplcluster.com/"]
MIN_GAP_S = 0.25  # public servers are shared: at most ~4 requests per second from us
RIPPLE_EPOCH = 946684800  # seconds between 1970-01-01 and 2000-01-01

# Issuers whose USD tokens we trust as ~1 USD. Anyone can issue a token called "USD", so others stay unpriced.
USD_ISSUERS = {
    "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De": "RLUSD",  # Ripple USD
    "rvYAfWj5gh67oV6fW32ZzP3Aw4Eubs59B": "USD",  # Bitstamp
    "rhub8VRN55s94qWKDv6jmDy1pUykJzF3wq": "USD",  # GateHub
}
RLUSD_HEX = "524C555344000000000000000000000000000000"


class Xrpl:
    def __init__(self, servers=SERVERS, min_gap=MIN_GAP_S, retries=4):
        self.servers = list(servers)
        self.min_gap = min_gap
        self.retries = retries
        self._last = 0.0
        self._i = 0

    def request(self, req):
        err = None
        for attempt in range(self.retries * len(self.servers)):
            wait = self.min_gap - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            url = self.servers[self._i % len(self.servers)]
            try:
                self._last = time.monotonic()
                resp = JsonRpcClient(url).request(req)
                if resp.is_successful():
                    return resp.result
                err = resp.result.get("error", resp.result)
                if err in ("lgrNotFound", "actNotFound", "invalidParams", "actMalformed"):
                    raise RuntimeError(f"{url}: {err}")
                # slowDown / tooBusy / noCurrent etc: back off, then try the next server
            except RuntimeError:
                raise
            except Exception as e:  # network errors
                err = f"{type(e).__name__}: {e}"
            self._i += 1
            time.sleep(min(8, 0.5 * 2 ** (attempt // len(self.servers))))
        raise RuntimeError(f"XRPL request failed after retries: {err}")

    # ------------------------------------------------------------------ helpers
    def server_info(self):
        return self.request(ServerInfo())["info"]

    def validated_index(self) -> int:
        return int(self.server_info()["validated_ledger"]["seq"])

    def ledger(self, index: int | str = "validated", use_cache=True) -> dict:
        """Full ledger with expanded transactions + metadata, cached to disk by index."""
        if use_cache and isinstance(index, int):
            f = CACHE / f"ledger_{index}.json"
            if f.exists():
                return json.loads(f.read_text())
        led = self.request(Ledger(ledger_index=index, transactions=True, expand=True))["ledger"]
        if use_cache and led.get("closed", True):
            CACHE.mkdir(parents=True, exist_ok=True)
            (CACHE / f"ledger_{int(led['ledger_index'])}.json").write_text(json.dumps(led))
        return led

    def xrp_usd(self) -> float | None:
        """Mid price of XRP in RLUSD from the on-ledger order book (RLUSD ~ 1 USD)."""
        rl = IssuedCurrency(currency=RLUSD_HEX, issuer="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De")
        try:
            ask = self.request(BookOffers(taker_gets=XRP(), taker_pays=rl, limit=5)).get("offers", [])
            bid = self.request(BookOffers(taker_gets=rl, taker_pays=XRP(), limit=5)).get("offers", [])
        except RuntimeError:
            return None
        prices = []
        if ask:  # seller gives XRP (drops), wants RLUSD: quality = RLUSD per drop
            prices.append(float(ask[0]["quality"]) * 1e6)
        if bid:  # seller gives RLUSD, wants XRP: quality = drops per RLUSD
            q = float(bid[0]["quality"])
            if q > 0:
                prices.append(1e6 / q)
        return sum(prices) / len(prices) if prices else None


# ---------------------------------------------------------------------- parsing
def tx_parts(entry: dict) -> tuple[dict, dict, str]:
    """(tx_json, meta, hash) for API v2 entries, with a v1 fallback."""
    tx = entry.get("tx_json", entry)
    meta = entry.get("meta") or entry.get("metaData") or {}
    return tx, meta, entry.get("hash") or tx.get("hash", "")


def decode_currency(code: str) -> str:
    """40-hex currency codes -> ASCII where printable (e.g. RLUSD); 3-letter codes unchanged."""
    if len(code) == 40:
        try:
            s = bytes.fromhex(code).rstrip(b"\x00").decode("ascii")
            if s.isprintable() and s:
                return s
        except ValueError:
            pass
        return code[:8] + "…"
    return code


def parse_amount(a) -> tuple[float, str, str | None]:
    """(value, currency, issuer). XRP comes as a drops string; tokens as {currency, issuer, value}; MPTs as {mpt_issuance_id, value}."""
    if a is None or a == "unavailable":
        return 0.0, "", None
    if isinstance(a, str):
        return int(a) / 1e6, "XRP", None
    if "mpt_issuance_id" in a:
        return float(a.get("value", 0)), "MPT:" + a["mpt_issuance_id"][:8], None
    return float(a.get("value", 0)), decode_currency(a.get("currency", "")), a.get("issuer")


def pipeline_currency(cur: str, issuer: str | None) -> str:
    """Currency label used in the pipeline: priced codes stay plain, other tokens carry their issuer."""
    if cur == "XRP" or not issuer:
        return cur
    if issuer in USD_ISSUERS and cur in ("USD", "RLUSD"):
        return "USD"
    return f"{cur}:{issuer[:8]}"


def delivered(entry: dict):
    """Amount actually delivered by a payment.

    meta.delivered_amount is authoritative (DeliverMax/Amount is only the requested maximum and can be
    partial). A failed transaction (tec*) delivers nothing, so it returns None -> value 0.
    """
    tx, meta, _ = tx_parts(entry)
    if meta.get("TransactionResult") != "tesSUCCESS":
        return None
    return meta.get("delivered_amount", tx.get("DeliverMax", tx.get("Amount")))


def close_time(led_or_entry: dict) -> datetime:
    iso = led_or_entry.get("close_time_iso")
    if iso:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return datetime.fromtimestamp(int(led_or_entry["close_time"]) + RIPPLE_EPOCH, tz=timezone.utc)


def is_address(s: str) -> bool:
    return isinstance(s, str) and s.startswith("r") and 25 <= len(s) <= 35
