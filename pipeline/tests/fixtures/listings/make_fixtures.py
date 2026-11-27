"""Build the anonymised listing fixtures from raw WG-Gesucht pages (F4.2; run by hand, not by CI).

    uv run python pipeline/tests/fixtures/listings/make_fixtures.py data/listings_raw

Keeps only the panels the parser reads (title, key facts, costs, address and availability,
WG details, object details) in their original markup and replaces everything that could point
to a person or a real ad: the ad number (fake 9000000x), image URLs (fake), house numbers,
the free text (synthetic German text), single-person ages, and the map marker (rounded to
3 decimals, ~100 m). Contact boxes, profile pictures, initials, "member since", ads and
scripts are dropped. The script fails if anything of the original identifiers survives.
Raw pages stay in `data/` (git-ignored) and are never committed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# raw ad number → fixture name, fake number and replacements
FIXTURES = {
    "14421533": {
        "name": "wg_minimal",
        "fake": "90000001",
        "texts": {
            "Zimmer": (
                "Helles Zimmer in einer ruhigen 3er-WG, zentral gelegen. Die Warmmiete enthält "
                "Nebenkosten, Internet und Waschmaschine. Stadt und Uni zu Fuß erreichbar."
            )
        },
    },
    "4053055": {
        "name": "wg_rich",
        "fake": "90000002",
        "house_number": ("Auf dem Kreuz 26", "Auf dem Kreuz 1"),
        "texts": {
            "Zimmer": "Das Zimmer ist ca. 18 m² groß, teilmöbliert, mit Blick über die Stadt.",
            "Lage": "Ruhige Lage am Hang, Bus drei Minuten zu Fuß, Supermarkt nah.",
            "WG-Leben": (
                "Wir kochen ab und zu zusammen und teilen uns die Aufgaben im Haushalt. "
                "Meldet euch gern per Mail an wg.beispiel@example.org oder unter 0170 1234567, "
                "Instagram @wg_beispiel, mehr Bilder auf www.example.org/wg."
            ),
            "Sonstiges": "Besichtigungen sind abends und am Wochenende möglich.",
        },
    },
    "6669142": {
        "name": "wg_medium",
        "fake": "90000003",
        "ages": ("Bewohneralter:\n28\nbis\n28", "Bewohneralter:\n26\nbis\n26"),
        "texts": {
            "Zimmer": "Teilmöbliertes Zimmer in einer 2er-WG, hell und ruhig, mit großem Fenster.",
            "Lage": "Bäcker und Bus sind um die Ecke, mit dem Rad ist man schnell in der Stadt.",
            "WG-Leben": "Gemeinsames Wohnzimmer und Küche, entspanntes Zusammenleben.",
        },
    },
    "14219426": {
        "name": "studio",
        "fake": "90000004",
        "texts": {
            "Wohnung": "Gemütliche 1-Zimmer-Wohnung mit Terrasse und eigener Küche.",
            "Lage": "Ruhige Wohnstraße, Bus in zwei Minuten zu Fuß.",
        },
    },
    "14337244": {
        "name": "flat",
        "fake": "90000005",
        "texts": {
            "Wohnung": "Große 3-Zimmer-Wohnung im Erdgeschoss mit Garten, befristet.",
        },
    },
}
MAX_IMAGES = 3


def _clean(page: str) -> str:
    return re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<svg.*?</svg>|<!--.*?-->", "", page)


def _element_at(page: str, start: int) -> str:
    """The balanced <div …>…</div> element that starts at `start`."""
    depth = 0
    for m in re.finditer(r"<div\b|</div>", page[start:]):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            return page[start : start + m.end()]
    raise ValueError("unbalanced div")


def _panels(page: str) -> list[str]:
    out, pos = [], 0
    while (i := page.find('<div class="panel section_panel', pos)) >= 0:
        el = _element_at(page, i)
        out.append(el)
        pos = i + len(el)
    return out


def _drop(fragment: str, marker: str) -> str:
    """Remove the innermost row <div class="row"> that contains `marker`."""
    i = fragment.find(marker)
    if i < 0:
        return fragment
    start = fragment.rfind('<div class="row">', 0, i)
    return fragment.replace(_element_at(fragment, start), "", 1)


def _gallery(fake: str, n: int) -> str:
    slides = "".join(
        f'<div class="sp-slide"><img class="sp-image" src="img/d.gif" '
        f'data-large="https://img.wg-gesucht.de/media/up/fixture/{fake}_{k}.large.jpg" '
        f'alt="Bild {k}"/></div>\n'
        for k in range(1, n + 1)
    )
    return (
        f'<div class="gallery_section_panel"><div id="gallery_slides" class="sp-slides">\n{slides}'
        f'</div></div>\n<span id="gallery_details" class="display-none">{n} Fotos</span>\n'
    )


def _free_text(texts: dict[str, str]) -> str:
    tabs = "".join(
        f'<div class="section_panel_tab" data-text="#freitext_{i}"><h2 class="headline '
        f'section_panel_title">{tab}</h2></div>\n'
        for i, tab in enumerate(texts)
    )
    bodies = "".join(
        f'<div id="freitext_{i}" class="wordWrap section_freetext">\n<p>{text}</p>\n</div>\n'
        for i, text in enumerate(texts.values())
    )
    return (
        f'<div class="section_panel_tabs">\n{tabs}</div>\n<div class="panel section_panel '
        f'section_panel_with_tabs"><div id="ad_description_text">\n{bodies}</div></div>\n'
    )


def build(raw: str, ad: str, spec: dict) -> str:
    page = _clean(raw)
    fake = spec["fake"]
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', raw).group(1)
    marker = json.loads(re.search(r"markers:\s*(\[\{.*?\}\])", raw).group(1))[0]
    n_img = min(MAX_IMAGES, len(set(re.findall(r'data-large="([^"]+)"', page))))
    kept = []
    for panel in _panels(page[page.find('id="main_column"') :]):
        if 'class="detailed-view-title"' in panel:
            h1 = re.search(r'(?s)<h1 class="detailed-view-title">.*?</h1>', panel).group(0)
            facts = _element_at(panel, panel.find('<div class="section_footer_dark">'))
            number = f'<div id="basic_ad_details"><b>Anzeigennummer:</b> {ad}</div>\n'
            kept.append(f'<div class="panel section_panel">\n{h1}\n{_gallery(fake, n_img)}')
            kept.append(f"{number}{facts}\n</div>")
        elif re.search(r"section_panel_title[^>]*>\s*Kosten", panel):
            kept.append(_drop(panel, "SCHUFA"))
        elif re.search(
            r"section_panel_title[^>]*>\s*(Adresse|WG-Details|Angaben zum Objekt)", panel
        ):
            kept.append(panel)
    body = "\n".join(kept)
    # free text after the address panel, as on the page
    addr_end = body.find("</div>", body.find("Verfügbarkeit"))
    split = body.find('<div class="panel section_panel">', addr_end)
    free = _free_text(spec["texts"])
    body = body + "\n" + free if split < 0 else body[:split] + free + body[split:]
    for pair in (spec.get("house_number"), spec.get("ages")):
        if pair is None:
            continue
        old, new = pair
        pattern = r"\s+".join(re.escape(part) for part in old.split("\n"))
        body, n = re.subn(pattern, new.replace("\n", " "), body)
        assert n, f"{spec['name']}: {old!r} not found"
    body = body.replace(ad, fake)
    lat, lon = round(marker["lat"], 3), round(marker["lng"], 3)
    script = (
        "<script>\n  var map_config = {\n"
        f'    markers: [{{"lat":{lat},"lng":{lon},"offer_id":"{fake}"}}],\n'
        '    language: "de"\n  };\n</script>\n'
    )
    url = canonical.replace(ad, fake)
    doc = (
        '<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        f"<title>fixture {spec['name']}</title>\n"
        f'<link rel="canonical" href="{url}">\n</head>\n<body>\n'
        "<!-- Anonymised fixture built by make_fixtures.py from a WG-Gesucht ad (27 Nov 2026): "
        "ids, images, house numbers, free text and single ages replaced. -->\n"
        f'<div id="main_column">\n{body}\n</div>\n{script}</body>\n</html>\n'
    )
    doc = re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", doc))
    _check(doc, raw, ad)
    return doc


def _check(doc: str, raw: str, ad: str) -> None:
    """Fail if an original identifier or personal detail survived."""
    real_images = set(re.findall(r"img\.wg-gesucht\.de/[^\"']*?/media/up/20\d\d/[^\"']+", raw))
    problems = [ad] if ad in doc else []
    problems += [u for u in real_images if u in doc]
    for word in ("Mitglied seit", "profile_image", "nachricht-senden", "t_ph.html", "SCHUFA"):
        if word in doc:
            problems.append(word)
    if problems:
        raise SystemExit(f"anonymisation failed: {problems[:5]}")


def main(raw_dir: str) -> None:
    for ad, spec in FIXTURES.items():
        raw = (Path(raw_dir) / f"ad_{ad}.html").read_text(encoding="utf-8")
        doc = build(raw, ad, spec)
        path = HERE / f"{spec['name']}.html"
        path.write_text(doc, encoding="utf-8")
        print(f"{path.name}: {len(doc.encode()) / 1024:.1f} KB")


if __name__ == "__main__":
    main(sys.argv[1])
