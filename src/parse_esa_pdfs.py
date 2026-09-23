"""Turn the two PDF-only federal sources into JSON.

    python parse_esa_pdfs.py          (after fetch_noaa_data.py)

Writes raw/expenditures.json and raw/sar_atlantic.json.

Neither source has a machine-readable release, so both are parsed out of the
published PDF's text layer with pypdf. Both parsers are *self-checking*: they
refuse to write a file whose numbers do not reconcile against a total the
document itself prints. That is the only defence against a silently truncated
parse, which is the failure mode that matters here -- a table that stops
halfway still looks entirely plausible.
"""
import json
import re
import sys
from pathlib import Path

import pypdf

RAW = Path(__file__).parent / "raw"

# ---------------------------------------------------------------------------
# 1. FWS Report to Congress, Table 2: expenditures per listed entity
# ---------------------------------------------------------------------------
# A row is one listing entity and reads:
#
#   <rank> <common name> (<scientific name>) - <population> <status> $<total> $<cumulative>
#
# with the whole thing wrapped across as many as five lines. Rather than try to
# rebuild the line breaks, the parser flattens each table to one string and
# uses the *pair* of dollar figures as the row terminator: every row ends with
# exactly one, and nothing else in the table does.
#
# The cumulative column then validates the parse for free. Cumulative is a
# running sum of the total column, so it must never decrease, and the last row's
# cumulative must equal the sum of every total. FY2019 prints cents and
# reconciles to the penny; FY2020-22 print whole dollars and drift by a few
# dollars of rounding, which the tolerance below allows for.
MONEY_PAIR = re.compile(r"\$([\d,]+(?:\.\d\d)?)\s+\$([\d,]+(?:\.\d\d)?)")
STATUS_TOKENS = {
    "E", "T", "C", "EXPN", "EXP N", "XN", "XE", "SAE", "SAT", "PE", "PT",
    "E(S/A)", "T(S/A)", "EmE", "EmT",
}


def _flatten_table2(reader):
    """Return the text of Table 2 as one line, and the total it prints itself."""
    start = end = None
    for i, page in enumerate(reader.pages):
        head = [" ".join(l.split()) for l in (page.extract_text() or "").split("\n")[:3]]
        for line in head:
            if line.startswith("TABLE 2.") and start is None:
                start = i
            elif start is not None and end is None and re.match(r"TABLE [34]\.", line):
                end = i
    if start is None:
        sys.exit("could not find TABLE 2 -- the report's layout has changed")
    if end is None:
        end = len(reader.pages)

    chunks, stated_total, started = [], None, False
    for i in range(start, end):
        for line in (reader.pages[i].extract_text() or "").split("\n"):
            line = " ".join(line.split())
            if not line:
                continue
            # FY2021 prints two paragraphs of preamble between the table's
            # title and its first row. Nothing counts until the column header
            # appears, or the preamble's own mention of "Table 1" gets glued
            # to the front of rank 1 and takes a $61m row's name with it.
            if not started:
                started = line.startswith("Rank Species")
                continue
            # The table's own grand total, printed once at the end. Everything
            # after it belongs to the next section.
            m = re.match(r"Total Ranked Species Expenditures\s+\$([\d,]+(?:\.\d\d)?)", line)
            if m:
                stated_total = float(m.group(1).replace(",", ""))
                return " ".join(chunks), stated_total
            if (line.startswith("TABLE ") or line.startswith("Rank Species")
                    or line.startswith("NOT INCLUDING")):
                continue
            chunks.append(line)
    return " ".join(chunks), stated_total


def _split_name(segment):
    """'123 Salmon, Chinook (Oncorhynchus (=Salmo) tshawytscha) - Puget Sound ESU T'
    -> ('Salmon, Chinook', 'Oncorhynchus (=Salmo) tshawytscha', 'Puget Sound ESU')

    The scientific name is the first balanced parenthesis group that opens with
    a capitalised genus. Scanning for balance rather than regex-matching matters
    because plenty of these names contain a nested group of their own --
    'Physeter catodon (=macrocephalus)', 'Dipodomys stephensi (incl. D. cascus)'.
    """
    segment = re.sub(r"^\d{1,4}\s+", "", segment).strip()
    depth = open_at = 0
    for i, ch in enumerate(segment):
        if ch == "(":
            if depth == 0:
                open_at = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                inner = segment[open_at + 1:i]
                if re.match(r"^[A-Z][a-z]", inner) and (" " in inner):
                    common = segment[:open_at].strip(" ,-")
                    rest = segment[i + 1:].strip(" -–")
                    # The status code is the last token, but a population can
                    # legitimately end in a capital ("...DPS"), so only strip
                    # tokens that are actual status codes.
                    tokens = rest.split()
                    while tokens and tokens[-1] in STATUS_TOKENS:
                        tokens.pop()
                    if len(tokens) >= 2 and " ".join(tokens[-2:]) in STATUS_TOKENS:
                        tokens = tokens[:-2]
                    population = " ".join(tokens).strip(" -,")
                    # FY2021 and FY2022 append a regulatory cross-reference to
                    # the population cell; it is the same string for every
                    # NMFS-led entity and carries no information.
                    population = re.sub(r"\s*[-–]?\s*See 50 CFR [\d.]+\s*$", "", population)
                    return common, inner.strip(), population.strip(" -,")
    return segment, None, ""


def parse_expenditures():
    years = sorted(int(p.stem.split("fy")[1]) for p in RAW.glob("expenditures_fy*.pdf"))
    if not years:
        sys.exit("no raw/expenditures_fy*.pdf -- run fetch_noaa_data.py first")
    out = {}
    for year in years:
        reader = pypdf.PdfReader(RAW / f"expenditures_fy{year}.pdf")
        text, stated_total = _flatten_table2(reader)

        rows, pos, running = [], 0, -1.0
        for m in MONEY_PAIR.finditer(text):
            segment = text[pos:m.start()].strip()
            pos = m.end()
            total = float(m.group(1).replace(",", ""))
            cumulative = float(m.group(2).replace(",", ""))
            # Reject page furniture: axis labels and page numbers produce money
            # pairs with no species text in front of them, and any real row's
            # cumulative is >= the one before it.
            if cumulative < running or len(re.findall(r"[A-Za-z]", segment)) < 6:
                continue
            running = cumulative
            common, sciname, population = _split_name(segment)
            rows.append({"cn": common, "sn": sciname, "pop": population, "total": total})

        summed = sum(r["total"] for r in rows)
        reference = stated_total if stated_total is not None else running
        drift = summed - reference
        if reference == 0 or abs(drift) > max(50.0, len(rows) * 1.0):
            sys.exit(f"FY{year}: parsed rows sum to ${summed:,.2f} but the report says "
                     f"${reference:,.2f} (drift ${drift:,.2f}) -- refusing to write a "
                     f"table that does not reconcile")
        unnamed = sum(1 for r in rows if not r["sn"])
        print(f"  FY{year}: {len(rows):,} entities, ${summed:,.0f} "
              f"(report says ${reference:,.0f}, drift ${drift:,.0f}); "
              f"{unnamed} rows with no scientific name parsed")
        out[str(year)] = {"total": reference, "rows": rows}

    (RAW / "expenditures.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8", newline="\n")
    print(f"  -> raw/expenditures.json ({(RAW / 'expenditures.json').stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# 2. NOAA Atlantic SAR, Table 1: abundance, PBR and human-caused mortality
# ---------------------------------------------------------------------------
# Table 1 is a wide landscape table, and pypdf returns it as a soup: the
# species / stock / area cells come back as a run of one- and two-word
# fragments, then every numeric column arrives on a single line, then a
# free-text Comments cell may wrap around the whole thing. The columns are
#
#   Y   4,260 0.24 3,817 0.04 0.5  38  0.2  0   N   2023 2021  NEC
#   |   Nest  CV   Nmin  Rmax Fr   PBR M/SI Fish |   SAR  Last  NMFS
#   updated this year                        strategic   survey centre
#
# so the reliable anchor is the numeric block itself: eight values, then the
# strategic Y/N, then two year cells. Everything since the previous anchor is
# the stock's name. Awkward real values this has to survive, all of which
# silently dropped rows in earlier drafts:
#
#   "3, 391"        a thousands separator that kept its space
#   "12.2-21.5"     an en-dashed range instead of a point estimate
#   "0 - -"         hyphens standing in for unknown
#   "7.6M"          millions, for the harp seal
#   "18 (0.09)"     a parenthesised CV riding along with the value
#   "1980- 2008"    a survey *period* rather than a survey year
DASH = "–—"
# A bare number. The comma alternative comes first and may contain a space,
# because "3, 391" is how a wrapped thousands separator survives extraction --
# but it must see the comma, or an ordinary "0 367" gets read as one number and
# silently shifts every column to its right by one.
SAR_PLAIN = r"(?:\d{1,3}(?:,\s?\d{3})+|\d+)(?:\.\d+)?[MK]?"
SAR_NUM = (r"(?:" + SAR_PLAIN + r"(?:[" + DASH + r"]\s?" + SAR_PLAIN + r")?"
           r"|unk|undet|N/A|n/a|-|[" + DASH + r"])(?:\s*\([^)]{1,20}\))?")
SAR_YEAR = r"(?:\d{4}(?:[" + DASH + r"-]\s?\d{4})?|unk|n/a|N/A)"
SAR_ROW = re.compile(
    r"([YN])\s+((?:" + SAR_NUM + r"\s+){7}" + SAR_NUM + r")\s+([YN])\s+"
    r"(" + SAR_YEAR + r")\s+((?:" + SAR_YEAR + r",?\s?)+)(?=\s|$)"
)
SAR_FURNITURE = re.compile(
    r"^(ID Species|Ctr\.?$|CV Nmin|Total$|Annual$|Strategic$|Status$|SAR of$|Last$|"
    r"Update$|Survey$|Year$|Comments|this Year|TABLE|Total annual|coefficient|"
    r"= unknown|M/SI Fish|\(CV\)|Nest$|July \d{4})"
)
SAR_NAME_NOISE = re.compile(
    r"(Details for this stock are included in the collective|report:|"
    r"M/SI Fish\.? M/SI|Nbest |N[a-z]* includes |^\W+)"
)


def _sar_value(token):
    """One numeric cell -> (low, high). Both None when the cell is unknown."""
    token = re.sub(r"\([^)]*\)", "", token).strip()
    token = token.replace(",", "").replace(" ", "")
    if token in ("unk", "undet", "n/a", "N/A", "-", "–", "—", ""):
        return None, None
    parts = re.split("[" + DASH + "]", token)

    def one(p):
        mult = 1
        if p.endswith("M"):
            mult, p = 1_000_000, p[:-1]
        elif p.endswith("K"):
            mult, p = 1_000, p[:-1]
        try:
            return float(p) * mult
        except ValueError:
            return None

    low = one(parts[0])
    high = one(parts[1]) if len(parts) > 1 else low
    return low, high


def parse_sar():
    path = RAW / "sar_atlantic_2024.pdf"
    if not path.exists():
        sys.exit("no raw/sar_atlantic_2024.pdf -- run fetch_noaa_data.py first")
    reader = pypdf.PdfReader(path)

    pages = [i for i, p in enumerate(reader.pages)
             if "ID Species Stock Area" in (p.extract_text() or "")]
    if not pages:
        sys.exit("could not find the SAR summary table header")

    chunks = []
    for i in range(pages[0], pages[-1] + 1):
        for line in (reader.pages[i].extract_text() or "").split("\n"):
            line = " ".join(line.split())
            if line and not SAR_FURNITURE.match(line):
                chunks.append(line)
    text = " ".join(chunks).replace("�", "’")

    rows, cursor = [], 0
    for m in SAR_ROW.finditer(text):
        segment = text[cursor:m.start()].strip()
        cursor = m.end()
        # The stock ID is the last bare integer before the name; earlier digits
        # are page numbers and leftovers from the previous row's comment cell.
        ids = re.findall(r"(?:^|\s)(\d{1,3})(?=\s)", segment)
        stock_id = int(ids[-1]) if ids else None
        if stock_id is not None:
            segment = segment[segment.rindex(ids[-1]) + len(ids[-1]):]
        name = SAR_NAME_NOISE.sub(" ", segment)
        name = " ".join(name.split()).strip(" .,;")

        cells = re.findall(SAR_NUM, m.group(2))
        cells += [""] * (8 - len(cells))
        n_est, _ = _sar_value(cells[0])
        n_min, _ = _sar_value(cells[2])
        pbr, _ = _sar_value(cells[5])
        msi_low, msi_high = _sar_value(cells[6])
        fish_low, fish_high = _sar_value(cells[7])
        rows.append({
            "id": stock_id,
            "name": name,
            "updated_this_year": m.group(1) == "Y",
            "n_est": n_est,
            "n_min": n_min,
            "pbr": pbr,
            # Where the report gives a range, msi_low is the conservative end:
            # anything counted as over PBR is over PBR on the report's own
            # lowest estimate.
            "msi_low": msi_low,
            "msi_high": msi_high,
            "msi_fisheries": fish_low,
            "msi_fisheries_high": fish_high,
            "strategic": m.group(3) == "Y",
            "sar_year": m.group(4),
            "survey_year": " ".join(m.group(5).split()),
        })

    ids_seen = {r["id"] for r in rows if r["id"]}
    expected = max(ids_seen) if ids_seen else 0
    if len(rows) < expected * 0.95:
        sys.exit(f"SAR table parsed {len(rows)} stocks but the ID column runs to "
                 f"{expected} -- missing {sorted(set(range(1, expected + 1)) - ids_seen)}")
    comparable = [r for r in rows if r["pbr"] and r["msi_low"] is not None]
    over = [r for r in comparable if r["msi_low"] > r["pbr"]]
    print(f"  SAR Atlantic 2024: {len(rows)} stocks (ID column runs to {expected}), "
          f"{len(comparable)} with both a PBR and a mortality estimate, "
          f"{len(over)} of those above PBR")
    right = next((r for r in rows if "right whale" in r["name"].lower()), None)
    if right:
        print(f"    check -- {right['name']}: Nmin {right['n_min']:,.0f}, "
              f"PBR {right['pbr']}, human-caused deaths {right['msi_low']}/yr")

    (RAW / "sar_atlantic.json").write_text(
        json.dumps({"edition": "2024 Atlantic and Gulf of America SARs",
                    "url": "https://www.fisheries.noaa.gov/s3/2026-04/atlantic_2024_mmsars.pdf",
                    "stocks": rows}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8", newline="\n")
    print("  -> raw/sar_atlantic.json")


def main():
    print("FWS expenditure reports")
    parse_expenditures()
    print("NOAA marine mammal stock assessments")
    parse_sar()


if __name__ == "__main__":
    main()
