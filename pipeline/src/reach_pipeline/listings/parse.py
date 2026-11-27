"""Parse a WG-Gesucht ad page into the listing fields of the data contract (F4.2).

One field spec for the server job and the import in the browser: the output is the "Parser
output" object of `docs/data_contract.md` (section Listings). Pure functions on the HTML text;
no network, no personal data kept: names, initials, profile pictures and contact details on the
page are never read, and contact data in the free text and title is replaced by `[…]`.

A page that cannot be read fully gives a partial result with `warnings` (`unknown:<field>`) and
`errors` (`no_address`, `not_an_ad`), never an exception.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

SOURCE = "wg_gesucht"
REDACTED = "[…]"

# URL path prefix → listing kind (data contract `kind`).
_KIND_PREFIX = (
    ("wg-zimmer-in-", "wg_room"),
    ("1-zimmer-wohnungen-in-", "studio"),
    ("wohnungen-in-", "flat"),
)
# Items of the "Angaben zum Objekt" block → normalised feature keys (data contract).
_FEATURE_WORDS = {
    "waschmaschine": "washing_machine",
    "spülmaschine": "dishwasher",
    "balkon": "balcony",
    "terrasse": "terrace",
    "garten": "garden",
    "gartenmitbenutzung": "garden",
    "keller": "cellar",
    "fahrradkeller": "bike_cellar",
    "aufzug": "lift",
    "haustiere erlaubt": "pets_allowed",
    "barrierefrei": "barrier_free",
    "eigene küche": "own_kitchen",
    "eigenes bad": "own_bathroom",
}
# Icon blocks that carry a feature themselves (icon class → key, or None to read the text).
_FEATURE_ICONS = {
    "mdi-wifi": "internet",
    "mdi-silverware-fork-knife": None,
    "mdi-wheelchair-accessibility": None,
    "mdi-plus-circle-outline": None,
}
# Fields whose absence is reported as `unknown:<field>` (all kinds, then per kind).
_EXPECTED = (
    "listing_id",
    "title",
    "rent_total_eur",
    "rent_cold_eur",
    "deposit_eur",
    "size_m2",
    "available_from",
    "address_text",
    "postcode",
    "district",
    "source_lat",
)
_EXPECTED_KIND = {"wg_room": ("household_size", "looking_for_gender"), "flat": ("rooms",)}

_NUM = r"(\d+(?:[.,]\d+)?)"
_PHONE = re.compile(r"(?<![\w.])(?:\+|00)?\d[\d ()/.-]{6,}\d(?![\w.])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S*[^\s.,;:!?)]", re.IGNORECASE)
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{3,}")
_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


@dataclass
class Listing:
    """The parser output object (data contract, section Listings → Parser output)."""

    listing_id: str | None = None
    source: str = SOURCE
    source_url: str | None = None
    kind: str | None = None
    title: str | None = None
    rent_total_eur: int | None = None
    rent_cold_eur: int | None = None
    utilities_eur: int | None = None
    other_costs_eur: int | None = None
    deposit_eur: int | None = None
    transfer_fee_eur: int | None = None
    size_m2: float | None = None
    flat_size_m2: float | None = None
    rooms: float | None = None
    household_size: int | None = None
    flatmates_women: int | None = None
    flatmates_men: int | None = None
    flatmates_diverse: int | None = None
    flatmates_age_min: int | None = None
    flatmates_age_max: int | None = None
    looking_for_gender: str | None = None
    looking_for_age_min: int | None = None
    looking_for_age_max: int | None = None
    wg_types: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    smoking: str | None = None
    available_from: str | None = None
    available_to: str | None = None
    furnished: str | None = None
    features: list[str] = field(default_factory=list)
    district: str | None = None
    postcode: str | None = None
    address_text: str | None = None
    source_lat: float | None = None
    source_lon: float | None = None
    image_urls: list[str] = field(default_factory=list)
    description_excerpt: str | None = None
    online_text: str | None = None
    online_since: str | None = None
    fetched_at: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------------------------
# small helpers


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed."""
    no_tags = re.sub(r"<br\s*/?>", "\n", fragment)
    no_tags = re.sub(r"<[^>]+>", " ", no_tags)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(no_tags)).strip()


def _flat(fragment: str) -> str:
    return re.sub(r"\s+", " ", _text(fragment)).strip()


def _number(value: str | None) -> float | None:
    """German number ("1.150", "18,5", "590€") → float; "n.a." and empty → None."""
    if not value:
        return None
    m = re.search(r"\d[\d.]*(?:,\d+)?", value)
    if not m:
        return None
    raw = m.group(0)
    raw = raw.replace(".", "") if "," in raw or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw) else raw
    return float(raw.replace(",", "."))


def _euro(value: str | None) -> int | None:
    n = _number(value)
    return None if n is None else int(round(n))


def _date(value: str | None, fetched: datetime | None) -> str | None:
    """ "26.11.2026" → "2026-11-26"; "ab sofort"/"sofort" → the fetch date."""
    if not value:
        return None
    m = _DATE.search(value)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    if "sofort" in value.lower() and fetched is not None:
        return fetched.date().isoformat()
    return None


def strip_contact(text: str) -> str:
    """Replace e-mail addresses, URLs, phone numbers and messenger handles by `[…]`."""
    for pattern in (_EMAIL, _URL, _HANDLE):
        text = pattern.sub(REDACTED, text)
    # a date ("01.12.2026") looks like a group of digits: keep it
    return _PHONE.sub(lambda m: m.group(0) if _DATE.fullmatch(m.group(0)) else REDACTED, text)


def _shorten(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", strip_contact(text)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-")
    return f"{cut} …"


def _clean(page: str) -> str:
    return re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<svg.*?</svg>|<!--.*?-->", "", page)


# ---------------------------------------------------------------------------------------------
# field groups


def _kind(url: str | None) -> str | None:
    if not url:
        return None
    path = url.rsplit("/", 1)[-1]
    return next((kind for prefix, kind in _KIND_PREFIX if path.startswith(prefix)), None)


def _identity(raw: str, page: str, url: str | None, out: Listing) -> None:
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', raw)
    out.source_url = canonical.group(1) if canonical else url
    number = re.search(r"Anzeigennummer:\s*</b>\s*(\d+)", page)
    if not number and out.source_url:
        number = re.search(r"\.(\d+)\.html", out.source_url)
    out.listing_id = f"{SOURCE}:{number.group(1)}" if number else None
    out.kind = _kind(out.source_url)


def _title(page: str, out: Listing, limit: int) -> str | None:
    """Title text and the household attribute of the heading ("3er WG (1w,1m,0d,0n)")."""
    m = re.search(r'(?s)<h1 class="detailed-view-title">(.*?)</h1>', page)
    if not m:
        return None
    spans = re.findall(r'(?s)<span class="[^"]*">(.*?)</span>', m.group(1))
    title = _flat(spans[-1]) if spans else _flat(m.group(1))
    out.title = _shorten(title, limit)
    attr = re.search(r'<span class="mr5" title="([^"]*)"', m.group(1))
    return attr.group(1) if attr else None


def _key_facts(page: str, out: Listing) -> None:
    labels = [_flat(x) for x in re.findall(r'(?s)<span class="key_fact_detail">(.*?)</span>', page)]
    values = [_flat(x) for x in re.findall(r'(?s)<b class="key_fact_value">(.*?)</b>', page)]
    for label, value in zip(labels, values, strict=False):
        if label in ("Zimmergröße", "Größe"):
            out.size_m2 = _number(value)
        elif label == "Gesamtmiete":
            out.rent_total_eur = _euro(value)
        elif label == "Zimmer":
            out.rooms = _number(value)


def _panel_pairs(page: str) -> dict[str, str]:
    """`section_panel_detail` label → `section_panel_value` text of the cost and date panels."""
    pairs = re.findall(
        r'(?s)<span class="section_panel_detail">([^<]*?)</span>(?:(?!section_panel_detail).)*?'
        r'<span class="section_panel_value">(.*?)</span>',
        page,
    )
    return {_flat(k).rstrip(":"): _flat(v) for k, v in pairs}


def _costs(pairs: dict[str, str], out: Listing, fetched: datetime | None) -> None:
    out.rent_cold_eur = _euro(pairs.get("Miete"))
    out.utilities_eur = _euro(pairs.get("Nebenkosten"))
    out.other_costs_eur = _euro(pairs.get("Sonstige Kosten"))
    out.deposit_eur = _euro(pairs.get("Kaution"))
    out.transfer_fee_eur = _euro(pairs.get("Ablösevereinbarung"))
    out.available_from = _date(pairs.get("frei ab"), fetched)
    out.available_to = _date(pairs.get("frei bis"), fetched)
    if out.rent_total_eur is None and out.rent_cold_eur is not None:
        parts = (out.rent_cold_eur, out.utilities_eur or 0, out.other_costs_eur or 0)
        out.rent_total_eur = sum(parts)


def _address(page: str, out: Listing) -> None:
    m = re.search(r'(?s)Adresse\s*</h2>.*?<span class="section_panel_detail">(.*?)</span>', page)
    if not m:
        return
    lines = [ln.strip() for ln in _text(m.group(1)).split("\n") if ln.strip()]
    place = next((ln for ln in lines if re.match(r"\d{5}\b", ln)), None)
    street = next((ln for ln in lines if ln is not place), None)
    out.address_text = street or None
    if place:
        pm = re.match(r"(\d{5})\s+(\S+)\s*(.*)", place)
        if pm:
            out.postcode = pm.group(1)
            district = pm.group(3).strip()
            out.district = district if district and district != pm.group(2) else None


def _online(page: str, out: Listing, fetched: datetime | None) -> None:
    m = re.search(r"(?s)Online:\s*</span>.*?<b[^>]*>(.*?)</b>", page)
    if not m:
        return
    text = _flat(m.group(1))
    out.online_text = text
    if fetched is None:
        return
    absolute = _date(text, None)
    if absolute:
        out.online_since = absolute
        return
    rel = re.match(r"(\d+)\s+(Minute|Stunde|Tag)", text)
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        delta = {"Minute": timedelta(minutes=n), "Stunde": timedelta(hours=n)}.get(
            unit, timedelta(days=n)
        )
        since = (fetched - delta).replace(minute=0, second=0, microsecond=0)
        out.online_since = since.isoformat()


def _gender(text: str) -> str | None:
    t = text.lower()
    if "egal" in t:
        return "any"
    if t.startswith("frau"):
        return "woman"
    if t.startswith("mann"):
        return "man"
    if t.startswith("divers"):
        return "diverse"
    return None


def _wg_details(page: str, title_attr: str | None, out: Listing) -> None:
    """The "WG-Details" lists: household, flatmates (counts, age range), who is wanted."""
    block = re.search(r"(?s)WG-Details\s*</h2>(.*?)(?:Angaben zum Objekt|map_marker_info_)", page)
    items = []
    wanted: list[str] = []
    if block:
        parts = re.split(r"Gesucht wird:", block.group(1), maxsplit=1)
        item_re = r'(?s)<li>\s*<span class="section_panel_detail">(.*?)</span>\s*</li>'
        items = [_flat(x) for x in re.findall(item_re, parts[0])]
        if len(parts) > 1:
            wanted = [_flat(x) for x in re.findall(item_re, parts[1])]
    for it in items:
        if m := re.search(r"(\d+)er WG", it):
            out.household_size = int(m.group(1))
        if m := re.match(r"Wohnungsgröße:\s*" + _NUM, it):
            out.flat_size_m2 = _number(m.group(1))
        if "(" in it and re.search(r"Frau|Mann|Männer|Divers", it):
            out.flatmates_women = _count(it, r"Frau(?:en)?")
            out.flatmates_men = _count(it, r"M(?:a|ä)nn(?:er)?")
            out.flatmates_diverse = _count(it, r"Divers(?:e)?")
        if m := re.match(r"Bewohneralter:\s*(\d+)\s*bis\s*(\d+)", it):
            out.flatmates_age_min, out.flatmates_age_max = int(m.group(1)), int(m.group(2))
        if it.startswith("Rauchen"):
            out.smoking = it
        if m := re.match(r"Sprache/n:\s*(.*)", it):
            out.languages = [x.strip() for x in m.group(1).split(",") if x.strip()]
        if re.search(r"\bWG\b|-WG\b|Verbindung", it) and not re.search(r"\d+er WG", it):
            out.wg_types = [x.strip() for x in it.split(",") if x.strip()]
    # fallback: the heading attribute "3er WG (1w,1m,0d,0n)"
    household = re.match(r"(\d+)er WG \((\d+)w,(\d+)m,(\d+)d", title_attr or "")
    if household and out.household_size is None:
        out.household_size = int(household.group(1))
        out.flatmates_women, out.flatmates_men, out.flatmates_diverse = (
            int(household.group(2)),
            int(household.group(3)),
            int(household.group(4)),
        )
    for w in wanted:
        out.looking_for_gender = _gender(w) or out.looking_for_gender
        if m := re.search(r"zwischen\s+(\d+)\s+und\s+(\d+)", w):
            out.looking_for_age_min, out.looking_for_age_max = int(m.group(1)), int(m.group(2))


def _count(text: str, word: str) -> int:
    m = re.search(r"(\d+)\s*" + word + r"\b", text)
    return int(m.group(1)) if m else 0


def _object(page: str, out: Listing) -> None:
    """The "Angaben zum Objekt" icon block: furnishing and features."""
    found: list[str] = []
    item_re = (
        r'(?s)<div class="text-center">\s*<span class="mdi (mdi-[a-z-]+)[^"]*"></span>(.*?)</div>'
    )
    for icon, fragment in re.findall(item_re, page):
        text = _flat(fragment)
        low = text.lower()
        if icon == "mdi-bed-double-outline":
            if "teilmöbliert" in low:
                out.furnished = "partly"
            elif "unmöbliert" in low:
                out.furnished = "none"
            elif "möbliert" in low:
                out.furnished = "full"
        elif icon == "mdi-car":
            if re.search(
                r"gute parkmöglichkeiten|bewohnerparken|tiefgarage|eigener parkplatz", low
            ):
                found.append("parking")
        elif icon in _FEATURE_ICONS:
            key = _FEATURE_ICONS[icon]
            if key:
                found.append(key)
                continue
            for word in (w.strip() for w in text.split(",")):
                if word:
                    found.append(_FEATURE_WORDS.get(word.lower(), f"other:{word}"))
    out.features = list(dict.fromkeys(found))


def _images(page: str) -> list[str]:
    block = re.search(r'(?s)<div id="gallery_slides"(.*?)<span id="gallery_details"', page)
    urls = re.findall(r'data-large="([^"]+)"', block.group(1) if block else "")
    return list(dict.fromkeys(html.unescape(u).replace("/./", "/") for u in urls))


def _description(page: str, limit: int) -> str | None:
    texts = []
    for m in re.finditer(
        r'(?s)<div id="freitext_\d+"[^>]*>(.*?)</div>\s*(?=<div id="freitext_|</div>)', page
    ):
        inner = re.sub(r"(?s)<div id='div-gpt-ad[^>]*>\s*</div>", "", m.group(1))
        t = _flat(inner)
        if t:
            texts.append(t)
    return _shorten(" ".join(texts), limit)


def _source_point(raw: str, out: Listing) -> None:
    m = re.search(r"markers:\s*(\[\{.*?\}\])", raw)
    if not m:
        return
    try:
        marker = json.loads(m.group(1))[0]
        out.source_lat, out.source_lon = float(marker["lat"]), float(marker["lng"])
    except (ValueError, KeyError, IndexError, TypeError):
        return


# ---------------------------------------------------------------------------------------------
# entry points


def parse_ad(
    raw: str,
    url: str | None = None,
    fetched_at: datetime | None = None,
    *,
    description_max_chars: int,
    title_max_chars: int,
) -> Listing:
    """Parse one ad page; never raises on unexpected content (warnings and errors instead)."""
    out = Listing(fetched_at=fetched_at.isoformat() if fetched_at else None)
    page = _clean(raw)
    if 'class="detailed-view-title"' not in page and "Anzeigennummer" not in page:
        out.errors.append("not_an_ad")
        out.source_url = url
        out.kind = _kind(url)
        return out
    _identity(raw, page, url, out)
    title_attr = _title(page, out, title_max_chars)
    _key_facts(page, out)
    _costs(_panel_pairs(page), out, fetched_at)
    _address(page, out)
    _online(page, out, fetched_at)
    if out.kind == "wg_room":
        _wg_details(page, title_attr, out)
    _object(page, out)
    out.image_urls = _images(page)
    out.description_excerpt = _description(page, description_max_chars)
    _source_point(raw, out)
    if out.kind in ("studio",) and out.rooms is None:
        out.rooms = 1.0
    expected = _EXPECTED + _EXPECTED_KIND.get(out.kind or "", ())
    out.warnings = [f"unknown:{f}" for f in expected if getattr(out, f) is None]
    if out.address_text is None and out.district is None:
        out.errors.append("no_address")
    return out


def coverage(listing: Listing) -> float:
    """Share of the expected fields that were read (reported per fixture and in V12)."""
    expected = _EXPECTED + _EXPECTED_KIND.get(listing.kind or "", ())
    return 1 - sum(1 for f in expected if getattr(listing, f) is None) / len(expected)


@dataclass(frozen=True)
class SearchHit:
    """One ad on a search result page."""

    listing_id: str
    kind: str | None
    url: str


def parse_search(raw: str, base_url: str) -> list[SearchHit]:
    """Ads on a search result page, in page order, without duplicates."""
    hits: dict[str, SearchHit] = {}
    card_re = r'class="wgg-list-card offer_list_item[^"]*"\s+data-id="(\d+)"\s+href="([^"]+)"'
    for ad_id, href in re.findall(card_re, raw):
        url = href if href.startswith("http") else base_url.rstrip("/") + href
        hits.setdefault(ad_id, SearchHit(f"{SOURCE}:{ad_id}", _kind(url), url))
    return list(hits.values())
