"""Fit, areas and reasons on a tiny hand-made model (methodology §6 worked example)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reach_api.fit import ProfileError, cell_summary, fit_response, score, term_results
from reach_api.model import Model

A, P = 1.25, 4


def _model() -> Model:
    cells = pd.DataFrame(
        {
            "cell_id": ["A", "B", "E"],
            "district_id": ["d1", "d1", "d2"],
            "populated": [True, True, False],
            "lon": [9.05, 9.06, 9.07],
            "lat": [48.52, 48.52, 48.52],
        }
    )
    types = pd.DataFrame(
        [
            ("campus_site", "Campus", "Campus", "campus", "morning_lecture", 20, 5, None),
            ("mensa", "Mensa", "Mensa", "campus", "midday", 15, 3, 3),
            ("grocery", "Supermarket", "Supermarkt", "osm", "evening", 10, 2, 3),
            ("sport", "Sport", "Sport", "labels", "evening", 20, 0, None),
            ("nightlife", "Going out", "Ausgehen", "osm", "night_return", 20, 1, 3),
        ],
        columns=[
            "destination_type",
            "label_en",
            "label_de",
            "source",
            "trip_window",
            "fine_time_min",
            "trips_per_week",
            "nearest_k",
        ],
    )
    dests = pd.DataFrame(
        [
            ("campus_site:morgenstelle", "campus_site", "Morgenstelle"),
            ("campus_site:tal", "campus_site", "Tal"),
            ("mensa:m1", "mensa", "Mensa M"),
            ("grocery:n1", "grocery", "Markt 1"),
            ("grocery:edeka:n1", "grocery", "Markt 1"),
            ("sport:tennis:w1", "sport", "TC"),
            ("nightlife:n9", "nightlife", "Bar"),
        ],
        columns=["destination_id", "destination_type", "name"],
    )
    # cell A and B of the worked example (minutes), walk only; transit for nightlife
    t = {
        "A": {
            "campus_site:morgenstelle": 12,
            "campus_site:tal": 30,
            "mensa:m1": 8,
            "grocery:n1": 6,
            "grocery:edeka:n1": 6,
            "sport:tennis:w1": 14,
            "nightlife:n9": 25,
        },
        "B": {
            "campus_site:morgenstelle": 28,
            "campus_site:tal": 10,
            "mensa:m1": 22,
            "grocery:n1": 9,
            "grocery:edeka:n1": 9,
            "sport:tennis:w1": 8,
            "nightlife:n9": 35,
        },
        "E": {"campus_site:morgenstelle": 40, "mensa:m1": 40, "grocery:n1": 40},
    }
    rows = [(c, d, "walk", m * 60, None) for c, ds in t.items() for d, m in ds.items()] + [
        ("A", "nightlife:n9", "transit", 20 * 60, "00:47")
    ]
    times = pd.DataFrame(rows, columns=["cell_id", "destination_id", "mode", "time_s", "departure"])
    return Model.build(
        run_id="R1",
        cells=cells,
        districts=pd.DataFrame({"district_id": ["d1", "d2"], "name": ["West", "Ost"]}),
        types=types,
        labels=pd.DataFrame(
            {
                "destination_type": ["grocery", "sport"],
                "label_kind": ["brand", "category"],
                "label": ["edeka", "tennis"],
                "destinations": [1, 1],
            }
        ),
        label_names={},
        sites=pd.DataFrame(
            {
                "site_id": ["morgenstelle", "tal"],
                "name": ["M", "T"],
                "default_share": [0.5, 0.5],
                "lon": [9.0, 9.1],
                "lat": [48.5, 48.5],
            }
        ),
        programmes=pd.DataFrame(
            {
                "programme": ["biology"],
                "label_en": ["Biology"],
                "label_de": ["Biologie"],
                "sites": [["morgenstelle"]],
            }
        ),
        destinations=dests,
        times=times,
    )


PROFILE = {
    "programme": "biology",
    "modes": ["walk"],
    "destinations": {
        "campus_site": {"importance": 3},
        "mensa": {"importance": 2},
        "grocery": {"importance": 2},
        "sport:tennis": {"importance": 1},
        "nightlife": {"importance": 1},
    },
}


def test_worked_example_of_the_methodology() -> None:
    out = fit_response(_model(), PROFILE, A, P)
    fit_a, weekly_a, pop_a = out["cells"]["A"]
    fit_b, weekly_b, _ = out["cells"]["B"]
    assert (fit_a, fit_b) == (90, 51)  # methodology §6
    assert (weekly_a, weekly_b) == (242, 518)  # tennis never counts
    assert pop_a == 1 and out["cells"]["E"][2] == 0
    (area,) = out["areas"]  # E is not populated: d2 has no area
    assert area["name"] == "West" and area["best_cell_id"] == "A" and area["fit"] == 71


def test_modes_favourites_campus_days_and_reasons() -> None:
    m = _model()
    night = dict(PROFILE, modes=["walk", "transit"])
    s = cell_summary(m, night, "A", A, P)
    rel = [r for r in s["reasons"] if r["kind"] == "reliability"]
    assert rel and rel[0]["value"] == "00:47" and rel[0]["mode"] == "transit"
    assert 2 <= len(s["reasons"]) <= 4
    assert sum(p["share"] for p in s["fit_parts"]) == pytest.approx(1)
    fav = dict(PROFILE, labels={"grocery": ["edeka"]})
    assert fit_response(m, fav, A, P)["cells"]["A"][0] == 90
    days = dict(PROFILE, campus_days={"tal": 1})
    assert fit_response(m, days, A, P)["cells"]["B"][0] > 51  # Tal is 10 min from B
    assert s["targets"]["campus_site"] == ["campus_site:morgenstelle"]


def test_profile_errors_and_score() -> None:
    m = _model()
    for bad in (
        dict(PROFILE, modes=["bike"]),
        dict(PROFILE, destinations={"sport": {"importance": 1}}),  # container, not a term
        dict(PROFILE, destinations={"sport:golf": {"importance": 1}}),
        dict(PROFILE, labels={"grocery": ["aldi"]}),
        dict(PROFILE, programme="astrology"),
    ):
        with pytest.raises(ProfileError):
            fit_response(m, bad, A, P)
    s = score(np.array([15.0, np.nan]), 15, A, P)
    assert s[0] == pytest.approx(0.709, abs=1e-3) and s[1] == 0


def test_programme_shares_weight_the_campus_sites() -> None:
    m = _model()
    m.programmes = pd.DataFrame(
        {
            "programme": ["cs"],
            "label_en": ["CS"],
            "label_de": ["Inf"],
            "sites": [["morgenstelle", "tal"]],
            "shares": [[0.75, 0.25]],
        }
    ).set_index("programme")
    t = {r.key: r for r in term_results(m, dict(PROFILE, programme="cs"))}
    # cell A: 12 min to Morgenstelle, 30 min to Tal → 0.75·12 + 0.25·30 = 16.5
    assert t["campus_site"].minutes[m.cell_index["A"]] == pytest.approx(16.5)
