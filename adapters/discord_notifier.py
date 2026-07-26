"""Outbound Discord webhook notifications for CHOXR."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import requests


LOGGER = logging.getLogger(__name__)


class DiscordNotifier:
    """Send pre-formatted monitoring messages through a Discord webhook."""

    def __init__(
        self,
        webhook_url: str,
        enabled: bool = True,
        *,
        username: str = "CHOXR Trading Engine",
        timeout_seconds: float = 5.0,
        session: requests.Session | None = None,
    ) -> None:
        self._webhook_url = webhook_url.strip()
        self._enabled = bool(enabled and self._webhook_url)
        self._username = username
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send_message(self, content: str, username: str | None = None) -> bool:
        """Send a plain Discord message without applying business formatting."""

        return self._post_json(
            {
                "content": content,
                "username": username or self._username,
            }
        )

    def send_embed(
        self,
        title: str,
        description: str = "",
        color: int = 0x00FF00,
        fields: Sequence[Mapping[str, object]] | None = None,
        username: str | None = None,
    ) -> bool:
        """Send one Discord embed."""

        embed: dict[str, object] = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if fields:
            embed["fields"] = [dict(field) for field in fields]

        return self._post_json(
            {
                "username": username or self._username,
                "embeds": [embed],
            }
        )

    def send_accounts_summary(self, formatted_content: str) -> bool:
        return self.send_message(formatted_content)

    def send_positions_summary(self, formatted_content: str) -> bool:
        return self.send_message(formatted_content)

    def send_performance_summary(self, formatted_content: str) -> bool:
        return self.send_message(formatted_content)

    def send_picture(
        self,
        picture_path: str | Path,
        username: str | None = None,
    ) -> bool:
        """Upload one image or other monitoring artifact."""

        if not self._enabled:
            return False

        try:
            with Path(picture_path).open("rb") as picture:
                response = self._session.post(
                    self._webhook_url,
                    data={
                        "payload_json": json.dumps(
                            {"username": username or self._username}
                        )
                    },
                    files={"file": picture},
                    timeout=self._timeout_seconds,
                )
        except (OSError, requests.RequestException) as exc:
            LOGGER.warning("Discord picture notification failed: %s", exc)
            return False

        accepted = 200 <= response.status_code < 300
        if not accepted:
            LOGGER.warning(
                "Discord picture notification rejected with HTTP %s",
                response.status_code,
            )
        return accepted

    def _post_json(self, payload: Mapping[str, object]) -> bool:
        if not self._enabled:
            return False

        try:
            response = self._session.post(
                self._webhook_url,
                json=dict(payload),
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            LOGGER.warning("Discord notification failed: %s", exc)
            return False

        accepted = 200 <= response.status_code < 300
        if not accepted:
            LOGGER.warning(
                "Discord notification rejected with HTTP %s",
                response.status_code,
            )
        return accepted
