"""OpenTripPlanner inputs and client on recorded answers (fixtures/otp, OTP 2.10, 27 Nov 2026)."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from reach_pipeline import otp
from reach_pipeline.config import load_config
from reach_pipeline.errors import ExternalError, StageValidationError

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures" / "otp"
TZ = ZoneInfo("Europe/Berlin")


def _fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["response"]


def test_arrive_by_keeps_the_latest_departure() -> None:
    when = datetime(2026, 12, 1, 8, 10, tzinfo=TZ)
    trip = otp.parse_plan(_fixture("arrive_by_bus"), when, arrive_by=True)
    # three answers: a direct walk from 07:23, buses from 07:48 and 07:46 → the 07:48 one
    assert trip.first_route == "18" and not trip.walk_only
    assert trip.time_s == pytest.approx(21.4 * 60, abs=60)
    parts = trip.access_s + trip.wait_s + trip.in_vehicle_s + trip.egress_s
    assert parts == pytest.approx(trip.time_s, abs=2)


def test_depart_at_counts_the_wait_at_home() -> None:
    when = datetime(2026, 11, 28, 0, 30, tzinfo=TZ)
    trip = otp.parse_plan(_fixture("depart_at_night"), when, arrive_by=False)
    # bus arriving 00:51 beats the walk arriving 01:02; time from 00:30, not from the departure
    assert trip.time_s == pytest.approx(21 * 60, abs=60)
    assert trip.departure is not None and trip.departure >= "00:30"
    assert trip.wait_s >= 0 and trip.transfers == 0


def test_walk_only_and_bike_parking() -> None:
    when = datetime(2026, 12, 1, 18, 0, tzinfo=TZ)
    walk = otp.parse_plan(_fixture("walk_only"), when, arrive_by=False)
    assert walk.walk_only and walk.first_stop is None and walk.time_s < 300
    bike = otp.parse_plan(_fixture("bike_parking"), when, arrive_by=False)
    assert not bike.walk_only and bike.access_s > 0  # cycling to the stop is access


def test_no_itinerary_and_errors() -> None:
    when = datetime(2026, 12, 1, 18, 0, tzinfo=TZ)
    empty = {"data": {"planConnection": {"edges": []}}}
    assert otp.parse_plan(empty, when, arrive_by=False).time_s is None
    with pytest.raises(ExternalError, match="errors"):
        otp.parse_plan({"errors": [{"message": "bad"}]}, when, arrive_by=False)


def test_client_retries_server_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="starting")
        body = json.loads(request.content)
        assert body["variables"]["dt"] == {"latestArrival": "2026-12-01T08:10:00+01:00"}
        return httpx.Response(200, json=_fixture("arrive_by_bus"))

    cfg = load_config(REPO / "config" / "config.yaml").otp.model_copy(update={"backoff_s": 0})

    async def go() -> otp.Trip:
        async with otp.OtpClient(cfg, "http://otp", httpx.MockTransport(handler)) as c:
            return await c.plan(
                (9.0555, 48.5157),
                (9.035, 48.537),
                datetime(2026, 12, 1, 8, 10, tzinfo=TZ),
                True,
                "WALK",
            )

    assert asyncio.run(go()).first_route == "18" and calls["n"] == 2


def test_configs_from_the_routing_profiles() -> None:
    cfg = load_config(REPO / "config" / "config.yaml")
    router = otp.router_config(cfg)["routingDefaults"]
    assert router["walk"]["speed"] == pytest.approx(5.0 / 3.6, abs=1e-3)
    assert router["bicycle"]["speed"] == pytest.approx(15.0 / 3.6, abs=1e-3)
    build = otp.build_config([date(2026, 12, 1), date(2026, 11, 28)])
    assert build["transitServiceStart"] == "2026-11-27"
    assert build["transitServiceEnd"] == "2026-12-02"


def _feed(d: Path) -> Path:
    files = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,parent_station\n"
        "a,A,48.5,9.0,p\nb,B,48.6,9.1,\nc,C,49.0,9.5,\np,P,48.5,9.0,\n",
        "stop_times.txt": "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
        "t1,a,1,08:00:00,08:00:00\nt1,b,2,08:10:00,08:10:00\nt1,c,3,08:40:00,08:40:00\n"
        "t2,a,1,09:00:00,09:00:00\nt2,c,2,09:30:00,09:30:00\n",
        "trips.txt": "route_id,service_id,trip_id\nr1,s1,t1\nr2,s2,t2\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_type\nr1,ag,1,3\nr2,ag,2,3\n",
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nag,A,http://a,Europe/Berlin\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\ns1,1,1,1,1,1,0,0,20261101,20261231\n"
        "s2,1,1,1,1,1,0,0,20261101,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\ns2,20261201,2\n",
        "transfers.txt": "from_stop_id,to_stop_id,transfer_type\na,b,0\na,c,0\n",
        "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang\nX,http://x,de\n",
    }
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def test_clip_gtfs_keeps_trips_with_two_stops(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    src = _feed(tmp_path / "src")
    counts = otp.clip_gtfs(src, tmp_path / "out", ["a", "b"])
    # t2 has only one stop inside → dropped with its route and service; parent p kept
    assert counts["trips"] == 1 and counts["routes"] == 1 and counts["stops"] == 3
    assert counts["stop_times"] == 2 and counts["transfers"] == 1
    assert counts["calendar_dates"] == 0
    with pytest.raises(StageValidationError, match="no trips"):
        otp.clip_gtfs(src, tmp_path / "none", ["c"])
