"""Fetch the NOAA-side and money-side sources that ECOS does not carry.

    python fetch_noaa_data.py

ECOS (fetch_species_data.py) tells you *that* a species is listed and which
agency leads it. It does not tell you what NOAA itself says about the same
species, what anyone spent on it, or how much rulemaking it generated. These
five sources do, and every one of them is a primary federal document:

  1. NOAA Fisheries' own ESA species directory, as the JSON export its
     directory page offers. This is NMFS's authoritative list -- 105 species
     broken into ~258 separately listed entities -- with the fields ECOS has
     no column for: which NOAA region leads it, whether a recovery plan is
     final / draft / under development / absent, and whether critical habitat
     was designated, proposed, or found "not prudent".

  2. Four years of the FWS *Report to Congress on Federal and State Endangered
     and Threatened Species Expenditures* (FY2019-FY2022), as PDFs. Table 2 of
     each is a ranked, per-entity list of every dollar any federal agency or
     state reported spending on a listed species that year. There is no
     machine-readable release -- parse_esa_pdfs.py reads the PDFs.

  3. The Atlantic volume of NOAA's 2024 Marine Mammal Stock Assessment
     Reports. Its Table 1 gives, for every Atlantic and Gulf marine mammal
     stock, the minimum population estimate, the Potential Biological Removal
     level (the number of animals a year that can be killed by people without
     preventing the stock from reaching its optimum), and the actual observed
     human-caused mortality. PBR vs. actual is the sharpest single number in
     US marine mammal management.

  4. The Federal Register API -- the only genuinely documented API here
     (https://www.federalregister.gov/developers/documentation/api/v1) --
     for ESA rulemaking volume by agency and year, and for a live feed of
     each agency's most recent ESA documents.

  5. NatureServe Explorer's public search API, for the global conservation
     rank (G1 critically imperilled ... G5 secure) of each NOAA-managed
     species. NatureServe ranks *species*; the ESA lists *populations*. Where
     the two disagree is the point.

Nothing here is committed: raw/ is gitignored and everything is refetched.
The expenditure and SAR PDFs together are about 115 MB.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Quick Projects build script; wherever-found)"}

# --- 1. NOAA Fisheries ESA species directory --------------------------------
# The directory page at /species-directory/threatened-endangered offers CSV,
# JSON and XML exports of itself; the JSON one is this URL. It is the only
# NOAA endpoint here that behaves like an API.
NOAA_DIRECTORY = "https://www.fisheries.noaa.gov/species-directory/threatened-endangered-json"

# --- 2. FWS expenditure reports to Congress ---------------------------------
# FWS files these years late and under inconsistent names; each URL below was
# resolved from the report's own /media/ landing page. FY2022 is the most
# recent report published as of 2026-09.  Note FY2019 prints cents and the
# later years do not -- parse_esa_pdfs.py handles both.
EXPENDITURE_PDFS = {
    2019: "https://www.fws.gov/sites/default/files/documents/"
          "endangered-threatened-species-expenditures-report-to-congress-fiscal-year-2019.pdf",
    2020: "https://www.fws.gov/sites/default/files/documents/"
          "endangered-threatened-species-expenditures-%20report-to-congress-fiscal-year-2020.pdf",
    2021: "https://www.fws.gov/sites/default/files/documents/2026-05/"
          "endangered-and-threatened-species-expenditures-fiscal-year-2021.pdf",
    2022: "https://www.fws.gov/sites/default/files/documents/2026-05/"
          "endangered-and-threatened-species-expenditures-fiscal-year-2022_0.pdf",
}

# --- 3. Marine Mammal Stock Assessment Reports ------------------------------
# Only the Atlantic volume carries the cross-stock summary table (its Table 1).
# The 2024 Pacific and Alaska volumes are revision volumes -- they contain only
# the stocks revised that cycle and no summary table -- so this build is
# explicitly Atlantic + Gulf of America only, and the page says so.
SAR_ATLANTIC = "https://www.fisheries.noaa.gov/s3/2026-04/atlantic_2024_mmsars.pdf"

# --- 4. Federal Register -----------------------------------------------------
FR_API = "https://www.federalregister.gov/api/v1"
# Agency slugs as the Federal Register itself spells them. NMFS publishes ESA
# documents under the NOAA slug, not a separate fisheries one.
FR_AGENCIES = {
    "FWS": "fish-and-wildlife-service",
    "NOAA": "national-oceanic-and-atmospheric-administration",
}
# Both agencies head their ESA rulemaking with this phrase -- FWS as
# "Endangered and Threatened Wildlife and Plants", NMFS as "Endangered and
# Threatened Species" / "...Wildlife and Plants". Searching the phrase rather
# than a title regex catches notices and findings as well as rules.
FR_TERM = '"Endangered and Threatened"'


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_json(url, timeout=60):
    return json.loads(fetch(url, timeout))


def download(url, dest, timeout=400):
    print(f"  fetching {dest.name} ...", end="", flush=True)
    data = fetch(url, timeout)
    dest.write_bytes(data)
    print(f" {len(data):,} bytes")


def fr_query(agency_slug, extra=""):
    return (f"conditions%5Bagencies%5D%5B%5D={agency_slug}"
            f"&conditions%5Bterm%5D={urllib.parse.quote(FR_TERM)}{extra}")


def fetch_noaa_directory():
    print("NOAA Fisheries ESA species directory")
    data = fetch(NOAA_DIRECTORY, timeout=90)
    (RAW / "noaa_species_directory.json").write_bytes(data)
    parsed = json.loads(data)
    species = parsed["collection"]["species"]
    entities = sum(len(s.get("status_details", [])) for s in species)
    print(f"  -> {len(species)} species, {entities} separately listed entities")


def fetch_expenditures():
    print("FWS Report to Congress on ESA expenditures")
    for year, url in EXPENDITURE_PDFS.items():
        download(url, RAW / f"expenditures_fy{year}.pdf")


def fetch_sar():
    print("NOAA 2024 Marine Mammal Stock Assessment Reports (Atlantic volume)")
    download(SAR_ATLANTIC, RAW / "sar_atlantic_2024.pdf")


def fetch_federal_register():
    print("Federal Register API")
    out = {"term": FR_TERM, "agencies": {}}
    for label, slug in FR_AGENCIES.items():
        yearly = fetch_json(f"{FR_API}/documents/facets/yearly?{fr_query(slug)}")
        by_type = fetch_json(f"{FR_API}/documents/facets/type?{fr_query(slug)}")
        fields = "".join("&fields%5B%5D=" + f for f in
                         ("title", "publication_date", "type", "html_url", "abstract"))
        recent = fetch_json(
            f"{FR_API}/documents.json?per_page=40&order=newest&{fr_query(slug, fields)}"
        )
        out["agencies"][label] = {
            "slug": slug,
            "yearly": {v["name"]: v["count"] for v in yearly.values()},
            "by_type": {v["name"]: v["count"] for v in by_type.values()},
            "recent": recent.get("results", []),
            "total": recent.get("count"),
        }
        n = sum(out["agencies"][label]["yearly"].values())
        print(f"  {label}: {n:,} ESA documents since {min(out['agencies'][label]['yearly'])}")
        time.sleep(0.4)
    (RAW / "federal_register.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def fetch_federal_register_by_species():
    """How many Federal Register documents mention each NOAA species by name.

    A rough but honest measure of regulatory attention: the scientific name is
    a near-unique token, so a full-text phrase search for it is a good proxy.
    Counts saturate at the API's 10,000 cap, which nothing here comes near.
    """
    print("Federal Register: per-species document counts")
    directory = json.loads((RAW / "noaa_species_directory.json").read_text(encoding="utf-8"))
    names = sorted({s["scientific_name"].strip() for s in directory["collection"]["species"]
                    if s.get("scientific_name")})
    counts = {}
    for i, name in enumerate(names, 1):
        term = urllib.parse.quote(f'"{name}"')
        url = f"{FR_API}/documents.json?per_page=1&fields%5B%5D=title&conditions%5Bterm%5D={term}"
        try:
            counts[name] = fetch_json(url, timeout=45).get("count", 0)
        except Exception as exc:  # a single miss should not lose the whole run
            print(f"    ! {name}: {exc}")
            counts[name] = None
        if i % 25 == 0:
            print(f"    {i}/{len(names)}")
        time.sleep(0.25)
    (RAW / "federal_register_species.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    got = [v for v in counts.values() if v]
    print(f"  -> {len(got)} of {len(names)} species named in at least one FR document")


def fetch_natureserve():
    """Global conservation rank for every NOAA-managed species.

    NatureServe's Explorer search API is public and unauthenticated. It ranks
    a species across its whole global range (G1 critically imperilled through
    G5 secure), which is a different question from whether a US population is
    ESA-listed -- a G5 species with a listed ESU is the ESA's population unit
    doing exactly what it was written to do.
    """
    print("NatureServe Explorer global ranks")
    directory = json.loads((RAW / "noaa_species_directory.json").read_text(encoding="utf-8"))
    names = sorted({s["scientific_name"].strip() for s in directory["collection"]["species"]
                    if s.get("scientific_name")})
    out = {}
    for i, name in enumerate(names, 1):
        body = json.dumps({
            "criteriaType": "species",
            "textCriteria": [{"paramType": "textSearch", "searchToken": name,
                              "matchAgainst": "allScientificNames", "operator": "equals"}],
            "statusCriteria": [], "locationCriteria": [],
            "pagingOptions": {"page": 0, "recordsPerPage": 1},
        }).encode()
        req = urllib.request.Request(
            "https://explorer.natureserve.org/api/data/speciesSearch", data=body,
            headers={**UA, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                results = json.load(resp).get("results") or []
        except Exception as exc:
            print(f"    ! {name}: {exc}")
            results = []
        if results:
            r = results[0]
            us = next((n for n in r.get("nations", []) if n.get("nationCode") == "US"), None)
            out[name] = {
                "grank": r.get("roundedGRank"),
                "nrank_us": us.get("roundedNRank") if us else None,
                "common": r.get("primaryCommonName"),
                "url": "https://explorer.natureserve.org" + (r.get("nsxUrl") or ""),
            }
        if i % 25 == 0:
            print(f"    {i}/{len(names)}")
        time.sleep(0.15)
    (RAW / "natureserve.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    ranked = sum(1 for v in out.values() if v.get("grank"))
    print(f"  -> {ranked} of {len(names)} species carry a global rank"
          f" ({len(names) - ranked} unranked, mostly Indo-Pacific corals)")


def main():
    fetch_noaa_directory()
    fetch_expenditures()
    fetch_sar()
    fetch_federal_register()
    fetch_federal_register_by_species()
    fetch_natureserve()
    print("\nnow run: python parse_esa_pdfs.py")


if __name__ == "__main__":
    main()
