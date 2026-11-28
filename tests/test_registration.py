"""Reading a registration certificate (the "Fahrzeugschein"): the parser on the rows of text that text recognition finds, the preparation of the picture, the
whole reading of made-up certificates (tools/practice_registration.py - nothing here is a real document), the route and the form of the vehicle pass.
The reading itself needs Tesseract: those tests are skipped without it (the CI has none)."""

import io
import json
import tempfile
from pathlib import Path

import pytest

from carassistant import db, receipt, registration

# ------------------------------------------------------------------ the rows of a page as text recognition finds them (with the junk of the small boxes)

LEFT = [
    "Zulassungsbescheinigung Teil |",
    "Nr. | XX-X-1-000/26-00000",
    "Certificate of registration. Part I / Certificat d'immatriculation. Partie I",
    "A Amtliches Kennzeichen",
    "XY Z 4567",
    "C.1.1 Name oder Firmenname",
    "Mustermann",
    "C.1.2 Vorname(n)",
    "Erika",
    "C.1.3 Anschrift",
    "Musterstraße 1",
    "12345 Musterstadt",
    "X Nächste HU | 09.2026",
    "Musterstadt",
    "01.01.2026",
]
MID = [
    "|, 02.09.2019 || 8888 L QRS00002 4",
    "al 1",
    "| SAMPLEV0987654321 | Pix",
    "°°) SAMPLE",
    "2B",
    "=] GHIJKL2",
    "UVW34DEF5G6H7I8JK9",
    "°3] SAMPLE SPARK",
    "*) SAMPLE (H)",
    "*} Fz.z.Pers.bef.b. 8 Spl",
    "Schragheck",
    "”) 715/2007°692/2008F",
    "*] EURO6;F:PI/Cl; M, N1 |",
    "=! Benzin",
    '*| 0001 | “t 35F0 | *"| 999',
    "al DATUM ZUR EMISSIONSKLASSE: 02.09.2019*",
]
RIGHT = [
    "2 | 1 | ‘ 70/5000 | 215",
    "4400-4500 | | 1800-1900",
    "1400-1500 | | 1 1050--",
    "112 | | 1560 | | 1560",
    "920 | | 790 | |",
    "920 | | 790 | |",
    "85 | | 3750 | | 74",
    "Oz | [5 [7]",
    "185/65 R15 88T",
    "185/65 R15 88T",
    "Rot | [] 7",
    "e1*2007/46*0000*00",
    "10.05.2019 | | K | | CD6543",
]
WHAT_IT_SAYS = {
    "plate": "XY-Z 4567",
    "first_reg": "2019-09-02",
    "hsn": "8888",
    "tsn": "QRS",
    "vin": "SAMPLEV0987654321",
    "make": "Sample",
    "model": "Spark",
    "model_type": "2B",
    "body_type": "hatchback",
    "fuel_type": "petrol",
    "displacement_ccm": "999",
    "power_kw": "70",
    "seats": "5",
    "gross_weight_kg": "1560",
    "color": "Rot",
}


def _parse(left=LEFT, mid=MID, right=RIGHT):
    return registration.parse({"left": left, "mid": mid, "right": right})


def test_the_rows_of_a_certificate_give_every_field_of_the_pass_despite_the_junk_of_the_small_boxes():
    got = _parse()
    assert got["fields"] == WHAT_IT_SAYS
    assert got["inspection"] == "2026-09"  # X: the month, not the date of issue under it


def test_the_holder_is_never_read():
    blob = json.dumps(_parse(), ensure_ascii=False)
    for word in ("Mustermann", "Erika", "Musterstra", "Musterstadt", "12345"):
        assert word not in blob
    assert not any("holder" in f or "owner" in f or f == "name" for f in registration.FIELDS)


def test_the_plate_is_the_row_below_its_label_and_the_number_of_the_document_is_none():
    assert registration.parse({"left": LEFT})["fields"]["plate"] == "XY-Z 4567"
    for text, want in (("WAF - AB 123 E", "WAF-AB 123E"), ("M-EV 99 H", "M-EV 99H"), ("B  CD 1", "B-CD 1")):
        assert registration.parse({"left": ["A Amtliches Kennzeichen", text]})["fields"]["plate"] == want
    assert "plate" not in registration.parse({"left": ["A Amtliches Kennzeichen", "XX-X-1-000/26-00000"]})["fields"]


def test_a_vin_is_found_when_letters_are_confused_or_the_row_is_split():
    for line in (
        "E | EXAMPLE1234567890",
        "EXAMPLEl234567890",
        "E EXAMPLE12345 67890",
        "EXAMPLE123456789O",
        "EEXAMPLE1234567890",
    ):  # l for 1, a space, an O, a code glued on
        mid = ["02.09.2019 8888 QRS", line, "EXAMPLE", "T4 TOURER", "EXAMPLE (H)"]
        assert registration.parse({"mid": mid})["fields"]["vin"] == "EXAMPLE1234567890", line
    # eighteen characters that are no VIN with a code in front (the version of the type is as long as that), and 16 characters, are none
    assert "vin" not in registration.parse({"mid": ["UVW34DEF5G6H7I8JK9", "EXAMPLE123456789"]})["fields"]


def test_a_regulation_number_is_no_power_and_nothing_is_taken_from_the_middle_page():
    got = _parse(right=["a | b", "11 | 22"])["fields"]  # the first row of the third page was not read
    assert "power_kw" not in got  # 715/2007 stands on the middle page
    assert _parse(right=["2 | 1 | 150/- | 215"])["fields"]["power_kw"] == "150"  # an electric car: no revolutions
    assert "power_kw" not in _parse(right=["2 | 1 | 715/2007*692/2008F | 215"])["fields"]


def test_the_make_is_the_word_that_comes_back_in_the_trade_name_and_the_short_name():
    mid = [*MID[:3], "Aa SAMPLE", *MID[3:]]  # a code of the box in front of the make
    assert registration.parse({"mid": mid})["fields"]["make"] == "Sample"
    lines = [
        "| SAMPLEV0987654321 | Pix",
        "AA",
        "2B",
        "GHIJKL2",
        "UVW34DEF5G6H7I8JK9",
        "SAMPLE SPARK",
        "SAMPLE (H)",
    ]  # the row of the make was not read
    assert (
        "make" not in registration.parse({"mid": lines})["fields"]
    )  # a two-letter code is no make, and nothing is guessed from the rows further down


def test_a_make_of_two_words_is_found_whole_and_taken_out_of_the_trade_name():
    mid = [*MID[:3], "EXAMPLE MOTORS", "2B", "GHIJKL2", "UVW34DEF5G6H7I8JK9", "aa] EXAMPLE MOTORS SPARK", "EXAMPLE MOTORS (H)", *MID[9:]]
    got = registration.parse({"mid": mid})["fields"]
    assert got["make"] == "Example Motors" and got["model"] == "Spark" and got["model_type"] == "2B"
    mid = [*MID[:3], "MERCEDES-X", "2B", "GHIJKL2", "UVW34DEF5G6H7I8JK9", "MERCEDES-X CLASS", "MERCEDES-X (H)", *MID[9:]]
    got = registration.parse({"mid": mid})["fields"]
    assert got["make"] == "Mercedes-X" and got["model"] == "Class"  # a hyphen belongs to the word


def test_two_colours_name_the_first_and_a_big_family_car_is_a_van():
    assert _parse(right=[*RIGHT[:10], "GRAU/SCHWARZ | [] 7", *RIGHT[11:]])["fields"]["color"] == "Grau"
    mid = [line if line != "Schragheck" else "Großraumlimousine" for line in MID]
    assert registration.parse({"mid": mid})["fields"]["body_type"] == "van"


def test_the_model_is_the_trade_name_without_the_make_and_the_junk_in_front_of_it():
    for trade, want in (("°3 SAMPLE SPARK", "Spark"), ("aa] SAMPLE T4 TOURER", "T4 Tourer"), ("SAMPLE GTI", "GTI"), ("SAMPLE (H)", None)):
        mid = [*MID[:7], trade, "SAMPLE (H)", *MID[9:]]
        got = registration.parse({"mid": mid})["fields"]
        assert got.get("model") == want, trade
    mid = [*MID[:7], "SAMPLE", "SAMPLE (H)", *MID[9:]]  # the trade name is the make alone: no model
    assert "model" not in registration.parse({"mid": mid})["fields"]


def test_the_type_is_a_short_code_and_the_long_variant_is_not_taken_for_it():
    assert registration.parse({"mid": MID})["fields"]["model_type"] == "2B"
    without = [line for line in MID if line != "2B"]  # the first row under the make was not read: the variant stands there now
    assert "model_type" not in registration.parse({"mid": without})["fields"]


def test_the_seats_are_a_digit_of_its_own_in_the_row_above_the_tyres():
    def seats(row, *extra):
        return _parse(right=[*RIGHT[:7], row, *RIGHT[8:], *extra])["fields"].get("seats")

    assert seats("- | [] - | [] 5 | [] -") == "5"
    assert seats("Oz | [5 [7]") == "5"  # a bracket glued to the digit, the box of the next cell on its own
    assert seats("| 5 | \\*7") == "5"  # the code of the next box read as 7 with other marks around it is no seat
    assert seats("aa | aa | aa") is None  # nothing read: nothing guessed
    assert seats("| \\*7") is None
    assert seats("- 5 7") is None  # two digits of their own: which one?


def test_the_permitted_mass_is_the_pair_of_numbers_or_the_last_number_of_its_row():
    def mass(row):
        return _parse(right=[*RIGHT[:3], row, *RIGHT[4:]])["fields"].get("gross_weight_kg")

    assert mass("112 | | 1560 | | 1560") == "1560"
    assert mass("- | 1560 | 1560") == "1560"
    assert mass("128 | 21 50 | 2150") == "2150"  # one of the two was read badly: the last number, after the small CO2 value
    assert mass("128 | 2160 | I 3150") == "3150"  # (the vote of the readings decides which of the guesses stays)
    assert mass("4400-4500 | | 1800-1900") is None  # measures, no mass
    assert mass("920 | 790") is None  # axle loads: the first number is not small


@pytest.mark.parametrize(
    ("rows", "fuel", "second", "ccm"),
    [
        (["P.3 Benzin", "10 0001 | 14.1 35F0 | P.1 999"], "petrol", None, "999"),
        (["P.3 Diesel", "10 0001 | P.1 1968"], "diesel", None, "1968"),
        (["P.3 Dlesel", "10 0001 | 14.1 35F0 | P.1 1968"], "diesel", None, "1968"),
        (["P.3 Elektro", "10 0001 | P.1 -"], "electric", None, None),
        (["P.3 Elektro/Benzin", "10 0001 | 14.1 35F0 | P.1 1498"], "hybrid", None, "1498"),
        (["P.3 Benzin/Erdgas", "10 0001 | 14.1 35F0 | P.1 1395"], "petrol", "cng", "1395"),
        (["P.3 Super", "0001 | 35F0 | 1598"], "petrol", None, "1598"),
        (
            ["P.3 Elektro", "10 0001 | 14.1 35F0 | P.1 3560"],
            "electric",
            None,
            None,
        ),  # an electric car has no displacement, whatever the row says
        (["P.3 Benzin", "10 0001 | 14.1 35F0 | P.1 -"], "petrol", None, None),  # a dash in the last cell
    ],
)
def test_the_fuel_the_second_fuel_and_the_displacement(rows, fuel, second, ccm):
    got = registration.parse({"mid": ["02.09.2019 8888 QRS", "E SAMPLEV0987654321", "SAMPLE", *rows]})["fields"]
    assert got["fuel_type"] == fuel
    assert got.get("fuel2_type") == second
    assert got.get("displacement_ccm") == ccm


def test_a_colour_word_with_a_misread_sharp_s_is_found():
    for word, want in (("Weiß", "Weiß"), ("WeiB", "Weiß"), ("WEISS", "Weiß"), ("Schwarz", "Schwarz"), ("Grün", "Grün"), ("Blau", "Blau")):
        assert _parse(right=[*RIGHT[:10], f"{word} | [] 7", *RIGHT[11:]])["fields"]["color"] == want, word
    assert "color" not in _parse(right=[*RIGHT[:10], "xyz", *RIGHT[11:]])["fields"]


def test_the_inspection_is_month_and_year_and_the_date_of_issue_is_none():
    assert registration.parse({"left": ["X Nächste HU", "12.2027", "Musterstadt", "01.01.2026"]})["inspection"] == "2027-12"
    assert registration.parse({"left": ["Musterstadt", "01.01.2026"]})["inspection"] == ""
    assert registration.parse({"left": ["X 13.2027"]})["inspection"] == ""  # no month 13


def test_a_page_that_is_no_certificate_gives_nothing():
    got = registration.parse({"all": ["Lorem ipsum dolor sit amet", "12.99", "Total 45,32 EUR", "Aral Heidelberg"]})
    assert got["fields"] == {} and got["inspection"] == ""


def test_the_first_row_gives_date_hsn_and_tsn_and_a_date_outside_the_years_of_cars_none():
    assert registration.parse({"mid": ["B 15,03.2016 | 2.1 9999 | 2.2 XYZ00001 3"]})["fields"] == {
        "first_reg": "2016-03-15",
        "hsn": "9999",
        "tsn": "XYZ",
    }
    assert "first_reg" not in registration.parse({"mid": ["B 15.03.1840 9999 XYZ"]})["fields"]
    assert "first_reg" not in registration.parse({"mid": ["B 31.02.2016 9999 XYZ"]})["fields"]  # no such day
    assert registration.parse({"mid": ["B 21 11 2023 | 9999 | XYZ00001 3"]})["fields"] == {
        "hsn": "9999",
        "tsn": "XYZ",
    }  # the dots of the date were lost: its year is no HSN
    assert registration.parse({"mid": ["B | 7777 | LMN00003 5"]})["fields"] == {
        "hsn": "7777",
        "tsn": "LMN",
    }  # no date at all: HSN and TSN still count


def test_the_parser_never_fails_on_odd_text():
    import random

    rng = random.Random(7)
    pages = [LEFT, MID, RIGHT]
    for page in pages:  # every beginning and every end of every page: a picture that was cut, a row that was not read
        for n in range(len(page) + 1):
            registration.parse({"left": page[:n], "mid": page[:n], "right": page[:n]})
            registration.parse({"all": page[n:]})
    alphabet = "AB1 2.|/-()[]*°e\\\n\tßÄü0O"
    for _ in range(300):
        rows = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40))) for _ in range(rng.randint(0, 14))]
        registration.parse({"left": rows, "mid": rows[::-1], "right": rows})
        registration.parse({"all": rows})
    assert registration.parse({}) == {"fields": {}, "inspection": "", "vin_score": 0, "alt": {}}


# ------------------------------------------------------------------ several readings


def _reading(fields, inspection="", vin_score=0):
    return {"fields": fields, "inspection": inspection, "vin_score": vin_score}


def test_the_readings_vote_a_number_must_be_exactly_right_and_a_word_may_have_lost_a_letter():
    merged = registration.merge(
        [
            _reading({"make": "Exampl", "power_kw": "110", "plate": "AB-CD 123"}),
            _reading({"make": "Example", "power_kw": "10", "plate": "AB-CD 123"}),
            _reading({"make": "Example", "power_kw": "110"}),
            _reading({"make": "Exampl", "power_kw": "110"}),
        ]
    )["fields"]
    assert (
        merged["make"] == "Example" and merged["power_kw"] == "110" and merged["plate"] == "AB-CD 123"
    )  # (Exampl, Example, Example, Exampl: the longer one of the group)
    # a word that is another word is no lost letter
    other = registration.merge([_reading({"color": "Rot"}), _reading({"color": "Rot"}), _reading({"color": "Blau"})])["fields"]
    assert other["color"] == "Rot"


def test_a_vin_that_looks_more_like_one_counts_more_and_the_first_reading_wins_a_tie():
    merged = registration.merge(
        [_reading({"vin": "AAAAAAAAAAAAAAAA1"}, vin_score=1), _reading({"vin": "BBBBBBBBBBBBBB123456"[:17]}, vin_score=5)]
    )["fields"]
    assert merged["vin"].startswith("B")
    tie = registration.merge([_reading({"hsn": "1111"}), _reading({"hsn": "2222"})])["fields"]
    assert tie["hsn"] == "1111"


def test_a_field_that_only_one_reading_found_is_unsure():
    one = registration.merge([_reading({"hsn": "1111", "plate": "AB-CD 123"}), _reading({"hsn": "1111"}), _reading({})])
    assert one["fields"] == {"plate": "AB-CD 123", "hsn": "1111"} and one["unsure"] == ["plate"]
    assert (
        registration.merge([_reading({"make": "Example"}), _reading({"make": "Exampl"})])["unsure"] == []
    )  # one lost letter: the same word twice


def test_the_seats_must_be_found_twice_or_they_are_not_offered():
    once = registration.merge([_reading({"seats": "5", "hsn": "1111"}), _reading({"hsn": "1111"}), _reading({"hsn": "1111"})])
    assert "seats" not in once["fields"] and once["unsure"] == []  # a lone digit among three readings: no seats rather than a wrong one
    twice = registration.merge([_reading({"seats": "5"}), _reading({"seats": "5"}), _reading({})])
    assert twice["fields"]["seats"] == "5" and twice["unsure"] == []
    assert (
        registration.merge([_reading({"seats": "5"}), _reading({})])["fields"]["seats"] == "5"
    )  # two readings only: as every other field, offered but unsure
    assert registration.merge([_reading({"seats": "5"}), _reading({})])["unsure"] == ["seats"]


def test_the_date_of_the_emission_class_is_a_second_reading_of_the_first_registration():
    def reading(b=None, alt=None):
        return {"fields": {"first_reg": b} if b else {}, "inspection": "", "alt": {"first_reg": alt} if alt else {}}

    assert (
        registration.merge([reading("2016-03-15", "2016-03-15"), reading()])["unsure"] == []
    )  # twice in one reading: it agrees with itself
    mixed = registration.merge([reading("2016-08-15", "2016-03-15"), reading("2016-03-15")])  # a digit of the first row misread once
    assert mixed["fields"]["first_reg"] == "2016-03-15" and mixed["unsure"] == []
    only = registration.merge([reading(None, "2016-03-15"), reading()])  # the row of the date itself was not read
    assert only["fields"]["first_reg"] == "2016-03-15" and only["unsure"] == ["first_reg"]
    both = registration.merge([reading("2016-03-15", "2017-01-01"), reading()])  # it is not always the same date: the first row wins
    assert both["fields"]["first_reg"] == "2016-03-15"


def test_the_month_of_the_inspection_is_the_one_most_readings_name():
    assert (
        registration.merge([_reading({}, "2027-06"), _reading({}, "2027-08"), _reading({}, "2027-06"), _reading({})])["inspection"]
        == "2027-06"
    )
    assert registration.merge([_reading({})])["inspection"] == ""
    assert registration.merge([_reading({}, "2027-06"), _reading({}), _reading({})])["unsure"] == [
        "inspection"
    ]  # read once: offered, but unsure


# ------------------------------------------------------------------ the picture


@pytest.fixture(scope="module")
def samples():
    import practice_registration as pr

    return {s.name: s for s in pr.samples()}


def test_the_paper_is_cut_out_of_the_photo_and_brought_to_one_width(samples):
    page = registration.paper(registration._open(samples["diesel-wagon"].data))
    assert (
        abs(page.width - registration.PAPER_WIDTH) < registration.PAPER_WIDTH * 0.1
    )  # (turned straight: the corners grow the picture a little)
    assert 1.8 < page.width / page.height < 2.2  # the folded certificate is twice as wide as high


def test_a_flat_scan_is_taken_as_it_is(samples):
    flat = registration._open(samples["diesel-wagon"].clean)
    page = registration.paper(flat)
    assert abs(page.width / page.height - flat.width / flat.height) < 0.05


def test_the_folds_between_the_three_pages_are_found(samples):
    page = registration.paper(registration._open(samples["petrol-hatchback"].data))
    where = registration.pages(registration.ink(page))
    w = page.width
    assert where["left"][0] == 0 and where["right"][1] == w
    assert 0.2 * w < where["left"][1] < 0.36 * w and 0.5 * w < where["mid"][1] < 0.72 * w
    assert where["left"][1] < where["mid"][0] < where["mid"][1] < where["right"][0] < where["right"][1]


def test_a_page_that_leans_is_turned_level_and_its_ruling_lines_are_taken_out(samples):
    from PIL import Image

    page = registration.paper(registration._open(samples["petrol-hatchback"].data))
    binary = registration.ink(page)
    x0, x1 = registration.pages(binary)["mid"]
    mid = binary.crop((x0, 0, x1, binary.height))

    def evenness(img):
        return sum(share * share for share in registration._dark(img, 1))

    leaning = mid.rotate(2.4, resample=Image.BICUBIC, fillcolor=255)
    level = registration.level(leaning)
    assert evenness(level) > evenness(leaning) * 1.15  # the rows of ink stand out again
    cleaned = registration.clean_page(registration.level(mid))
    lines_before = sum(1 for share in registration._dark(registration.level(mid), 1) if share >= 0.5)
    assert lines_before >= 5 and not any(
        share >= 0.5 for share in registration._dark(cleaned, 1)
    )  # the ruling lines of the full width are gone
    assert registration.level(mid).size == mid.size


def test_a_picture_that_is_no_picture_is_refused_and_a_picture_that_is_too_big_too():
    with pytest.raises(ValueError):
        registration.scan(b"this is not an image")
    with pytest.raises(ValueError):
        registration.scan(b"x" * (registration.MAX_BYTES + 1))
    with pytest.raises(ValueError):
        registration.scan_file(b"x" * (registration.MAX_BYTES + 1))


# ------------------------------------------------------------------ the whole reading of the made-up certificates

needs_tesseract = pytest.mark.skipif(not receipt.available(), reason="Tesseract is not installed")
KEY = ("plate", "vin", "first_reg", "hsn", "tsn", "make", "fuel_type", "power_kw")


@needs_tesseract
@pytest.mark.parametrize("name", ["diesel-wagon", "petrol-hatchback", "electric-suv"])
@pytest.mark.parametrize("kind", ["clean", "photo"])
def test_the_made_up_certificates_are_read_right_and_nothing_wrong_is_offered(samples, name, kind):
    sample = samples[name]
    got = registration.scan(sample.clean if kind == "clean" else sample.data)
    wrong = {k: (v, sample.truth.get(k)) for k, v in got["fields"].items() if sample.truth.get(k) != v}
    assert not wrong, wrong  # a field that is missing is bad, a field that is wrong is worse
    assert set(KEY) <= set(got["fields"]), sorted(set(KEY) - set(got["fields"]))
    assert len(got["fields"]) >= len(sample.truth) - 2
    assert got["inspection"] == sample.inspection
    assert got["found"] == [k for k in registration.FIELDS if k in got["fields"]]
    assert set(got["unsure"]) <= set(got["fields"]) | {"inspection"}


@needs_tesseract
def test_a_certificate_comes_out_without_its_holder_and_leaves_no_picture_behind(samples):
    before = {p.name for p in Path(tempfile.gettempdir()).glob("ca-registration-*")}
    blob = json.dumps(registration.scan(samples["diesel-wagon"].data), ensure_ascii=False)
    for word in ("Mustermann", "Erika", "Musterstra", "Musterstadt"):
        assert word not in blob
    assert {p.name for p in Path(tempfile.gettempdir()).glob("ca-registration-*")} == before


@needs_tesseract
@pytest.mark.parametrize("turn", [90, 270, 180])
def test_a_certificate_that_lies_on_its_side_or_upside_down_is_turned_upright(samples, turn):
    from PIL import Image

    flat = Image.open(io.BytesIO(samples["diesel-wagon"].clean)).convert("RGB").rotate(turn, expand=True)
    out = io.BytesIO()
    flat.save(out, "PNG")
    got = registration.scan(out.getvalue())["fields"]
    truth = samples["diesel-wagon"].truth
    assert all(got.get(k) == truth[k] for k in ("plate", "vin", "first_reg", "hsn", "make", "power_kw")), got


@needs_tesseract
def test_a_pdf_of_the_certificate_is_read_like_a_photo(samples):
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(samples["diesel-wagon"].clean)).convert("RGB").save(out, "PDF")
    got = registration.scan_file(out.getvalue())
    assert got["fields"].get("vin") == "EXAMPLE1234567890" and got["fields"].get("plate") == "AB-CD 123"


@needs_tesseract
def test_a_picture_of_something_else_finds_nothing_and_stops_early():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1600, 900), (230, 230, 230))
    ImageDraw.Draw(img).text((200, 400), "Some other paper without any field of a certificate", fill=(20, 20, 20))
    out = io.BytesIO()
    img.save(out, "JPEG")
    got = registration.scan(out.getvalue())
    assert got["fields"] == {} and got["found"] == [] and got["readings"] <= 3


# ------------------------------------------------------------------ the route and the form


def test_the_scan_route_hands_the_fields_over_and_keeps_nothing(client, monkeypatch):
    fake = {"fields": {"plate": "AB-CD 123"}, "found": ["plate"], "unsure": [], "inspection": "2027-06", "readings": 3}
    monkeypatch.setattr(receipt, "available", lambda: True)
    seen = []
    monkeypatch.setattr(registration, "scan_file", lambda data: seen.append(data) or fake)
    r = client.post("/registration/scan", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200 and r.json() == fake and r.headers["cache-control"] == "no-store"
    assert seen == [b"\xff\xd8\xff"]
    monkeypatch.setattr(registration, "scan_file", lambda data: (_ for _ in ()).throw(ValueError("not an image")))
    assert client.post("/registration/scan", content=b"x").status_code == 400
    monkeypatch.setattr(receipt, "available", lambda: False)
    assert client.post("/registration/scan", content=b"x").status_code == 501


def test_the_form_of_the_pass_offers_the_scan_only_where_text_recognition_is_installed(client, monkeypatch):
    client.post("/vehicles", data={"name": "Scan Car", "fuel_type": "diesel"})
    monkeypatch.setattr(receipt, "available", lambda: True)
    for url in ("/vehicles/new", "/v/scan-car/edit?mode=form"):
        page = client.get(url).text
        assert "data-regscan" in page and "registration.js" in page and "data-reg-file=" in page, url
        assert 'name="reg_inspection"' in page
    assert 'data-new="1"' in client.get("/vehicles/new").text and 'data-new="0"' in client.get("/v/scan-car/edit?mode=form").text
    monkeypatch.setattr(receipt, "available", lambda: False)
    for url in ("/vehicles/new", "/v/scan-car/edit?mode=form"):
        page = client.get(url).text
        assert "data-regscan" not in page and "registration.js" not in page, url


def _appointments(vid):
    with db.tx() as conn:
        return [
            dict(r) for r in conn.execute("SELECT kind, title, due_date, month_only, done FROM appointments WHERE vehicle_id = ?", (vid,))
        ]


def test_the_next_inspection_of_the_certificate_becomes_an_appointment_when_the_car_has_none(client):
    client.post("/vehicles", data={"name": "Cert Car", "fuel_type": "petrol", "reg_inspection": "2027-06"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles WHERE name = 'Cert Car'").fetchone()["id"]
    got = _appointments(vid)
    assert (
        len(got) == 1
        and got[0]["kind"] == "inspection"
        and got[0]["due_date"] == "2027-06-30"
        and got[0]["month_only"] == 1
        and got[0]["done"] == 0
    )
    assert got[0]["title"] == "Inspection (TÜV / MOT)"
    # saving the pass again with the same month adds nothing: there is an open inspection appointment
    client.post(f"/v/{vid}/edit", data={"name": "Cert Car", "fuel_type": "petrol", "reg_inspection": "2028-01"})
    assert len(_appointments(vid)) == 1 and _appointments(vid)[0]["due_date"] == "2027-06-30"  # what is there stays
    # a done one does not count
    with db.tx() as conn:
        conn.execute("UPDATE appointments SET done = 1 WHERE vehicle_id = ?", (vid,))
    client.post(f"/v/{vid}/edit", data={"name": "Cert Car", "fuel_type": "petrol", "reg_inspection": "2028-01"})
    assert sorted(a["due_date"] for a in _appointments(vid)) == ["2027-06-30", "2028-01-31"]


def test_a_month_that_is_none_adds_no_appointment(client):
    for n, bad in enumerate(("", "2027-13", "abc", "2027-6", "1850-01", "2027-06-15", "20270600")):
        client.post("/vehicles", data={"name": f"Bad {n}", "fuel_type": "petrol", "reg_inspection": bad})
        with db.tx() as conn:
            vid = conn.execute("SELECT id FROM vehicles WHERE name = ?", (f"Bad {n}",)).fetchone()["id"]
        assert _appointments(vid) == [], bad


def test_a_form_that_fails_adds_no_appointment(client):
    r = client.post("/vehicles", data={"name": "", "fuel_type": "petrol", "reg_inspection": "2027-06"})  # the name is a must
    assert r.status_code == 400
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0


def test_the_texts_of_the_scan_are_in_both_languages():
    from carassistant import i18n

    keys = [k for k in i18n.EN if k.startswith("reg.")]
    assert len(keys) >= 12
    assert all(k in i18n.DE for k in keys)
    for key, placeholder in (
        ("reg.ok", "{n}"),
        ("reg.diff", "{list}"),
        ("reg.inspection", "{month}"),
        ("reg.inspection_unsure", "{month}"),
        ("reg.inspection_have", "{month}"),
    ):  # the script fills these in: both languages must carry them
        assert placeholder in i18n.EN[key] and placeholder in i18n.DE[key], key
