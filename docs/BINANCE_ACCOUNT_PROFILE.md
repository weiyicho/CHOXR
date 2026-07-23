# Binance Account Profile

## Verified account mode

```text
CLASSIC_PORTFOLIO_MARGIN
```

Recommended local configuration:

```env
BINANCE_ACCOUNT_MODE=CLASSIC_PORTFOLIO_MARGIN
```

## Verification evidence

Verified again on 2026-07-21 with signed, read-only requests:

```text
GET /sapi/v1/portfolio/account
accountType = PM_2
GET /papi/v1/account = success, accountStatus NORMAL
GET /papi/v1/balance = success
GET /papi/v1/um/positionRisk = success
GET /papi/v1/um/positionSide/dual = success, ONE_WAY
```

Binance defines the values as:

```text
PM_1 = Portfolio Margin Pro
PM_2 = Classic Portfolio Margin
PM_3 = Portfolio Margin Pro SPAN
```

The account is therefore Classic Portfolio Margin, not Portfolio Margin Pro.

An HTTP 200 response from `/sapi/v1/portfolio/account` alone is not sufficient
to identify PM Pro. The `accountType` field is the authoritative discriminator.

## Required API routing

| Capability | Route family |
|---|---|
| Margin asset leg | `/papi/v1/margin/*` |
| USD-M perpetual leg | `/papi/v1/um/*` |
| Account information | `GET /papi/v1/account` |
| Account balances | `GET /papi/v1/balance` |
| Futures fund collection | `POST /papi/v1/auto-collection` |

Do not route this account's fund collection through the Portfolio Margin Pro
endpoint `/sapi/v1/portfolio/auto-collection`.

## Fund collection policy

The legacy method is located at:

```text
legacy/binance_sdk_v1/binance_sdk.py::auto_allocation
```

Its endpoint is correct for this account, but its name and docstring are wrong.
The operation is Binance `Fund Auto-collection`: it collects Futures assets
into the Classic Portfolio Margin pool.

The account UI currently has **Auto Aggregate Balances enabled**. That is the
normal collection path, so CHOXR must not call this endpoint after every order,
funding settlement, reconciliation, or process startup. The adapter retains
`collect_futures_funds()` as a manual operational fallback only. The app guard
requires both `CHOXR_LIVE_TRADING=true` and
`confirmed_manual_recovery=True` before it delegates the command.

## Safety notes

- This profile contains no API key, secret, balance, position, or equity data.
- The verification used read-only endpoints only.
- No order, transfer, borrow, repay, or fund-collection operation was executed
  during account-mode verification or this refactor.
- Never infer account mode by automatically falling back across FAPI, PAPI,
  and SAPI after a trading request fails.

## Official reference

[Binance Portfolio Margin account type field](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin-pro/api/rest-api/account)
