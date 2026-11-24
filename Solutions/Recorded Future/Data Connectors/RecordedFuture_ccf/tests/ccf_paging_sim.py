#!/usr/bin/env python3
"""Simulate how the CCF RestApiPoller pages through the Recorded Future export endpoint.

All request settings (endpoint path, time format, window size, parameter names, paging and
events paths, filter values) are read from the connector's JSON files next to this folder.
Only read-only GET calls are made. Python 3.11+, stdlib only. See README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLLER = HERE.parent / "RecordedFuture_PollerConfig.json"
DEFINITION = HERE.parent / "RecordedFuture_ConnectorDefinition.json"
FILTERS = ("categories", "priorities", "statuses")
FILTER_FIELD = {
    "categories": "category",
    "priorities": "priority",
    "statuses": "status",
}
REFERENCE_WINDOW = timedelta(hours=6)
REFERENCE_LIMIT = 100


@dataclass
class Config:
    path: str
    time_format: str  # strftime format
    window: timedelta
    start_name: str
    end_name: str
    limit: int
    filter_names: list[str]
    next_path: str
    next_param: str
    events_path: str
    filter_values: dict[str, list[str]] = field(default_factory=dict)


def _jsonpath(path: str) -> list[str]:
    # The poller only uses simple paths like "$.data" and "$.next".
    return [p for p in path.removeprefix("$").split(".") if p]


def _get(obj, path: list[str]):
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _dotnet_to_strftime(fmt: str) -> str:
    table = {"yyyy": "%Y", "MM": "%m", "dd": "%d", "HH": "%H", "mm": "%M", "ss": "%S"}
    return re.sub("|".join(table), lambda m: table[m.group(0)], fmt)


def _dropdown_keys(node, name: str) -> list[str] | None:
    if isinstance(node, dict):
        if node.get("name") == name:
            return re.findall(r'"key": "([^"]+)"', json.dumps(node))
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            if (found := _dropdown_keys(child, name)) is not None:
                return found
    return None


def load_config(poller: Path = POLLER, definition: Path = DEFINITION) -> Config:
    props = json.loads(poller.read_text())[0]["properties"]
    req, paging = props["request"], props["paging"]
    path = urllib.parse.urlparse(req["apiEndpoint"]).path
    path = re.sub(r"^/gw/[^/]+", "", path)  # --base-url already carries /gw/<name>
    qp = req.get("queryParameters", {})
    cfg = Config(
        path=path,
        time_format=_dotnet_to_strftime(req["queryTimeFormat"]),
        window=timedelta(minutes=req["queryWindowInMin"]),
        start_name=req["startTimeAttributeName"],
        end_name=req["endTimeAttributeName"],
        limit=int(qp.get("limit", 100)),
        filter_names=[k for k in qp if k != "limit"],
        next_path=_jsonpath(paging["nextPageTokenJsonPath"])[0],
        next_param=paging["nextPageParaName"],
        events_path=_jsonpath(props["response"]["eventsJsonPaths"][0])[0],
    )
    if definition.exists():
        doc = json.loads(definition.read_text())
        cfg.filter_values = {n: _dropdown_keys(doc, n) or [] for n in cfg.filter_names}
    return cfg


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class Page:
    status: int
    records: list[dict]
    next: str | None
    latency: float
    message: str = ""


class Client:
    def __init__(self, base_url: str, token: str, cfg: Config, timeout: float = 120):
        self.url = base_url.rstrip("/") + cfg.path
        self.token, self.cfg, self.timeout = token, cfg, timeout

    def with_token(self, token: str) -> Client:
        other = Client("", token, self.cfg, self.timeout)
        other.url = self.url
        return other

    def get(self, params: dict) -> Page:
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        req = urllib.request.Request(
            f"{self.url}?{query}",
            headers={"X-RFToken": self.token, "Accept": "application/json"},
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        latency = time.monotonic() - t0
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {"message": raw[:200].decode(errors="replace")}
        if status != 200:
            msg = body.get("message") or body.get("error") or str(body)[:200]
            return Page(status, [], None, latency, str(msg))
        return Page(
            status,
            body.get(self.cfg.events_path) or [],
            body.get(self.cfg.next_path) or None,
            latency,
        )


@dataclass
class Window:
    start: datetime
    end: datetime
    pages: list[Page] = field(default_factory=list)

    @property
    def records(self) -> list[dict]:
        return [r for p in self.pages for r in p.records]


def windows(start: datetime, end: datetime, size: timedelta):
    while start < end:
        yield start, min(start + size, end)
        start += size


def poll_window(client: Client, start, end, limit: int, filters: dict) -> Window:
    """Page 1, then follow next until absent, sending limit and filters on every page."""
    cfg, win = client.cfg, Window(start, end)
    base = {
        cfg.start_name: start.strftime(cfg.time_format),
        cfg.end_name: end.strftime(cfg.time_format),
        "limit": limit,
        **{k: v for k, v in filters.items() if v},
    }
    token = None
    while True:
        page = client.get({**base, cfg.next_param: token})
        win.pages.append(page)
        if page.status != 200 or not page.next:
            return win
        token = page.next


def poll_range(client, start, end, size, limit, filters) -> list[Window]:
    return [
        poll_window(client, s, e, limit, filters) for s, e in windows(start, end, size)
    ]


def key(rec: dict) -> tuple[str, str]:
    return (str(rec.get("id")), str(rec.get("updated_date")))


def analyse(polled: list[Window], reference: list[Window] | None, limit: int) -> dict:
    """Return a report dict; report["failures"] lists the reasons to exit non-zero."""
    all_keys = [key(r) for w in polled for r in w.records]
    counts = Counter(all_keys)
    rep: dict = {"total": len(all_keys), "failures": []}
    rep["dup_across"] = sorted(k for k, n in counts.items() if n > 1)
    rep["dup_within"] = {}
    rep["outside"], rep["full_then_empty"], rep["ms_split"] = [], [], []
    bounds = {w.start.replace(microsecond=0) for w in polled} | {w.end for w in polled}
    on_boundary: dict = defaultdict(list)
    for w in polled:
        wid = f"{w.start:%Y-%m-%dT%H:%M:%SZ}..{w.end:%H:%M:%SZ}"
        dups = [k for k, n in Counter(key(r) for r in w.records).items() if n > 1]
        if dups:
            rep["dup_within"][wid] = dups
        for r in w.records:
            ts = parse_ts(r["updated_date"])
            if ts < w.start or ts > w.end:
                rep["outside"].append((wid, key(r)))
            if ts.replace(microsecond=0) in bounds:
                on_boundary[key(r)].append(wid)
        for i, (a, b) in enumerate(zip(w.pages, w.pages[1:]), start=1):
            if len(a.records) == limit and not b.records and b.status == 200:
                rep["full_then_empty"].append((wid, i))
            shared = {r["updated_date"] for r in a.records} & {
                r["updated_date"] for r in b.records
            }
            if shared:
                rep["ms_split"].append((wid, i, sorted(shared)))
    rep["on_boundary"] = dict(on_boundary)
    pages = [p for w in polled for p in w.pages]
    lat = [p.latency for p in pages] or [0.0]
    rep["pages"], rep["max_latency"], rep["avg_latency"] = (
        len(pages),
        max(lat),
        sum(lat) / len(lat),
    )
    rep["http_errors"] = [(p.status, p.message) for p in pages if p.status != 200]
    if reference is not None:
        rep["http_errors"] += [
            (p.status, p.message) for w in reference for p in w.pages if p.status != 200
        ]
        ref = {key(r) for w in reference for r in w.records}
        rep["missing"] = sorted(ref - set(all_keys))
        rep["extra"] = sorted(set(all_keys) - ref)
        if rep["missing"]:
            rep["failures"].append(
                f"{len(rep['missing'])} records in reference but not polled"
            )
    if rep["dup_within"]:
        rep["failures"].append("duplicates within a window")
    if rep["http_errors"]:
        rep["failures"].append(f"{len(rep['http_errors'])} HTTP errors")
    return rep


def print_report(rep: dict) -> None:
    print(f"total records polled: {rep['total']} in {rep['pages']} pages")
    print(f"page latency: max {rep['max_latency']:.2f}s avg {rep['avg_latency']:.2f}s")
    sections = [
        ("duplicates across windows (boundary, not a failure)", rep["dup_across"]),
        ("duplicates within a window", list(rep["dup_within"].items())),
        ("in reference but not polled", rep.get("missing", [])),
        ("polled but not in reference", rep.get("extra", [])),
        ("updated_date outside its window", rep["outside"]),
        (
            "updated_date on a window boundary second -> windows",
            list(rep["on_boundary"].items()),
        ),
        ("full page followed by an empty page (window, page)", rep["full_then_empty"]),
        ("same-ms group split across pages (window, page, ts)", rep["ms_split"]),
        ("HTTP errors", rep["http_errors"]),
    ]
    for title, items in sections:
        print(f"{title}: {len(items)}")
        for item in items[:20]:
            print(f"  {item}")
    print("FAIL: " + "; ".join(rep["failures"]) if rep["failures"] else "OK")


def run_filters_matrix(client: Client, end: datetime) -> list[str]:
    cfg, problems = client.cfg, []
    start = end - timedelta(hours=1)
    cases = [{}] + [
        {n: v} for n in cfg.filter_names for v in cfg.filter_values.get(n, [])
    ]
    for case in cases:
        win = poll_window(client, start, end, cfg.limit, case)
        for p in win.pages:
            if p.status != 200:
                problems.append(f"{case or 'no filters'}: HTTP {p.status} {p.message}")
        for name, value in case.items():
            fld = FILTER_FIELD.get(name, name)
            bad = [r.get("id") for r in win.records if str(r.get(fld)) != value]
            if bad:
                problems.append(
                    f"{name}={value}: {len(bad)} records with other {fld}, e.g. {bad[:3]}"
                )
        print(
            f"{case or 'no filters'}: {len(win.records)} records, {len(win.pages)} pages"
        )
    return problems


def run_bad_params(client: Client, end: datetime) -> list[str]:
    cfg = client.cfg
    base = {
        cfg.start_name: (end - timedelta(hours=1)).strftime(cfg.time_format),
        cfg.end_name: end.strftime(cfg.time_format),
        "limit": cfg.limit,
    }
    cases = {
        "limit=0": ({**base, "limit": 0}, client),
        "limit=101": ({**base, "limit": 101}, client),
        "unknown status": ({**base, "statuses": "NoSuchStatus"}, client),
        "malformed next": ({**base, cfg.next_param: "not-a-valid-token"}, client),
        "bad token": (base, client.with_token("invalid-token")),
    }
    problems = []
    for name, (params, c) in cases.items():
        page = c.get(params)
        ok = page.status in (400, 401)
        print(f"{name}: HTTP {page.status} {page.message}")
        if not ok:
            problems.append(f"{name}: expected 400/401, got {page.status}")
    return problems


def _utc(value: str) -> datetime:
    dt = parse_ts(value)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--base-url", required=True, help="e.g. https://<host>/gw/azure-dev"
    )
    ap.add_argument("--start", type=_utc, help="ISO time, UTC if no offset")
    ap.add_argument("--end", type=_utc, help="ISO time, default now")
    ap.add_argument(
        "--hours", type=float, help="poll the last N hours (instead of --start)"
    )
    for name in cfg.filter_names:
        ap.add_argument(f"--{name}", default="", help="comma separated")
    ap.add_argument("--limit", type=int, default=cfg.limit)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--filters-matrix", action="store_true")
    mode.add_argument("--bad-params", action="store_true")
    args = ap.parse_args(argv)

    token = os.environ.get("RF_TOKEN")
    if not token:
        print("error: set the RF_TOKEN environment variable", file=sys.stderr)
        return 2
    client = Client(args.base_url, token, cfg)
    end = args.end or datetime.now(UTC).replace(microsecond=0)
    if args.filters_matrix or args.bad_params:
        run = run_filters_matrix if args.filters_matrix else run_bad_params
        problems = run(client, end)
        print("FAIL:\n  " + "\n  ".join(problems) if problems else "OK")
        return 1 if problems else 0
    if args.start:
        start = args.start
    elif args.hours:
        start = end - timedelta(hours=args.hours)
    else:
        ap.error("give --start or --hours")
    filters = {n: getattr(args, n) for n in cfg.filter_names}
    polled = poll_range(client, start, end, cfg.window, args.limit, filters)
    reference = poll_range(
        client, start, end, REFERENCE_WINDOW, REFERENCE_LIMIT, filters
    )
    rep = analyse(polled, reference, args.limit)
    print_report(rep)
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
