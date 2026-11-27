"""Reading an invoice: the parser on the text of a PDF or a photo (no file needed), the PDF reader, and the text recognition on a made-up photo."""

import io
from datetime import date

import pytest

from carassistant import invoice, receipt

TODAY = date(2026, 11, 27)

WORKSHOP = """
Autohaus Beispiel GmbH · Musterweg 1 · 12345 Musterstadt
Herr Max Mustermann
Musterstraße 5
12345 Musterstadt

Rechnung Nr. 2026-0815
Rechnungsdatum: 12.03.2026
Kennzeichen: AB-CD 123
Erstzulassung: 03.2018
km-Stand: 86.020
Nächste HU: 05/2028

Pos  Bezeichnung                       Menge   Preis     Betrag
1    Inspektion nach Herstellervorgabe  1,00   189,00    189,00
2    Ölfilter                           1,00    14,50     14,50
3    Motoröl 5W-30 Arbeitslohn          1,00    29,30     29,30

Summe netto                                              232,80
zzgl. 19% MwSt                                            44,23
Gesamtbetrag                                             277,03 EUR
Zahlbar bis 26.03.2026 ohne Abzug
"""

COLUMNS = """
Werkstatt Meier KG
Rechnungsdatum
12.03.2026
Rechnung Nr. R-77
Nettobetrag
232,80
MwSt 19 %
44,23
Rechnungsbetrag
277,03
"""

TABLE = """
Reifen Schmidt e.K.
Rechnung 2026/55 vom 02.11.2026
Reifenwechsel und Montage, 4 Räder

Nettobetrag     MwSt. 19%     Gesamtbetrag
84,03           15,97         100,00
"""

ENGLISH = """
Spare Parts Ltd
Invoice No: INV-20933
Invoice date: 5 March 2026
Order number 88231
Brake discs front (part no. 4B0615301)      2 x 89.50      179.00
Brake pads                                                  64.90
Shipping                                                     9.90
Subtotal                                                 1,094.13
VAT 19%                                                    207.89
Total                                                    1,302.02
"""

INSURANCE = """
Beispiel Versicherung AG
Beitragsrechnung zur Kfz-Haftpflicht- und Vollkaskoversicherung
Rechnungsdatum: 02.01.2026
Beitrag                                            349,00 EUR
Versicherungssteuer 19 %                            66,31 EUR
Gesamtbeitrag jährlich                             415,31 EUR
"""

ARAL = """
ARAL Tankstelle
Musterstrasse 12
12345 Musterstadt

Datum: 21.11.2026   Uhrzeit 17:42
Zapfsaeule 4
Super E10      45,32 l
Preis/l        1,789 EUR/l
Gesamtbetrag   81,08 EUR
MwSt 19%       12,95 EUR
"""


def test_amounts_in_german_and_english_writing_but_never_dates_or_rates():
    assert invoice._amounts("Gesamt 1.234,56 EUR") == [1234.56]
    assert invoice._amounts("Total 1,234.56") == [1234.56]
    assert invoice._amounts("Summe 277,03") == [277.03]
    assert invoice._amounts("Rechnung vom 12.03.2026, MwSt 19,00 % Erstzulassung 03.2018") == []
    assert invoice._amounts("2 x 89.50 = 179.00") == [89.5, 179.0]
    assert invoice._amounts("1 234,56".replace(" ", " ")) == [1234.56]


def test_a_workshop_invoice_is_read_completely():
    r = invoice.parse(WORKSHOP, TODAY)
    assert r["amount"] == 277.03 and r["net"] == 232.8 and r["vat"] == 44.23 and r["checked"] and not r["guess"]
    assert r["date"] == "2026-03-12"  # not the due date, not the registration, not the next inspection
    assert r["vendor"] == "Autohaus Beispiel GmbH"
    assert r["number"] == "2026-0815"
    assert r["odometer"] == 86020
    assert r["kind"] == "service" and r["work"] == "inspection"
    assert r["found"] == ["date", "amount", "vendor", "number", "odometer"]


def test_labels_and_figures_on_lines_of_their_own_are_put_together():
    r = invoice.parse(COLUMNS, TODAY)
    assert (r["amount"], r["net"], r["vat"], r["checked"]) == (277.03, 232.8, 44.23, True)
    assert r["date"] == "2026-03-12" and r["vendor"] == "Werkstatt Meier KG" and r["number"] == "R-77"


def test_a_table_with_net_vat_and_gross_over_their_figures():
    r = invoice.parse(TABLE, TODAY)
    assert (r["amount"], r["net"], r["vat"], r["checked"]) == (100.0, 84.03, 15.97, True)
    assert r["date"] == "2026-11-02" and r["vendor"] == "Reifen Schmidt e.K." and r["work"] == "tyres"


def test_an_english_invoice_with_thousands_and_a_total_that_adds_up():
    r = invoice.parse(ENGLISH, TODAY)
    assert r["date"] == "2026-03-05" and r["number"] == "INV-20933" and r["vendor"] == "Spare Parts Ltd"
    assert r["kind"] == "parts"
    assert (r["amount"], r["net"], r["vat"], r["checked"]) == (1302.02, 1094.13, 207.89, True)


def test_a_total_that_does_not_add_up_is_offered_but_not_checked():
    r = invoice.parse("Foo GmbH\nRechnungsdatum 01.11.2026\nSumme netto 100,00\nMwSt 19% 19,00\nGesamtbetrag 129,00 EUR", TODAY)
    assert r["amount"] == 129.0 and r["checked"] is False and r["guess"] is False  # the page shows it plainly, the person looks


def test_an_insurance_invoice_is_a_yearly_fixed_cost():
    r = invoice.parse(INSURANCE, TODAY)
    assert r["amount"] == 415.31 and r["date"] == "2026-01-02"
    assert (r["kind"], r["fixed_kind"], r["every"]) == ("fixed", "insurance", "year")


def test_a_fuel_receipt_is_a_refuel():
    r = invoice.parse(ARAL, TODAY)
    assert r["kind"] == "fuel" and r["fuel"]["amount"] == 45.32 and r["fuel"]["price_per_unit"] == 1.789
    assert r["amount"] == 81.08 and r["date"] == "2026-11-21"


def test_an_estimate_is_not_an_invoice():
    r = invoice.parse("Autohaus X GmbH\nKostenvoranschlag Nr. 5\nDatum: 01.11.2026\nGesamtbetrag 900,00 EUR", TODAY)
    assert r["doc_type"] == "estimate"
    assert invoice.parse(WORKSHOP, TODAY)["doc_type"] is None


def test_without_a_label_the_biggest_figure_is_a_guess_and_says_so():
    r = invoice.parse("Foo GmbH\nDatum 01.11.2026\nBremsen 10,00\nBelag 55,50\n", TODAY)
    assert r["amount"] == 55.5 and r["guess"] is True and r["checked"] is False


def test_a_text_without_anything_is_an_empty_result():
    r = invoice.parse("", TODAY)
    assert r["found"] == [] and r["amount"] is None and r["kind"] is None
    r = invoice.parse("nothing to see here", TODAY)
    assert r["found"] == [] and r["amount"] is None


def test_dates_in_other_writings():
    d = lambda text: invoice._date(receipt._clean_text(text), TODAY)  # noqa: E731
    assert d("Date: 2026-03-05") == "2026-03-05"
    assert d("Datum 5. März 2026") == "2026-03-05"
    assert d("Date: March 5, 2026") == "2026-03-05"
    assert d("Date 03/25/2026") == "2026-03-25"  # the second number cannot be a month: American writing
    assert d("fällig am 01.12.2026") is None  # a due date is not the date of the invoice
    assert d("Datum 01.01.1999") is None
    assert d("Datum 01.12.2026") is None  # in the future


def _pdf(text_lines: list[str]) -> bytes:
    """A small PDF with a text layer (one page, Helvetica) - made by hand, so that the test needs no PDF library to write one."""
    content = (
        "BT /F1 11 Tf 40 780 Td 14 TL " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj T*" for line in text_lines) + " ET"
    )
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_a_pdf_with_a_text_layer_is_read_without_text_recognition():
    lines = [line for line in WORKSHOP.strip().split("\n") if line.strip()]
    r = invoice.read(_pdf(lines), "rechnung.pdf", TODAY)
    assert r["how"] == "pdf"
    assert r["amount"] == 277.03 and r["checked"] and r["date"] == "2026-03-12" and r["odometer"] == 86020
    assert r["vendor"] == "Autohaus Beispiel GmbH"


def test_files_that_cannot_be_read_give_an_empty_result_and_no_error():
    assert invoice.read(b"%PDF-1.4 broken", "x.pdf", TODAY)["how"] == ""
    assert invoice.read(b"not a picture", "x.jpg", TODAY)["found"] == []
    assert invoice.read(b"anything", "x.csv", TODAY)["how"] == ""
    assert invoice.read(b"Rechnungsdatum 12.03.2026\nGesamtbetrag 10,00", "x.txt", TODAY)["amount"] == 10.0


def _page_photo(lines: list[str], size: int = 34) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size)
    img = Image.new("L", (1800, 60 + (size + 18) * len(lines)), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((60, 40 + i * (size + 18)), line, fill=0, font=font)
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


@pytest.mark.skipif(not receipt.available(), reason="Tesseract is not installed")
def test_a_photo_of_an_invoice_is_read_by_text_recognition():
    lines = [
        "Autohaus Beispiel GmbH",
        "Rechnung Nr. 2026-0815",
        "Rechnungsdatum: 12.03.2026",
        "km-Stand: 86020",
        "Inspektion nach Herstellervorgabe    189,00",
        "Summe netto    232,80",
        "zzgl. 19% MwSt    44,23",
        "Gesamtbetrag    277,03 EUR",
    ]
    r = invoice.read(_page_photo(lines), "scan.jpg", TODAY)
    assert r["how"] == "ocr"
    assert r["amount"] == 277.03 and r["date"] == "2026-03-12"
    assert r["vendor"] == "Autohaus Beispiel GmbH" and r["kind"] == "service"


@pytest.mark.skipif(not receipt.available(), reason="Tesseract is not installed")
def test_a_scanned_pdf_is_read_through_the_picture_on_its_page():
    from PIL import Image

    lines = ["Werkstatt Meier KG", "Rechnungsdatum: 12.03.2026", "Gesamtbetrag    277,03 EUR"]
    photo = Image.open(io.BytesIO(_page_photo(lines)))
    out = io.BytesIO()
    photo.save(out, "PDF")  # a picture on a page, no text layer: what a scanner makes
    r = invoice.read(out.getvalue(), "scan.pdf", TODAY)
    assert r["how"] == "ocr" and r["amount"] == 277.03 and r["date"] == "2026-03-12"


# ------------------------------------------------------------------ the pages: upload, read, book


def _upload(client, vid, name, data, mime="application/pdf"):
    from tests.test_web import slug

    return client.post(f"/v/{slug(vid)}/invoices", files={"file": (name, data, mime)}, follow_redirects=False)


def _invoice_pdf():
    lines = [line for line in WORKSHOP.strip().split("\n") if line.strip()]
    return _pdf(lines)


def test_an_invoice_is_uploaded_read_and_booked_as_a_service_entry(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client, "Invoice Car")
    base = f"/v/{slug(vid)}"
    assert "Invoices" in client.get(f"{base}/invoices").text  # the tab, and an empty page that says what to do
    done = _upload(client, vid, "scan.pdf", _invoice_pdf())
    assert done.status_code == 303 and "/invoices/" in done.headers["location"]
    with db.tx() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()
    assert (
        doc["category"] == "invoice"
        and doc["amount"] == 277.03
        and doc["doc_date"] == "2026-03-12"
        and doc["title"].startswith("Autohaus Beispiel")
    )
    page = client.get(f"{base}/invoices/{doc['id']}")
    assert page.status_code == 200 and "277.03" in page.text and "the figures add up" in page.text and "Book as" in page.text
    # booking opens the form of the kind, filled in
    form = client.get(f"{base}/e/service?invoice={doc['id']}").text
    assert 'name="invoice"' in form and 'value="Autohaus Beispiel GmbH"' in form and 'value="277.03"' in form and "2026-03-12" in form
    saved = client.post(
        f"{base}/e/service",
        data={
            "invoice": str(doc["id"]),
            "date": "2026-03-12",
            "title": "Inspection",
            "workshop": "Autohaus Beispiel GmbH",
            "cost": "277.03",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303 and f"/invoices/{doc['id']}" in saved.headers["location"]
    with db.tx() as conn:
        entry = conn.execute("SELECT id, cost FROM service WHERE vehicle_id = ?", (vid,)).fetchone()
        linked = conn.execute("SELECT booked_table, booked_id FROM documents WHERE id = ?", (doc["id"],)).fetchone()
    assert entry["cost"] == 277.03 and (linked["booked_table"], linked["booked_id"]) == ("service", entry["id"])
    assert "Booked as Service" in client.get(f"{base}/invoices/{doc['id']}").text
    assert "Booked" in client.get(f"{base}/invoices").text
    # the entry is deleted: the invoice is to be booked again
    client.post(f"{base}/e/service/{entry['id']}/delete")
    with db.tx() as conn:
        assert conn.execute("SELECT booked_table FROM documents WHERE id = ?", (doc["id"],)).fetchone()[0] is None
    assert "To book" in client.get(f"{base}/invoices").text


def test_the_same_file_is_not_stored_twice_and_odd_files_are_refused(client):
    from tests.test_web import create_vehicle

    from carassistant import db

    vid = create_vehicle(client, "Twice Car")
    first = _upload(client, vid, "a.pdf", _invoice_pdf())
    again = _upload(client, vid, "b.pdf", _invoice_pdf())
    assert first.headers["location"].split("?")[0] == again.headers["location"].split("?")[0]  # the same invoice
    assert "inv_again" in again.headers["location"]
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 1
    assert "err.file_type" in _upload(client, vid, "virus.exe", b"MZ").headers["location"]
    assert "err.file_type" in _upload(client, vid, "page.html", b"<script>1</script>", "text/html").headers["location"]


def test_an_unreadable_file_is_kept_and_can_still_be_booked(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client, "Blank Car")
    done = _upload(client, vid, "photo.jpg", b"not really a picture", "image/jpeg")
    assert done.status_code == 303
    with db.tx() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()
    page = client.get(f"/v/{slug(vid)}/invoices/{doc['id']}")
    assert "Nothing could be read" in page.text
    assert client.get(f"/v/{slug(vid)}/e/service?invoice={doc['id']}").status_code == 200  # an empty form, still linked to the invoice
    # an invoice of another car cannot be used
    other = create_vehicle(client, "Other Car")
    assert 'name="invoice"' not in client.get(f"/v/{slug(other)}/e/service?invoice={doc['id']}").text
    assert client.get(f"/v/{slug(other)}/invoices/{doc['id']}").status_code == 404


def test_a_fixed_cost_and_a_refuel_are_booked_from_their_invoices(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db

    vid = create_vehicle(client, "Kinds Car")
    base = f"/v/{slug(vid)}"
    _upload(client, vid, "ins.txt", INSURANCE.encode(), "text/plain")
    _upload(client, vid, "tank.txt", ARAL.encode(), "text/plain")
    with db.tx() as conn:
        ids = {r["filename"]: r["id"] for r in conn.execute("SELECT id, filename FROM documents WHERE vehicle_id = ?", (vid,))}
    fixed = client.get(f"{base}/e/fixed?invoice={ids['ins.txt']}").text
    assert 'value="415.31"' in fixed and 'value="2026-01-02"' in fixed and "selected" in fixed
    fuel = client.get(f"{base}/e/fuel?invoice={ids['tank.txt']}").text
    assert 'name="invoice"' in fuel and "45.32" in fuel and "1.789" in fuel and "81.08" in fuel
    assert (
        client.post(
            f"{base}/e/fixed",
            data={
                "invoice": str(ids["ins.txt"]),
                "title": "Insurance",
                "cost_kind": "insurance",
                "cost": "415.31",
                "every": "year",
                "start_date": "2026-01-02",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    with db.tx() as conn:
        assert conn.execute("SELECT booked_table FROM documents WHERE id = ?", (ids["ins.txt"],)).fetchone()[0] == "fixed_costs"


def test_the_invoice_file_is_shown_with_its_own_type_and_the_tab_follows_the_cost_page_switch(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, modules

    vid = create_vehicle(client, "Switch Car")
    base = f"/v/{slug(vid)}"
    _upload(client, vid, "r.pdf", _invoice_pdf())
    with db.tx() as conn:
        doc_id = conn.execute("SELECT id FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()[0]
    got = client.get(f"{base}/invoices/{doc_id}/file")
    assert (
        got.status_code == 200 and got.headers["content-type"] == "application/pdf" and got.headers["x-content-type-options"] == "nosniff"
    )
    tabs = client.get(f"{base}/invoices").text.split('<nav class="seg-tabs')[1].split("</nav>")[0]
    assert tabs.count("<svg") == 3 and f'href="{base}/invoices" class="on"' in tabs  # Overview | Fixed costs | Invoices
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "report", False)
    assert client.get(f"{base}/invoices").status_code == 404


def test_deleting_an_invoice_keeps_the_entry_and_the_backup_keeps_the_link(client):
    from tests.test_web import create_vehicle, slug

    from carassistant import db, vehiclebackup

    vid = create_vehicle(client, "Backup Car")
    base = f"/v/{slug(vid)}"
    _upload(client, vid, "r.pdf", _invoice_pdf())
    with db.tx() as conn:
        doc_id = conn.execute("SELECT id FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()[0]
    client.post(f"{base}/e/service", data={"invoice": str(doc_id), "date": "2026-03-12", "title": "Inspection", "cost": "10"})
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
    # the car comes back under new numbers: the invoice still points at its entry
    with db.tx() as conn:
        new_vid = vehiclebackup.restore(conn, raw)
    with db.tx() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE vehicle_id = ?", (new_vid,)).fetchone()
        entry = conn.execute("SELECT id FROM service WHERE vehicle_id = ?", (new_vid,)).fetchone()
    assert doc["booked_table"] == "service" and doc["booked_id"] == entry["id"] and doc["amount"] == 277.03
    client.post(f"{base}/invoices/{doc_id}/delete")
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM service WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE vehicle_id = ?", (vid,)).fetchone()[0] == 0
