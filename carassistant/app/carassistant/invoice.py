"""Read an invoice: the text of a PDF (its text layer - or, for a scan, the pictures in it) or of a photo (text recognition on this server, see
receipt.py), then a parser that picks out what a cost needs: the date, the total, who sent it, its number, the odometer, and what kind of cost it is.

Nothing leaves the server. The result only *fills in* the form of a new entry (service, parts, modification, fixed cost, refuel); the person looks at
it and saves. ``parse`` works on plain text, so it can be tested without a file. German and English invoices are understood; for any other language
the fields stay empty and the person types them.

The total is checked where the invoice allows it: net + VAT = gross (to two cents). With that check a misread digit is found, and a total that was
only guessed (the biggest amount of the page) says so.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta

from . import receipt

MAX_BYTES = receipt.MAX_BYTES  # a larger photo is kept but not read
PDF_PAGES = 3  # the pages of a PDF that are read: an invoice has its figures on the first ones
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".bmp")
KINDS = ("service", "parts", "mods", "fixed", "fuel")  # what an invoice can be booked as (the entries of the cost page)
FIXED_KINDS = ("insurance", "tax", "club", "parking", "toll")  # a fixed cost this can be (entities.FIXED_KINDS, "other" otherwise)

# ------------------------------------------------------------------ amounts

# 1.234,56 (German) | 1,234.56 (English) | 1 234,56 with a non-breaking space or an apostrophe (Swiss) | 234,56; never a date (12.03.2026) or a rate (19,00 %)
_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:[  ']\d{3})+[.,]\d{2}|\d+[.,]\d{2})(?!\d|[.,]\d)(?!\s*%)"
)
_RATE = re.compile(r"(?<![\d.,])(\d{1,2}(?:[.,]\d{1,2})?)\s*%")

# the labels of the lines that name a total, by how sure they are
_W4 = re.compile(
    r"gesamtbetrag|gesamtsumme|rechnungsbetrag|rechnungssumme|endbetrag|endsumme|gesamtpreis|bruttobetrag|brutto[-\s]?summe|summe\s+brutto|"
    r"gesamt\s+brutto|grand\s+total|invoice\s+total|total\s+invoice|total\s+amount|total\s+gross|gross\s+total",
    re.I,
)
_W3 = re.compile(
    r"zahlbetrag|zahlungsbetrag|zu\s+zahlen|zu\s+bezahlen|amount\s+due|total\s+due|balance\s+due|amount\s+payable|insgesamt|gesamtbeitrag|zahlbeitrag|"
    r"gesamtpr[aä]mie|jahresbeitrag|jahrespr[aä]mie",
    re.I,
)
_W2 = re.compile(r"\b(?:total|gesamt|summe|brutto|sum|gross)\b", re.I)
_W1 = re.compile(r"\b(?:betrag|amount|beitrag|pr[aä]mie|bar|ec|ec-karte|karte|visa|mastercard|paypal|lastschrift|eur|euro)\b|€", re.I)
_NET = re.compile(
    r"\b(?:netto|nettobetrag|nettosumme|nettopreis|net|net\s+amount|net\s+total|zwischensumme|subtotal|sub-total|summe\s+netto|gesamt\s+netto|total\s+net)\b",
    re.I,
)
_VAT = re.compile(r"\b(?:mwst|mw\.?\s*st|ust|umsatzsteuer|mehrwertsteuer|vat|sales\s+tax|gst)\b", re.I)
_COL = re.compile(
    r"(netto|\bnet\b|zwischensumme|subtotal)|(mwst|mw\.?\s*st|\bust\b|umsatzsteuer|mehrwertsteuer|\bvat\b)|(brutto|gesamt\w*|total|summe|endbetrag|rechnungsbetrag)",
    re.I,
)
_NEGATIVE = re.compile(
    r"anzahlung|vorauszahlung|bereits\s+bezahlt|abz[uü]glich|abzgl|rabatt|discount|skonto|gutschrift|credit\s+note|deposit|already\s+paid|\bpaid\b|"
    r"r[uü]ckerstattung|refund|trinkgeld|\btip\b|pfand",
    re.I,
)


def _money(token: str) -> float:
    t = re.sub(r"[  ']", "", token)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    else:
        t = t.replace(",", ".")
    return float(t)


def _amounts(line: str) -> list[float]:
    """Every amount of a line (two decimals, German or English writing), as numbers."""
    out = []
    for m in _AMOUNT.finditer(line):
        value = _money(m.group(1))
        if 0.5 <= value <= 500_000:
            out.append(value)
    return out


def _only_amount(line: str) -> bool:
    """A line that is nothing but an amount (and a currency): the figure belongs to the label above it."""
    rest = _AMOUNT.sub("", line)
    return bool(_AMOUNT.search(line)) and not re.search(r"[A-Za-zÄÖÜäöüß]{3,}", re.sub(r"eur(?:o)?|chf|usd|gbp", "", rest, flags=re.I))


def _total(lines: list[str]) -> dict:
    """The total of an invoice: the amount on a line that names it (the surest label wins, then the biggest figure), checked against net + VAT."""
    cand: list[tuple[int, float]] = []
    nets: list[float] = []
    vats: list[float] = []
    rates: list[float] = []
    every: list[float] = []
    for i, line in enumerate(lines):
        vals = _amounts(line)
        every += vals
        near = vals
        if _VAT.search(line):
            rates += [_money(r.group(1)) for r in _RATE.finditer(line)]
        if not near and i + 1 < len(lines) and _only_amount(lines[i + 1]):
            below = _amounts(lines[i + 1])
            cols = [m.lastindex for m in _COL.finditer(line)]
            if len(cols) == len(below) >= 2:  # a table: Net | VAT | Gross, each over its figure
                for column, value in zip(cols, below, strict=True):
                    if column == 1:
                        nets.append(value)
                    elif column == 2:
                        vats.append(value)
                    else:
                        cand.append((3, value))
                continue
            near = below  # a column layout: the label, then its figure on the next line
        weight = 4 if _W4.search(line) else 3 if _W3.search(line) else 2 if _W2.search(line) else 1 if _W1.search(line) else 0
        if _NEGATIVE.search(line):
            weight = 0
        if weight < 4 and _NET.search(line):
            nets += near
            weight = 0
        elif weight < 4 and _VAT.search(line):
            vats += [v for v in near if v < 100_000]
            weight = 0
        if weight and near:
            cand.append((weight, near[-1]))
    best, best_weight = None, 0
    if cand:
        best_weight = max(w for w, _ in cand)
        best = max(v for w, v in cand if w == best_weight)
    out = {"amount": best, "net": None, "vat": None, "checked": False, "guess": best is not None and best_weight <= 1}

    def has(x: float) -> bool:
        return any(abs(x - y) <= 0.015 for y in every)

    for n in nets:  # net + VAT = gross, with the VAT as an amount or as a rate
        for v in vats:
            g = round(n + v, 2)
            if v < n and has(g) and (best is None or best_weight < 4 or abs(best - g) <= 0.015):
                return {**out, "amount": g, "net": n, "vat": v, "checked": True}
        for r in rates:
            g = round(n * (1 + r / 100), 2)
            if 0 < r < 30 and has(g) and (best is None or best_weight < 4 or abs(best - g) <= 0.015):
                return {**out, "amount": g, "net": n, "vat": round(g - n, 2), "checked": True}
    if best is not None:
        for v in vats:  # the gross and a VAT amount that fits one of its rates
            for r in rates:
                if 0 < r < 30 and abs(round(best * r / (100 + r), 2) - v) <= 0.02:
                    return {**out, "net": round(best - v, 2), "vat": v, "checked": True}
        return out
    if every:
        return {**out, "amount": max(every), "guess": True}  # nothing says which it is: the biggest figure of the page, to be checked
    return out


# ------------------------------------------------------------------ date

_MONTHS = {
    "jan": 1, "januar": 1, "january": 1, "feb": 2, "februar": 2, "february": 2, "mar": 3, "mär": 3, "maer": 3, "märz": 3, "maerz": 3, "march": 3,
    "apr": 4, "april": 4, "mai": 5, "may": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "okt": 10, "oct": 10, "oktober": 10, "october": 10, "nov": 11, "november": 11,
    "dez": 12, "dec": 12, "dezember": 12, "december": 12,
}  # fmt: skip
_NUM_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)|(?<!\d)(\d{1,2})[./-]\s?(\d{1,2})[./-]\s?(\d{4}|\d{2})(?!\d)")
_TEXT_DATE = re.compile(r"(?<!\d)(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]{3,9})\.?,?\s+(\d{4})(?!\d)")  # 12. März 2026 | 12 March 2026
_TEXT_DATE_US = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)")  # March 12, 2026
_DATE_TOP = re.compile(
    r"rechnungsdatum|belegdatum|rechnung\s+vom|invoice\s+date|date\s+of\s+invoice|datum\s+der\s+rechnung|ausstellungsdatum|date\s+of\s+issue|issue\s+date",
    re.I,
)
_DATE_LABEL = re.compile(r"\b(?:datum|date|leistungsdatum|lieferdatum|auftragsdatum)\b", re.I)
_DATE_SKIP = re.compile(
    r"f[aä]llig|zahlbar|\bdue\b|sp[aä]testens|payable|g[uü]ltig|\bvalid|ablauf|expir|zulassung|registration|geburt|birth|n[aä]chste|next\s+(?:hu|inspection)|"
    r"\bhu\s+bis|t[uü]v\s+bis|\bbis\b|until|zahlungsziel|lieferung\s+bis|\bab\s+dem\b",
    re.I,
)


def _dates_in(line: str, today: date) -> list[date]:
    found: list[date] = []
    for m in _NUM_DATE.finditer(line):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                a, b, year = int(m.group(4)), int(m.group(5)), int(m.group(6))
                year = year + 2000 if year < 100 else year
                day, month = (b, a) if b > 12 >= a else (a, b)  # 03/25/2026 is American; with both up to 12 the day comes first
                d = date(year, month, day)
        except ValueError:
            continue
        found.append(d)
    for m in _TEXT_DATE.finditer(line):
        month = _MONTHS.get(m.group(2).lower())
        if month:
            try:
                found.append(date(int(m.group(3)), month, int(m.group(1))))
            except ValueError:
                continue
    for m in _TEXT_DATE_US.finditer(line):
        month = _MONTHS.get(m.group(1).lower())
        if month:
            try:
                found.append(date(int(m.group(3)), month, int(m.group(2))))
            except ValueError:
                continue
    return [d for d in found if date(2000, 1, 1) <= d <= today + timedelta(days=1)]


def _date(lines: list[str], today: date) -> str | None:
    """The date of the invoice: the one next to ``Rechnungsdatum`` / ``Invoice date``, else one next to ``Datum`` / ``Date``, else the first one (due
    dates, the registration of the car and the next inspection are passed over)."""
    best: tuple[int, int, date] | None = None
    for i, line in enumerate(lines):
        if _DATE_SKIP.search(line) and not _DATE_TOP.search(line):
            continue
        days = _dates_in(line, today)
        if not days and i + 1 < len(lines) and (_DATE_TOP.search(line) or _DATE_LABEL.search(line)):
            nxt = lines[i + 1]
            if not _DATE_SKIP.search(nxt) and len(re.sub(r"[\d./\-\s]", "", nxt)) <= 3:  # the date stands alone on the next line
                days = _dates_in(nxt, today)
        if not days:
            continue
        rank = 0 if _DATE_TOP.search(line) else 1 if _DATE_LABEL.search(line) else 2
        if best is None or rank < best[0]:
            best = (rank, i, days[0])
    return best[2].isoformat() if best else None


# ------------------------------------------------------------------ who, which number, which kilometres

_LEGAL = re.compile(
    r"\b(?:gmbh(?:\s*&\s*co\.?\s*kg)?|mbh|ag|kg|ohg|ug|gbr|e\.?\s?k\.?|e\.?\s?v\.?|kgaa|ltd\.?|llc|inc\.?|plc|s\.?a\.?|s\.?r\.?l\.?|b\.?v\.?|n\.?v\.?|oy|a/s|co\.)(?=\s|$|[,.;])",
    re.I,
)
_BUSINESS = re.compile(
    r"autohaus|\bauto\b|kfz|werkstatt|garage|motors?|reifen|tyres?|tires?|karosserie|lackier|tankstelle|versicherung|insurance|automobil|"
    r"zentrum|center|centre|parkhaus|parking|\bclub\b|adac|t[uü]v|dekra|\bgt[uü]\b|\bteile\b|\bparts\b|\bshop\b",
    re.I,
)
_NOT_NAME = re.compile(
    r"rechnung|invoice|beleg|quittung|receipt|lieferschein|kundennummer|customer|datum|\bdate\b|seite|\bpage\b|\btel\b|telefon|\bfax\b|e-?mail|www\.|http|"
    r"\biban\b|\bbic\b|\bust\b|steuer|\bherr\b|\bfrau\b|^an\b|kennzeichen|fahrgestell|\bfin\b|\bvin\b|\d{5}\s+\w|@",
    re.I,
)
_SENDER_SPLIT = re.compile(r"\s{3,}|\s+[·•|]\s+|,\s+(?=[^,]*\d)")
_NUMBER = re.compile(
    r"(?:rechnungs?[-\s]*(?:nr|nummer|no)\.?|invoice\s*(?:no|number|nr|#)\.?|beleg[-\s]*(?:nr|nummer)\.?|rg[-\s]*nr\.?|rechnung\s+nr\.?)[\s:#.-]*([A-Z0-9][A-Z0-9\-/.]{2,24})",
    re.I,
)
_ODOMETER = re.compile(
    r"\b(?:km[\s.\-]*sta[a-z]{1,2}|kilometer[\s.\-]*sta[a-z]{1,2}|tachostand|laufleistung|fahrleistung|km[\s.\-]*leistung|kilometerleistung|odometer|"
    r"mileage|fzg\.?[\s\-]*km)\b[\s.:=]*(\d{1,3}(?:[ .,'’]\d{3})+|\d{3,7})(?!\d)",
    re.I,
)


def _vendor(lines: list[str]) -> str:
    """The sender: the name in the letterhead - a line with a legal form (GmbH, AG, ...) or a trade word (Autohaus, Reifen, ...), or the small sender line
    above the address (``Name · Street 1 · 12345 Town``)."""
    best, best_score = "", 0
    for i, raw in enumerate(lines[:14]):
        parts = _SENDER_SPLIT.split(raw)
        sender = len(parts) > 1 and any(re.search(r"\d", p) for p in parts[1:])
        name = parts[0].strip(" ,;:-")
        if name.endswith(".") and not _LEGAL.search(name):  # a full stop ends a sentence, but belongs to e.K. / Ltd.
            name = name.rstrip(" .")
        letters = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", name)
        if not 3 <= len(letters) <= 60 or len(name) > 70 or len(name.split()) > 7 or len(letters) < 0.6 * len(name.replace(" ", "")):
            continue
        if _NOT_NAME.search(name):
            continue
        trade = bool(_LEGAL.search(name) or _BUSINESS.search(name))
        score = (
            (3 if _LEGAL.search(name) else 0) + (2 if _BUSINESS.search(name) else 0) + (2 if sender and trade else 0) + (1 if i < 3 else 0)
        )
        if score > best_score:
            best, best_score = name, score
    return best[:60] if best_score >= 2 else ""


_ORDER_NUMBER = re.compile(
    r"(?:bestell(?:ung)?s?[-\s]*(?:nr|nummer)|auftrags[-\s]*(?:nr|nummer)|order\s*(?:no|number|nr|#))\.?[\s:#.-]*([A-Z0-9][A-Z0-9\-/.]{2,24})",
    re.I,
)


def _number(lines: list[str]) -> str:
    """The number of the invoice; a shop that names only its order or job number gives that one."""
    for pattern in (_NUMBER, _ORDER_NUMBER):
        for line in lines[:60]:
            m = pattern.search(line)
            if m:
                return m.group(1).strip(".-/")[:24]
    return ""


def _odometer(lines: list[str]) -> int | None:
    """The odometer reading a workshop printed (only a labelled number: an invoice is full of other numbers), in kilometres."""
    for line in lines:
        m = _ODOMETER.search(re.sub(r"(?<=\d)[Oo](?=\d)", "0", line))
        if m:
            value = int(re.sub(r"\D", "", m.group(1)))
            if 100 <= value <= 9_999_999:
                return value
    return None


# ------------------------------------------------------------------ what kind of cost

_FIXED_WORDS = {
    "insurance": r"versicherung|haftpflicht|kasko|insurance|pr[aä]mie|\bpolice\b|policy",
    "tax": r"kfz-?steuer|kraftfahrzeugsteuer|steuerbescheid|vehicle\s+tax|road\s+tax|hauptzollamt|vehicle\s+excise",
    "club": r"\badac\b|mitgliedsbeitrag|mitgliedschaft|membership|automobilclub|\bavd\b",
    "parking": r"parkgeb[uü]hr|parkhaus|stellplatz|dauerparker|parking|tiefgarage",
    "toll": r"vignette|\bmaut\b|\btoll\b|asfinag|autobahngeb",
}
_LABOUR = re.compile(
    r"arbeitslohn|arbeitszeit|arbeitswert|\baw\b|\blohn\b|montage|einbau|werkstatt|inspektion|wartung|kundendienst|reparatur|labou?r|workshop|fitting|"
    r"diagnose|hauptuntersuchung|\bt[uü]v\b|\bhu\b|reifenwechsel|achsvermessung|[oö]lwechsel|\bservice\b|instandsetzung",
    re.I,
)
_SHOP = re.compile(
    r"artikelnummer|art\.?\s*-?\s*nr|teilenummer|bestellnummer|bestellung|order\s*(?:no|number)|versand|lieferung|shipping|delivery|ersatzteil|"
    r"spare\s+part|zubeh[oö]r|accessor|\bsku\b|part\s*(?:no|number)|warenkorb",
    re.I,
)
_MODS = re.compile(
    r"umbau|nachr[uü]stung|retrofit|tuning|folierung|\bwrap\b|anh[aä]ngerkupplung|sportfahrwerk|tieferlegung|chiptuning|abgasanlage|"
    r"teilegutachten|eintragung|spoiler|conversion",
    re.I,
)
_EVERY = (
    ("halfyear", r"\bhalbj[aä]hrlich|semi-?annual|half[-\s]?year"),
    ("quarter", r"\bviertelj[aä]hrlich|quarterly|per\s+quarter"),
    ("month", r"\bmonatlich|monthly|per\s+month|pro\s+monat"),
    ("year", r"\bj[aä]hrlich|annual|yearly|per\s+year|pro\s+jahr|jahresbeitrag|jahrespr[aä]mie"),
)
_WORK = (  # what the work or the goods were: the first that is named gives the title of the entry (an i18n key inv.w.<key>)
    ("inspection", r"inspektion|wartung|kundendienst|inspection|maintenance|\bservice\s+(?:a|b|1|2)\b"),
    ("hu", r"hauptuntersuchung|\bt[uü]v\b|\bhu\b|abgasuntersuchung|pr[uü]fplakette|\bmot\b|dekra"),
    ("oil", r"[oö]lwechsel|motor[oö]l|oil\s+change|engine\s+oil"),
    ("brakes", r"bremsscheibe|bremsbel[aä]g|bremsen|bremsfl[uü]ssigkeit|brake"),
    ("tyres", r"reifenwechsel|reifen|r[aä]der|felgen|\btyres?\b|\btires?\b|wheels?"),
    ("alignment", r"achsvermessung|spurvermessung|alignment"),
    ("ac", r"klimaanlage|klimaservice|air\s+conditioning"),
    ("windscreen", r"windschutzscheibe|frontscheibe|steinschlag|windscreen|windshield"),
    ("battery", r"batterie|akku\b|battery"),
    ("sparkplugs", r"z[uü]ndkerze|gl[uü]hkerze|spark\s+plug"),
    ("filter", r"filter"),
    ("wipers", r"wischer|wiper"),
    ("bulbs", r"gl[uü]hlampe|leuchtmittel|\blampe|bulb"),
    ("diagnosis", r"diagnose|fehlerspeicher|diagnostic"),
    ("repair", r"reparatur|repair|instandsetzung"),
    ("wash", r"autow[aä]sche|waschanlage|fahrzeugpflege|car\s+wash|detailing|aufbereitung"),
)
_DOCTYPE = (
    ("estimate", r"kostenvoranschlag|angebot|offerte|quotation|\bestimate\b|proforma"),
    ("delivery", r"lieferschein|delivery\s+note|packing\s+slip"),
    ("reminder", r"mahnung|zahlungserinnerung|payment\s+reminder|\breminder\b"),
)


def _count(pattern: str | re.Pattern, text: str) -> int:
    rx = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, re.I)
    return len({m.group(0).lower() for m in rx.finditer(text)})


def _kind(text: str, fuel: dict | None) -> dict:
    """What an invoice is, as far as its words say: ``kind`` (one of KINDS or None), for a fixed cost its ``fixed_kind`` and ``every``, and the ``work``
    it names (a key of _WORK)."""
    out: dict = {"kind": None, "fixed_kind": "other", "every": "once", "work": ""}
    scores = {k: _count(w, text) for k, w in _FIXED_WORDS.items()}
    fixed = sum(scores.values())
    labour, shop, mods = _count(_LABOUR, text), _count(_SHOP, text), _count(_MODS, text)
    if fuel is not None and not labour:  # a refuel: a fuel named and amount x price = total, and nothing of a workshop
        out["kind"] = "fuel"
    elif fixed and fixed >= labour + shop:
        out["kind"] = "fixed"
    elif mods >= 2 or re.search(r"umbau|nachr[uü]stung|retrofit|tuning|folierung|anh[aä]ngerkupplung|tieferlegung", text, re.I):
        out["kind"] = "mods"
    elif labour and labour >= shop:
        out["kind"] = "service"
    elif shop:
        out["kind"] = "parts"
    elif _BUSINESS.search(text[:600]) and re.search(r"werkstatt|autohaus|garage|kfz|workshop", text[:600], re.I):
        out["kind"] = "service"
    if out["kind"] == "fixed":
        top = max(scores.items(), key=lambda kv: kv[1])
        if top[1]:
            out["fixed_kind"] = top[0]
        for name, pattern in _EVERY:
            if re.search(pattern, text, re.I):
                out["every"] = name
                break
        else:
            out["every"] = "year" if out["fixed_kind"] in ("insurance", "tax", "club") else "once"
    for key, pattern in _WORK:
        if re.search(pattern, text, re.I):
            out["work"] = key
            break
    return out


# ------------------------------------------------------------------ the text of an invoice

FIELDS = ("date", "amount", "vendor", "number", "odometer")  # what the page says was found


def parse(text: str, today: date | None = None) -> dict:
    """The invoice in a text: ``date``, ``amount`` (the total), ``net``, ``vat``, ``checked`` (net + VAT = gross), ``guess`` (the total is only the
    biggest figure), ``vendor``, ``number``, ``odometer``, ``kind`` (see KINDS) with ``fixed_kind`` / ``every`` / ``work``, ``doc_type`` (an estimate, a
    delivery note or a reminder is not an invoice), ``fuel`` (the refuel of a fuel receipt) and ``found`` - the names of the fields that were found."""
    today = today or date.today()
    lines = receipt._clean_text(text)
    out: dict = {
        "date": None,
        "amount": None,
        "net": None,
        "vat": None,
        "checked": False,
        "guess": False,
        "vendor": "",
        "number": "",
        "odometer": None,
        "kind": None,
        "fixed_kind": "other",
        "every": "once",
        "work": "",
        "doc_type": None,
        "fuel": None,
        "found": [],
    }
    if not lines:
        return out
    whole = "\n".join(lines)
    out.update(_total(lines))
    out["date"] = _date(lines, today)
    out["vendor"] = _vendor(lines)
    out["number"] = _number(lines)
    out["odometer"] = _odometer(lines)
    pump = receipt.parse(text, today)
    if pump["checked"] and pump["notes"] and not pump["derived"]:  # amount x price = total and a fuel named: a fuel receipt
        out["fuel"] = {k: pump[k] for k in ("date", "amount", "price_per_unit", "price_total", "station", "notes", "odometer")}
    out.update(_kind(whole, out["fuel"]))
    if not re.search(r"rechnung|invoice|quittung|beleg|receipt", whole, re.I):
        for name, pattern in _DOCTYPE:
            if re.search(pattern, whole, re.I):
                out["doc_type"] = name
                break
    out["found"] = [k for k in FIELDS if out[k]]
    return out


def _score(result: dict) -> int:
    return (5 if result["amount"] else 0) + (6 if result["checked"] else 0) + (3 if result["date"] else 0) + (1 if result["vendor"] else 0)


def _complete(result: dict) -> bool:
    return bool(result["amount"] and result["date"])


# ------------------------------------------------------------------ the text of a file


def pdf_texts(data: bytes) -> list[str]:
    """The text layer of the first pages of a PDF, read two ways (laid out like the page, and as the file holds it): which one keeps a label and its figure
    together differs from file to file, so both are parsed. [] for a PDF that cannot be opened."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):  # many invoices are "protected" with an empty password
        return []
    pages = list(reader.pages[:PDF_PAGES])
    out = []
    for layout in (True, False):
        parts = []
        for page in pages:
            try:
                parts.append((page.extract_text(extraction_mode="layout") if layout else page.extract_text()) or "")
            except Exception:
                parts.append("")
        out.append("\n".join(parts))
    return out


def _page_pictures(page) -> list[bytes]:
    try:
        return [image.data for image in page.images]
    except Exception:  # a picture in a format that cannot be decoded
        return []


def pdf_pictures(data: bytes, pages: int = 2, limit: int = 3) -> list[bytes]:
    """The pictures of the first pages of a PDF: a scan is one picture per page."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        return []
    pictures: list[bytes] = []
    for page in list(reader.pages[:pages]):
        pictures += _page_pictures(page)
    return pictures[:limit]


def ocr_image(data: bytes, today: date | None = None, second_try: bool = True) -> list[str]:
    """The text of a photo or a scan of an invoice (one reading, and another with a different page layout when the first lacks the date or the total).
    ValueError for a file that is no picture."""
    cleaned = receipt.deskew(receipt.clean(data, target=3000))
    with receipt._one_at_a_time:
        texts = [receipt.read_text(cleaned, 6)]
        if second_try and not _complete(parse(texts[0], today)):
            texts.append(receipt.read_text(cleaned, 4))
    return texts


def read(data: bytes, filename: str, today: date | None = None) -> dict:
    """A file of an invoice -> what it says (``parse``) and ``how`` it was read: ``pdf`` (its text), ``ocr`` (text recognition), ``text``, or '' when
    nothing could be read (an unknown kind of file, no text recognition installed, a damaged file). Never raises for a file that cannot be read."""
    ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    texts: list[str] = []
    how = ""
    try:
        if ext == ".pdf":
            texts, how = pdf_texts(data), "pdf"
            if not any(len(re.sub(r"\s", "", t)) >= 40 for t in texts) and receipt.available():  # a scan: no text, but a picture per page
                texts, how = [], "ocr"
                for picture in pdf_pictures(data):
                    try:
                        texts += ocr_image(picture, today, second_try=False)
                    except ValueError:
                        continue
        elif ext in IMAGE_EXT and receipt.available() and len(data) <= MAX_BYTES:
            texts, how = ocr_image(data, today), "ocr"
        elif ext == ".txt":
            texts, how = [data[:200_000].decode("utf-8", "replace")], "text"
    except Exception:
        texts, how = [], ""
    parsed = [parse(t, today) for t in texts if t and t.strip()]
    if not parsed:
        return {**parse("", today), "how": ""}
    best = max(parsed, key=_score)
    for other in parsed:  # what only another reading found is kept
        for key in ("date", "vendor", "number", "odometer"):
            if not best[key] and other[key]:
                best[key] = other[key]
    best["found"] = [k for k in FIELDS if best[k]]
    best["how"] = how
    return best
