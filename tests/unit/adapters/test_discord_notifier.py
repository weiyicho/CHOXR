from __future__ import annotations

from dataclasses import dataclass

import requests

from adapters.discord_notifier import DiscordNotifier


@dataclass
class FakeResponse:
    status_code: int


class FakeSession:
    def __init__(
        self,
        *,
        status_code: int = 204,
        error: requests.RequestException | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        if self.error is not None:
            raise self.error
        self.calls.append((url, kwargs))
        return FakeResponse(self.status_code)


def test_disabled_notifier_does_not_send() -> None:
    session = FakeSession()
    notifier = DiscordNotifier("", session=session)

    assert notifier.enabled is False
    assert notifier.send_message("not sent") is False
    assert session.calls == []


def test_send_message_posts_expected_payload() -> None:
    session = FakeSession()
    notifier = DiscordNotifier(
        "https://discord.com/api/webhooks/example/token",
        session=session,
    )

    assert notifier.send_message("engine started") is True

    url, kwargs = session.calls[0]
    assert url.endswith("/example/token")
    assert kwargs["json"] == {
        "content": "engine started",
        "username": "CHOXR Trading Engine",
    }
    assert kwargs["timeout"] == 5.0


def test_send_embed_posts_fields_and_utc_timestamp() -> None:
    session = FakeSession()
    notifier = DiscordNotifier(
        "https://discord.com/api/webhooks/example/token",
        session=session,
    )

    assert notifier.send_embed(
        "Order filled",
        description="ETHUSDT",
        color=0x123456,
        fields=[{"name": "quantity", "value": "0.10", "inline": True}],
    )

    payload = session.calls[0][1]["json"]
    assert isinstance(payload, dict)
    embed = payload["embeds"][0]
    assert embed["title"] == "Order filled"
    assert embed["fields"][0]["value"] == "0.10"
    assert embed["timestamp"].endswith("+00:00")


def test_request_failure_returns_false() -> None:
    session = FakeSession(error=requests.Timeout("timed out"))
    notifier = DiscordNotifier(
        "https://discord.com/api/webhooks/example/token",
        session=session,
    )

    assert notifier.send_message("engine started") is False
