"""Join the NOAA, money, stock-assessment, rulemaking and global-rank sources
onto the ECOS listing entities that build_payload.py has already assembled.

Called from build_payload.py; not run on its own.

Everything here hangs off two join problems, and both are worth stating plainly
because they are where a rebuild will go wrong:

**Scientific names.** FWS and NOAA maintain separate taxonomies and do not
agree. FWS's master list still calls the Hawaiian monk seal *Monachus
schauinslandi*; NOAA calls it *Neomonachus schauinslandi*. FWS has the giant
manta ray as *Manta birostris*, NOAA as *Mobula birostris*; the totoaba is
*Cynoscion macdonaldi* to one agency and *Totoaba macdonaldi* to the other.
Nine of NOAA's 105 species fail a literal name match against FWS's export.
SCI_BRIDGE below resolves them by matching the species epithet within
NMFS-led rows only, which is safe because the epithet plus "NOAA leads it"
is unique across this data -- an unrestricted epithet match would marry the
ringed seal (*Pusa hispida*) to a Hawaiian mint (*Phyllostegia hispida*).

**Populations.** The expenditure reports are generated from the same 50 CFR
17.11/17.12 list ECOS publishes, so population text usually matches verbatim
once a "See 50 CFR 223.102" cross-reference is stripped. Where it does not,
the fallbacks are (1) a scientific name that has exactly one listing entity,
and (2) a bag-of-words match on the common name plus population, because the
two sources invert the name ("Woodpecker, red-cockaded" vs "Red-cockaded
Woodpecker"). Anything still unmatched stays in `spending.unjoined` so the
page's totals remain the report's own totals rather than the join's.
"""
import json
import re
import unicodedata
from collections import defaultdict

# Lead-agency values ECOS actually uses, for the two that involve NMFS.
NMFS_AGENCIES = {"NMFS", "FWS and NMFS"}


def norm(text):
    """Lowercase, strip punctuation, and drop the parenthetical asides both
    agencies bury inside names: '(=Salmo)', '(incl. D. cascus)', '[=longirostris]',
    and the expenditure reports' 'See 50 CFR 223.102' cross-reference."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text)).lower()
    text = re.sub(r"see 50 cfr [\d.]+", " ", text)
    text = re.sub(r"\(=[^)]*\)|\(incl[^)]*\)|\[[^\]]*\]", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def bag(text):
    """Word-set form, so 'Woodpecker, red-cockaded' == 'Red-cockaded Woodpecker'."""
    return " ".join(sorted(set(norm(text).split())))


def sci_forms(name):
    """Every spelling of a scientific name a source might use.

    'Physeter catodon (=macrocephalus)' is one name in FWS's list and two in
    everyone else's, so both 'physeter catodon' and 'physeter macrocephalus'
    have to be indexed or the sperm whale never joins.
    """
    forms = {norm(name)}
    for alt in re.findall(r"\(=\s*([^)]+)\)", str(name or "")):
        head = norm(name).split()
        alt = norm(alt)
        if head and alt:
            forms.add(" ".join([head[0], alt]) if " " not in alt else alt)
            if len(head) > 1:
                forms.add(" ".join([alt] + head[1:]))
    return {f for f in forms if f}


def _index_species(species):
    """Build every lookup the joins below need, over the assembled entities."""
    by_sci_pop, by_sci, by_bag_pop = defaultdict(list), defaultdict(list), defaultdict(list)
    epithet_nmfs = defaultdict(list)
    for rec in species:
        pop = norm(rec["pop"])
        for form in sci_forms(rec["sn"]):
            by_sci_pop[(form, pop)].append(rec)
            by_sci[form].append(rec)
            words = form.split()
            if len(words) >= 2 and rec["agency"] in NMFS_AGENCIES:
                epithet_nmfs[words[1]].append(rec)
        by_bag_pop[(bag(rec["cn"]), pop)].append(rec)
    return by_sci_pop, by_sci, by_bag_pop, epithet_nmfs


# ---------------------------------------------------------------------------
# NOAA Fisheries' own ESA species directory
# ---------------------------------------------------------------------------
def _noaa_directory(load, species, by_sci, epithet_nmfs):
    raw = load("noaa_species_directory.json")
    ranks = load("natureserve.json")
    fr_counts = load("federal_register_species.json")

    out, bridged, absent = [], [], []
    for item in raw["collection"]["species"]:
        sciname = (item.get("scientific_name") or "").strip()
        forms = sci_forms(sciname)
        matches = []
        for form in forms:
            matches = by_sci.get(form) or []
            if matches:
                break
        how = "name"
        if not matches:
            # Same animal, different accepted taxonomy. Match on the species
            # epithet, but only against entities ECOS itself says NMFS leads.
            words = norm(sciname).split()
            if len(words) >= 2:
                matches = epithet_nmfs.get(words[1], [])
            how = "epithet"
            if matches:
                bridged.append({"noaa": sciname,
                                "fws": sorted({m["sn"] for m in matches})})
            else:
                absent.append({"name": item.get("name"), "sn": sciname})
                how = "none"

        rank = ranks.get(sciname) or {}
        out.append({
            "name": item.get("name"),
            "sn": sciname,
            "url": item.get("page_url"),
            "cat": item.get("category_primary"),
            "cat2": item.get("category_secondary"),
            "entities": [{
                "unit": d.get("listed_entity"),
                "status": d.get("protected_status"),
                "year": d.get("year_listed"),
                "region": d.get("region"),
                "plan": d.get("recovery_plan_status") or "",
                "plan_url": d.get("recovery_plan_url") or "",
                "crithab": d.get("critical_habitat_status") or "",
                "crithab_url": d.get("critical_habitat_url") or "",
            } for d in item.get("status_details", [])],
            "grank": rank.get("grank"),
            "nrank_us": rank.get("nrank_us"),
            "ns_url": rank.get("url"),
            "fr_documents": fr_counts.get(sciname),
            "ecos_ids": sorted({m["id"] for m in matches}),
            "ecos_join": how,
        })

    # Which of these does ECOS itself credit to NMFS? Where the two agencies'
    # own databases disagree about who is in charge is a real finding, not an
    # artefact -- but only where the species matched by name, since an epithet
    # bridge is selected on the agency field in the first place.
    disagree = []
    for rec in out:
        if rec["ecos_join"] != "name" or not rec["ecos_ids"]:
            continue
        agencies = {s["agency"] for s in species if s["id"] in set(rec["ecos_ids"])}
        if agencies and not (agencies & NMFS_AGENCIES):
            disagree.append({"name": rec["name"], "sn": rec["sn"],
                             "ecos_agency": sorted(agencies)})

    print(f"NOAA directory: {len(out)} species, "
          f"{sum(len(r['entities']) for r in out)} listed entities; "
          f"{len(bridged)} matched to ECOS only through a taxonomic synonym, "
          f"{len(absent)} not in ECOS at all, "
          f"{len(disagree)} that ECOS credits to FWS alone")
    return {"species": out, "bridged": bridged, "absent": absent, "disagree": disagree}


# ---------------------------------------------------------------------------
# FWS expenditure reports
# ---------------------------------------------------------------------------
def _spending(load, species, noaa_block, by_sci_pop, by_sci, by_bag_pop):
    raw = load("expenditures.json")

    # A row counts as NOAA's if NOAA's own directory names the species, or if
    # ECOS says NMFS leads it. Either source alone undercounts: ECOS misses a
    # few NOAA species entirely, and NOAA's directory is species-level while
    # the money is reported per listing entity.
    noaa_names = set()
    for rec in noaa_block["species"]:
        noaa_names |= sci_forms(rec["sn"])
    ecos_noaa = set()
    for rec in species:
        if rec["agency"] in NMFS_AGENCIES:
            ecos_noaa |= sci_forms(rec["sn"])

    years = sorted(raw)
    by_year, unjoined, per_entity = {}, {}, defaultdict(dict)
    for year in years:
        rows, joined_total = raw[year]["rows"], 0.0
        noaa_total = 0.0
        leftovers = []
        for row in rows:
            forms = sci_forms(row["sn"] or "")
            pop = norm(row["pop"])
            hit = None
            for form in forms:
                hit = by_sci_pop.get((form, pop))
                if hit:
                    break
            if not hit:
                for form in forms:
                    single = by_sci.get(form)
                    if single and len({s["id"] for s in single}) == 1:
                        hit = single
                        break
            if not hit:
                hit = by_bag_pop.get((bag(row["cn"]), pop))
            if hit:
                per_entity[hit[0]["id"]][year] = row["total"]
                joined_total += row["total"]
            else:
                leftovers.append({"cn": row["cn"], "sn": row["sn"],
                                  "pop": row["pop"], "total": row["total"]})
            if forms & (noaa_names | ecos_noaa):
                noaa_total += row["total"]

        by_year[year] = {
            "total": raw[year]["total"],
            "entities": len(rows),
            "noaa_total": round(noaa_total, 2),
            "noaa_entities": sum(1 for r in rows
                                 if sci_forms(r["sn"] or "") & (noaa_names | ecos_noaa)),
            "joined_total": round(joined_total, 2),
            # The report ranks entities, so its own top of the list is the
            # honest headline -- taken straight from the PDF, before any join.
            "top": [{"cn": r["cn"], "sn": r["sn"], "pop": r["pop"], "total": r["total"],
                     "noaa": bool(sci_forms(r["sn"] or "") & (noaa_names | ecos_noaa))}
                    for r in sorted(rows, key=lambda r: -r["total"])[:40]],
        }
        unjoined[year] = leftovers
        share = noaa_total / raw[year]["total"] * 100
        print(f"  FY{year}: ${raw[year]['total']:,.0f} over {len(rows):,} entities; "
              f"NOAA-led species take ${noaa_total:,.0f} ({share:.1f}%); "
              f"{joined_total / raw[year]['total'] * 100:.0f}% joined to an ECOS entity")

    for rec in species:
        if rec["id"] in per_entity:
            rec["spend"] = per_entity[rec["id"]]

    return {"years": years, "by_year": by_year,
            "unjoined_counts": {y: len(v) for y, v in unjoined.items()}}


# ---------------------------------------------------------------------------
# Marine mammal stock assessments
# ---------------------------------------------------------------------------
def _sar(load):
    raw = load("sar_atlantic.json")
    stocks = raw["stocks"]
    comparable = [s for s in stocks if s["pbr"] and s["msi_low"] is not None]
    over = [s for s in comparable if s["msi_low"] > s["pbr"]]
    print(f"  SAR: {len(stocks)} Atlantic and Gulf stocks, {len(comparable)} with both "
          f"a PBR and a mortality estimate, {len(over)} above PBR, "
          f"{sum(1 for s in stocks if s['strategic'])} classed strategic")
    return {"edition": raw["edition"], "url": raw.get("url"), "stocks": stocks,
            "comparable": len(comparable), "over_pbr": len(over)}


# ---------------------------------------------------------------------------
# Federal Register
# ---------------------------------------------------------------------------
def _federal_register(load):
    raw = load("federal_register.json")
    for label, block in raw["agencies"].items():
        print(f"  Federal Register {label}: {block['total']:,} ESA documents, "
              f"{block['by_type']}")
    return raw


def attach(species, load):
    """Return the extra payload sections, and decorate `species` in place."""
    by_sci_pop, by_sci, by_bag_pop, epithet_nmfs = _index_species(species)
    noaa = _noaa_directory(load, species, by_sci, epithet_nmfs)
    print("expenditures")
    spending = _spending(load, species, noaa, by_sci_pop, by_sci, by_bag_pop)
    print("stock assessments")
    sar = _sar(load)
    print("rulemaking")
    federal_register = _federal_register(load)
    return {"noaa": noaa, "spending": spending, "sar": sar,
            "federal_register": federal_register}
