# CCF paging simulation (Recorded Future Playbook Alerts)

`ccf_paging_sim.py` walks the export endpoint the way the CCF `RestApiPoller` does, and checks
that nothing is missed or duplicated. Settings like the endpoint path, time format, window size,
parameter names, paging and events paths, and filter values are read from
`../RecordedFuture_PollerConfig.json` and `../RecordedFuture_ConnectorDefinition.json`.

It only makes read-only `GET` calls. Python 3.11+, stdlib only.

## Run

```sh
export RF_TOKEN=...   # sent as X-RFToken, never printed

# Local BFI started with bfi-dt (base URL includes the gateway prefix)
python3 ccf_paging_sim.py --base-url <bfi-dt-host>/gw/azure-dev --hours 24

# Production gateway, a fixed range, filtered
python3 ccf_paging_sim.py --base-url <prod-host>/gw/azure \
    --start 2026-11-23T00:00:00Z --end 2026-11-24T00:00:00Z --priorities High --limit 25

python3 ccf_paging_sim.py --base-url ... --filters-matrix   # 1h per single filter value
python3 ccf_paging_sim.py --base-url ... --bad-params       # expects 400/401
```

The default mode polls `queryWindowInMin` windows (page 1, then `next` until it's absent,
sending `limit` and the filters on every page). It compares them with a reference fetch in 6h
windows with limit 100, and reports duplicates, missing records, records outside or on a window
boundary, full pages followed by an empty page, same-millisecond groups split across pages,
page latency and HTTP errors.

Exit codes: `0` OK, `1` missing records, duplicates within a window or HTTP errors (duplicates
across windows are only reported), `2` usage error (for example `RF_TOKEN` is not set).

## Offline tests

```sh
uv run --with pytest pytest -q -p no:cacheprovider .
```
