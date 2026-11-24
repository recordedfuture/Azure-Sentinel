"""Offline tests for ccf_paging_sim.py against a fake BFI export endpoint (http.server)."""

import base64
import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import ccf_paging_sim as sim  # noqa: E402

CFG = sim.load_config()
T0 = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
W = CFG.window


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def rec(i, dt, **kw):
    return {"id": f"task:{i}", "updated_date": iso(dt), "category": "dark_web", **kw}


class FakeBFI:
    """Keyset-paged export: inclusive [from, until], ordered by (updated_date, id)."""

    def __init__(self, records, drop_next=False, on_page=None):
        self.records, self.drop_next, self.on_page, self.calls = (
            records,
            drop_next,
            on_page,
            [],
        )
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                status, body = fake.handle(self)
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/gw/azure-test"

    def handle(self, req):
        url = urlparse(req.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.calls.append(q)
        if req.headers.get("X-RFToken") != "tok":
            return 401, {"message": "bad token"}
        if not url.path.endswith(CFG.path):
            return 404, {"message": "not found"}
        limit = int(q.get("limit", 0))
        if not 1 <= limit <= 100:
            return 400, {"message": "limit must be 1..100"}
        lo = sim.parse_ts(q[CFG.start_name])
        hi = sim.parse_ts(q[CFG.end_name])
        rows = sorted(
            (r for r in self.records if lo <= sim.parse_ts(r["updated_date"]) <= hi),
            key=lambda r: (sim.parse_ts(r["updated_date"]), r["id"]),
        )
        for name, fld in sim.FILTER_FIELD.items():
            if q.get(name):
                rows = [r for r in rows if r.get(fld) in q[name].split(",")]
        if tok := q.get(CFG.next_param):
            try:
                ts, rid = json.loads(base64.urlsafe_b64decode(tok))
            except ValueError:
                return 400, {"message": "bad next"}
            rows = [
                r
                for r in rows
                if (sim.parse_ts(r["updated_date"]), r["id"]) > (sim.parse_ts(ts), rid)
            ]
        page = rows[:limit]
        body = {CFG.events_path: page}
        if len(page) == limit and not self.drop_next:
            last = page[-1]
            body[CFG.next_path] = base64.urlsafe_b64encode(
                json.dumps([last["updated_date"], last["id"]]).encode()
            ).decode()
        if self.on_page:
            self.on_page(self, len(self.calls))
        return 200, body


@pytest.fixture
def make():
    servers = []

    def _make(records, **kw):
        fake = FakeBFI(records, **kw)
        servers.append(fake)
        return fake, sim.Client(fake.url, "tok", CFG, timeout=5)

    yield _make
    for s in servers:
        s.server.shutdown()


def run(client, limit, start=T0, end=T0 + 2 * W):
    polled = sim.poll_range(client, start, end, W, limit, {})
    ref = sim.poll_range(client, start, end, sim.REFERENCE_WINDOW, 100, {})
    return sim.analyse(polled, ref, limit)


def test_config_is_read_from_poller_json():
    assert CFG.path == "/playbook-alert/export"
    assert (CFG.start_name, CFG.end_name, CFG.next_param) == (
        "updated_from",
        "updated_until",
        "next",
    )
    assert CFG.time_format == "%Y-%m-%dT%H:%M:%SZ" and CFG.window == timedelta(
        minutes=5
    )
    assert set(CFG.filter_names) == {"categories", "priorities", "statuses"}
    assert "High" in CFG.filter_values["priorities"]


def test_full_page_then_empty_page_and_params_on_every_page(make):
    fake, client = make([rec(i, T0 + timedelta(seconds=10 + i)) for i in range(4)])
    win = sim.poll_window(client, T0, T0 + W, 2, {"categories": "dark_web"})
    assert [len(p.records) for p in win.pages] == [2, 2, 0]
    assert all(c["limit"] == "2" and c["categories"] == "dark_web" for c in fake.calls)
    rep = sim.analyse([win], None, 2)
    assert rep["full_then_empty"] and not rep["failures"]


def test_ties_at_same_ms_across_pages(make):
    ts = T0 + timedelta(seconds=30, milliseconds=123)
    _, client = make([rec(i, ts) for i in range(3)])
    rep = run(client, 2)
    assert rep["total"] == 3 and not rep["missing"] and not rep["dup_within"]
    assert rep["ms_split"] and rep["ms_split"][0][2] == [iso(ts)]


def test_record_updated_during_paging_moves_later(make):
    records = [rec(i, T0 + timedelta(seconds=10 + i)) for i in range(4)]

    def bump(fake, call_no):
        if call_no == 1:  # after page 1 of window 1, task:0 is updated into window 2
            fake.records[0] = rec(0, T0 + W + timedelta(seconds=30))

    _, client = make(records, on_page=bump)
    rep = run(client, 2)
    assert not rep["missing"] and not rep["failures"]
    assert rep["extra"] == [
        ("task:0", iso(T0 + timedelta(seconds=10)))
    ]  # the stale version


def test_window_boundary_record(make):
    _, client = make([rec(1, T0 + W)])  # exactly on the boundary second
    rep = run(client, 25)
    assert rep["dup_across"] == [("task:1", iso(T0 + W))]  # inclusive on both ends
    assert len(rep["on_boundary"][("task:1", iso(T0 + W))]) == 2
    assert not rep["failures"]  # duplicates across windows are reported, not fatal


def test_stops_on_missing_next_and_reports_missing(make):
    fake, client = make(
        [rec(i, T0 + timedelta(seconds=10 + i)) for i in range(3)], drop_next=True
    )
    win = sim.poll_window(client, T0, T0 + W, 2, {})
    assert len(win.pages) == 1 and len(fake.calls) == 1
    rep = run(client, 2)
    assert rep["missing"] == [("task:2", iso(T0 + timedelta(seconds=12)))]
    assert rep["failures"]


def test_http_errors_are_reported(make):
    _, client = make([])
    rep = sim.analyse(sim.poll_range(client, T0, T0 + W, W, 0, {}), None, 0)
    assert rep["http_errors"] == [(400, "limit must be 1..100")] and rep["failures"]


def test_bad_params_mode(make):
    _, client = make([])
    assert sim.run_bad_params(client, T0) == [
        "unknown status: expected 400/401, got 200"
    ]


def test_filters_matrix_mode(make):
    _, client = make(
        [
            rec(1, T0 - timedelta(minutes=10)),
            rec(2, T0 - timedelta(minutes=5), category="dark_web"),
        ]
    )
    problems = sim.run_filters_matrix(client, T0)
    assert problems == []


def test_missing_token_fails_gracefully(monkeypatch, capsys):
    monkeypatch.delenv("RF_TOKEN", raising=False)
    assert sim.main(["--base-url", "http://127.0.0.1:9", "--hours", "1"]) == 2
    assert "RF_TOKEN" in capsys.readouterr().err
