# Binance API Contract Audit

Audit date: 2026-07-21

This audit covers the Classic Portfolio Margin account plane used by CHOXR,
the public Spot and USD-M market-data dependencies, request signing, and the
read-only account preflight.  The supplied legacy documentation was treated as
historical context and cross-checked against Binance's current developer
catalog and official Python connector.

## Audited official sources

- [Current Spot REST API](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Current Binance API catalog](https://developers.binance.com/en/docs/catalog)
- [Portfolio Margin REST API catalog](https://developers.binance.com/en/docs/catalog/advanced-trading-derivatives-trading-portfolio-margin/api/rest-api)
- [Portfolio Margin general information](https://developers.binance.com/en/docs/products/derivatives-trading-portfolio-margin/general-info)
- [Portfolio Margin user data streams](https://developers.binance.com/en/docs/products/derivatives-trading-portfolio-margin/user-data-streams)
- [Official Binance Python connector](https://github.com/binance/binance-connector-python)
- [Legacy Spot API documentation](https://developers.binance.com/legacy-docs/binance-spot-api-docs)
- [Legacy Spot changelog](https://developers.binance.com/legacy-docs/binance-spot-api-docs/CHANGELOG)
- [Legacy Margin introduction](https://developers.binance.com/legacy-docs/margin_trading/Introduction)
- [Legacy USD-M general information](https://developers.binance.com/legacy-docs/derivatives/usds-margined-futures/general-info)

The official connector snapshot used for the line-by-line comparison was
commit `15c2bfcbb9e9654d7186680a0dd32287a3285e11`, dated 2026-07-15.

## Confirmed routing

| Capability | Base URL and route |
|---|---|
| Spot public data | `https://api.binance.com/api/v3/*` |
| USD-M public data and server time | `https://fapi.binance.com/fapi/v1/*` |
| Classic Portfolio Margin account | `https://papi.binance.com/papi/v1/account` |
| Classic Portfolio Margin balance | `https://papi.binance.com/papi/v1/balance` |
| Classic Portfolio Margin Margin orders | `https://papi.binance.com/papi/v1/margin/*` |
| Classic Portfolio Margin UM orders | `https://papi.binance.com/papi/v1/um/*` |
| Portfolio account-type discriminator | `https://api.binance.com/sapi/v1/portfolio/account` |
| Portfolio Margin user stream | `wss://fstream.binance.com/pm/ws/<listenKey>` with `/papi/v1/listenKey` |

PAPI has no server-time resource.  The shared signed-request clock is therefore
synchronized from the public USD-M `GET /fapi/v1/time` resource.

## Confirmed request behavior

- Signed parameters are cleaned, URL-encoded, and only then signed with HMAC
  SHA-256.  This satisfies the Spot signing change effective 2026-01-15.
- Signed requests include `timestamp` and a bounded `recvWindow`.
- Timestamp error `-1021` owns one clock-resynchronization retry on the SAPI,
  FAPI, and PAPI clients, all backed by the same server clock.
- Side-effect network timeouts, `-1006`, `-1007`, and the documented 503
  `Unknown error, please check...` response become an unknown execution
  outcome; CHOXR does not blindly resubmit an order.
- The documented 503 `Service Unavailable`, `Internal error`, and `-1008`
  variants are definite retryable failures.  The transport classifies them but
  never retries a side-effect request itself.
- HTTP 429 and 418 are typed separately, and response rate-limit headers are
  captured.
- PAPI listen-key lifecycle calls require the API key but are not signed.
- UM post-only limit orders use `timeInForce=GTX`.
- The Margin spot leg defaults to `sideEffectType=NO_SIDE_EFFECT`, so the
  adapter does not silently borrow or repay.

## Contract corrections made during this audit

- Normalize the asset-filtered `/papi/v1/balance` object response into the
  adapter's list contract.
- Preserve funding-income `tranId` as a string.
- Accept `cumQty` in the current UM new-order response and tolerate the removed
  `avgPrice` and `cumQuote` fields.
- Stop reading a non-existent account-level unrealized-PnL field from
  `/papi/v1/account`.
- Parse and propagate `MARKET_LOT_SIZE` independently from `LOT_SIZE`.
- Parse `NOTIONAL.maxNotional`.
- Propagate symbol status and fail closed when it is not `TRADING`, including
  current statuses such as `CANCEL_ONLY`.
- Accept the documented Spot order-book depth range `1..5000` rather than the
  USD-M endpoint's discrete limit set.
- Add the actual Portfolio Margin WebSocket producer at
  `/pm/ws/<listenKey>`, a 45-minute keepalive, 24-hour connection rotation,
  bounded reconnect backoff, and listen-key expiry recovery.  Non-order
  account events are excluded from the engine order queue.

## Live read-only verification

The command below loads credentials from the process environment and performs
GET requests only.  It never submits or cancels an order, transfers assets,
borrows, repays, or triggers fund collection.

```bash
python3 -m app.binance_account_preflight
```

Verified result on 2026-07-21:

```text
accountType: PM_2
observed mode: CLASSIC_PORTFOLIO_MARGIN
account status: NORMAL
position mode: ONE_WAY
account equity field present: true
available balance field present: true
balance records: 2 (1 non-zero)
UM position records: 0 (0 open)
financial values: redacted
```

Repository verification after the contract corrections:

```text
99 tests passed
compileall passed
git diff --check passed
```
