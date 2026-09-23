"""Fetch every ECOS report this build needs, straight from FWS's live API.

Run with: python fetch_species_data.py
Writes raw JSON into raw/ (gitignored -- these are refetched, not committed).
Every endpoint here was found by watching the network tab while using the real
ECOSphere report pages at https://ecos.fws.gov/ecp/report/... -- none of it is
documented publicly, so if FWS changes the API this script is what breaks.
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)

BASE = "https://ecos.fws.gov"

# The master species table, queried through the Data Explorer's pull-reports
# export endpoint. Columns were discovered by clicking "Add all" in the
# Data Explorer UI (https://ecos.fws.gov/ecp/report/adhoc-creator?catalogId=species&reportId=species)
# and reading the resulting URL.
MASTER_COLUMNS = (
    "cn,sn,status,status_category,desc,listing_date,agency,country,"
    "is_foreign,dps,alt_status,recovery_priority_number,vipcode,id,sid,gn"
)

ENDPOINTS = {
    # All species entities the ESA has ever touched: Listed, Delisted,
    # Candidate, Proposed, Petitioned, Not Listed. No status filter, so this
    # is the full 11,000-plus row universe -- filtering to what we use
    # happens in build_payload.py.
    "master.json": (
        f"{BASE}/ecp/pullreports/catalog/species/report/species/export"
        f"?format=json&columns=%2Fspecies%40{urllib.parse.quote(MASTER_COLUMNS)}"
    ),
    # Delisted species joined to their delisting_info: the actual delisting
    # date and reason, which the master table does not carry.
    "delisted.json": (
        f"{BASE}/ecp/pullreports/catalog/species/report/species/export?format=json"
        "&columns=%2Fspecies%40cn%2Csn%2Cdesc%2Clisting_date%2Cagency%2Ccountry%2Cgn"
        "%2Cstatus%2Cstatus_category%2Cid%2Csid"
        "%3B%2Fspecies%2Fdelisting_info%40delisting_date%2Cdelisting_reason"
        "&filter=%2Fspecies%2Fdelisting_info%40delisting_date%20is%20not%20null"
        "&sort=%2Fspecies%40listing_date%20desc"
    ),
    # Every reclassification (uplisting/downlisting) with its Federal
    # Register date and the status it moved to.
    "reclassified.json": f"{BASE}/ecp/report/speciesReclassified?format=json",
    "candidate.json": f"{BASE}/ecp/report/candidateSpecies?format=json",
    "candidate_removed.json": (
        f"{BASE}/ecp/report/speciesCandidateRemovedOrWithdrawn?format=json"
    ),
    "dps.json": f"{BASE}/ecp/report/dps?format=json",
    "boxscore.json": f"{BASE}/ecp/report/boxscore?format=json",
    "by_year.json": f"{BASE}/ecp/report/speciesListingsByYearTotals?format=json",
    "by_state.json": (
        f"{BASE}/ecp/report/speciesListingsByStateTotals?format=json&statusCategory=Listed"
    ),
    "by_tax_group.json": (
        f"{BASE}/ecp/report/speciesListingsByTaxGroupTotals?format=json&statusCategory=Listed"
    ),
    "five_year_reviews.json": f"{BASE}/ecp/report/speciesFiveYearReview?format=json",
    "critical_habitat.json": f"{BASE}/ecp/report/criticalHabitat?format=json",
    "recovery_plans.json": f"{BASE}/ecp/report/speciesWithRecoveryPlans?format=json",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Quick Projects build script)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> None:
    for name, url in ENDPOINTS.items():
        out = RAW / name
        print(f"fetching {name} ...")
        data = fetch(url)
        out.write_bytes(data)
        parsed = json.loads(data)
        n = parsed.get("total", parsed.get("meta", {}).get("totalCount"))
        rows = parsed.get("data", parsed.get("results"))
        print(f"  -> {out.name}: {len(data):,} bytes, total={n}, rows={len(rows) if rows is not None else '?'}")
        time.sleep(0.5)  # be polite to a government API with no documented rate limit


if __name__ == "__main__":
    main()
