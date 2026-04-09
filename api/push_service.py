"""
Expo Push Notification service.
Sends push messages to all registered device tokens via Expo's push API.
"""
from __future__ import annotations

import logging
from typing import Any

from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(tokens: List[str], title: str, body: str, data: Optional[Dict] = None) -> dict:
    """
    Send a push notification to a list of Expo push tokens.

    Returns the Expo API response dict (or error info on failure).
    Tokens that are invalid are silently skipped.
    """
    if not tokens:
        return {"ok": True, "sent": 0}

    messages = [
        {
            "to":    token,
            "title": title,
            "body":  body,
            "data":  data or {},
            "sound": "default",
            "priority": "high",
        }
        for token in tokens
        if token and token.startswith("ExponentPushToken[")
    ]

    if not messages:
        return {"ok": True, "sent": 0, "note": "no valid expo tokens"}

    # Expo accepts up to 100 messages per request — chunk if needed
    sent = 0
    for i in range(0, len(messages), 100):
        chunk = messages[i : i + 100]
        try:
            resp = requests.post(
                EXPO_PUSH_URL,
                json=chunk,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            sent += len(chunk)
        except Exception as e:
            logger.warning("Expo push error (chunk %d): %s", i, e)

    return {"ok": True, "sent": sent}
