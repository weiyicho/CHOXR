"""Account-mode discrimination without endpoint fallback guessing."""

from __future__ import annotations

from .config import BinanceAccountMode


ACCOUNT_TYPE_TO_MODE = {
    "PM_1": BinanceAccountMode.PORTFOLIO_MARGIN_PRO,
    "PM_2": BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN,
    "PM_3": BinanceAccountMode.PORTFOLIO_MARGIN_PRO,
}


class AccountModeMismatch(RuntimeError):
    pass


def mode_from_account_type(account_type: str) -> BinanceAccountMode:
    """Map Binance's read-only ``accountType`` discriminator to our mode."""

    try:
        return ACCOUNT_TYPE_TO_MODE[account_type]
    except KeyError as exc:
        raise ValueError(f"unsupported Binance accountType: {account_type!r}") from exc


def verify_account_mode(
    configured: BinanceAccountMode,
    account_profile: dict[str, object],
) -> BinanceAccountMode:
    raw_account_type = account_profile.get("accountType")
    if not isinstance(raw_account_type, str):
        raise ValueError("account profile does not contain accountType")
    observed = mode_from_account_type(raw_account_type)
    if configured is not observed:
        raise AccountModeMismatch(
            f"configured Binance mode is {configured.value}, but accountType "
            f"{raw_account_type} resolves to {observed.value}"
        )
    return observed
