"""
Optional Chapa payment helpers for Dejaf Tadlu bot.

If CHAPA_SECRET_KEY is not set, initialize_payment raises ChapaError
and the bot falls back to manual / COD confirmation.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CHAPA_SECRET_KEY = os.getenv("CHAPA_SECRET_KEY", "").strip()
CHAPA_BASE = "https://api.chapa.co/v1"


class ChapaError(Exception):
    """Raised when Chapa API is unavailable or returns an error."""


async def initialize_payment(
    amount: float,
    email: str,
    first_name: str,
    last_name: str,
    tx_ref: str,
    callback_url: Optional[str] = None,
    return_url: Optional[str] = None,
) -> str:
    """
    Create a Chapa checkout session and return the checkout URL.
    Requires CHAPA_SECRET_KEY in environment.
    """
    if not CHAPA_SECRET_KEY:
        raise ChapaError("CHAPA_SECRET_KEY is not set")

    payload = {
        "amount": f"{amount:.2f}",
        "currency": "ETB",
        "email": email or "customer@dejaf.local",
        "first_name": first_name or "Customer",
        "last_name": last_name or "Customer",
        "tx_ref": tx_ref,
        "customization": {
            "title": "Dejaf Tadlu",
            "description": "Order payment",
        },
    }
    if callback_url:
        payload["callback_url"] = callback_url
    if return_url:
        payload["return_url"] = return_url

    headers = {
        "Authorization": f"Bearer {CHAPA_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{CHAPA_BASE}/transaction/initialize",
            json=payload,
            headers=headers,
        )

    data = {}
    try:
        data = resp.json()
    except Exception:
        pass

    if resp.status_code >= 400 or data.get("status") != "success":
        msg = data.get("message") if isinstance(data, dict) else resp.text
        logger.error("Chapa initialize failed: %s %s", resp.status_code, msg)
        raise ChapaError(str(msg) or f"HTTP {resp.status_code}")

    checkout_url = (data.get("data") or {}).get("checkout_url")
    if not checkout_url:
        raise ChapaError("No checkout_url in Chapa response")
    return checkout_url


async def verify_payment(tx_ref: str) -> dict:
    """Verify a transaction by tx_ref. Returns Chapa response data dict."""
    if not CHAPA_SECRET_KEY:
        raise ChapaError("CHAPA_SECRET_KEY is not set")

    headers = {"Authorization": f"Bearer {CHAPA_SECRET_KEY}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{CHAPA_BASE}/transaction/verify/{tx_ref}",
            headers=headers,
        )

    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise ChapaError(str(data.get("message") or resp.text))
    return data


def payment_succeeded(verify_response: dict) -> bool:
    """Return True if the verify response indicates a successful payment."""
    if not isinstance(verify_response, dict):
        return False
    status = (verify_response.get("status") or "").lower()
    data = verify_response.get("data") or {}
    tx_status = (data.get("status") or "").lower()
    return status == "success" and tx_status in ("success", "successful")
