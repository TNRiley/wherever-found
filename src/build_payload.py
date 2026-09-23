"""Merge the raw ECOS reports (raw/*.json) into one clean payload.json.

Join keys, worked out by hand against real records:
  - entity_id ("id" in master.json) is the true primary key: one row per
    listing entity, where a single species can have several (one per
    Distinct Population Segment). recovery_plans, five_year_reviews and
    critical_habitat all carry this same entity_id.
  - delisted.json also carries "id" (same entity_id) so it joins directly.
  - reclassified.json has no entity_id, only scientific name + a population
    description ("pop_abbrev"). It is joined by (sciname, normalized
    population text), falling back to sciname alone for the ~3% of species
    that have more than one listing entity and whose population text does
    not match verbatim -- see NOTES below.
"""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent.parent / "payload.json"


def load(name):
    with open(RAW / name, encoding="utf-8") as f:
        return json.load(f)


def norm_pop(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def mmddyyyy_to_iso(s):
    """'03-11-1967' or '03/11/1967' -> '1967-03-11'. Returns None if unparseable."""
    if not s:
        return None
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s.strip())
    if not m:
        return None
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def main():
    master = load("master.json")
    cols = [c["id"] for c in master["meta"]["columns"]]
    ci = {c: i for i, c in enumerate(cols)}
    rows = master["data"]

    entities = [r for r in rows if r[ci["status_category"]] in ("Listed", "Delisted")]
    print(f"master entities in scope (Listed + Delisted): {len(entities)}")

    # --- delisting_info, keyed by entity_id ---------------------------------
    delisted_raw = load("delisted.json")
    d_cols = [c["id"] for c in delisted_raw["meta"]["columns"]]
    d_i = {c: i for i, c in enumerate(d_cols)}
    delisting_by_id = {}
    for r in delisted_raw["data"]:
        delisting_by_id[r[d_i["id"]]] = {
            "date": mmddyyyy_to_iso(r[d_i["delisting_date"]]),
            "reason": r[d_i["delisting_reason"]],
        }

    # --- reclassification history, keyed by (sciname, normalized pop text) --
    # dps.json gives both the short DPS label ("abbrev") and the long-form
    # range description ("description") that master.json's "desc" column
    # actually uses, for the same population -- reclassified.json only gives
    # the short label, so this bridges the two vocabularies.
    dps_bridge_raw = load("dps.json")
    dps_bridge = {}
    for r in dps_bridge_raw["results"]:
        dps_bridge[(r["sciname"], norm_pop(r["abbrev"]))] = norm_pop(r["description"])

    reclass_raw = load("reclassified.json")
    reclass_by_key = defaultdict(list)
    reclass_by_sciname = defaultdict(list)
    reclass_fuzzy_candidates = []
    for r in reclass_raw["results"]:
        hist = [
            {"date": mmddyyyy_to_iso(h["fr_date"]), "to_status": h["aopt"]}
            for h in r.get("reclass_history", [])
        ]
        if not hist:
            continue
        pop_norm = norm_pop(r.get("pop_abbrev", ""))
        key = (r["sciname"], pop_norm)
        reclass_by_key[key].extend(hist)
        bridged = dps_bridge.get((r["sciname"], pop_norm))
        if bridged:
            reclass_by_key[(r["sciname"], bridged)].extend(hist)
        reclass_by_sciname[r["sciname"]].extend(hist)
        reclass_fuzzy_candidates.append((r["sciname"], set(pop_norm.split()), hist))

    def jaccard_match(sciname, desc_norm):
        """Last-resort fallback for the handful of DPS records whose population
        text is phrased so differently between reports that no exact or
        dps.json-bridged key matches (e.g. a leopard range written as
        'Gabon to Kenya and southward' in one report and as a country list
        in the other). Picks the best word-overlap match for this sciname,
        if any candidate clears a 0.3 Jaccard bar."""
        desc_tokens = set(desc_norm.split())
        best, best_score = None, 0.3
        for cand_sn, cand_tokens, cand_hist in reclass_fuzzy_candidates:
            if cand_sn != sciname or not cand_tokens:
                continue
            overlap = len(desc_tokens & cand_tokens) / len(desc_tokens | cand_tokens)
            if overlap > best_score:
                best, best_score = cand_hist, overlap
        return best

    # --- five-year status reviews, keyed by entity_id ------------------------
    fyr_raw = load("five_year_reviews.json")
    fyr_by_id = defaultdict(list)
    for r in fyr_raw["results"]:
        fyr_by_id[r["entity_id"]].append({
            "completed": mmddyyyy_to_iso(r.get("completion_date")) or r.get("completion_date"),
            "outcome": r.get("name"),
            "fr_publication_date": mmddyyyy_to_iso(r.get("fr_publication_date")),
            "fr_title": r.get("fr_publication_title"),
            "doc_url": r.get("completed_doc_path"),
            "fr_url": r.get("fr_url"),
        })

    # --- critical habitat, keyed by entity_id --------------------------------
    ch_raw = load("critical_habitat.json")
    ch_by_id = defaultdict(list)
    for r in ch_raw["results"]:
        ch_by_id[r["entity_id"]].append({
            "status": r.get("crithab_status"),
            "date": mmddyyyy_to_iso(r.get("fr_date")),
            "measurement": r.get("crithab_measurement"),
            "fr_title": (r.get("fr_title") or "").strip(),
            "fr_page": r.get("fr_page"),
            "fr_url": r.get("fr_url"),
            "region": (r.get("region_name") or "").strip(),
        })

    # --- recovery plans, keyed by entity_id ----------------------------------
    rp_raw = load("recovery_plans.json")
    rp_by_id = defaultdict(list)
    for r in rp_raw["data"]:
        entity_id = (r.get("plan_action_status") or {}).get("entity_id")
        if entity_id is None:
            continue
        plan_title = r.get("plan_title") or {}
        rp_by_id[entity_id].append({
            "title": plan_title.get("value"),
            "doc_url": plan_title.get("url"),
            "date": r.get("datesort"),
            "stage": r.get("plan_stage"),
        })

    # --- assemble ------------------------------------------------------------
    species = []
    multi_entity_snames = set()
    seen_sn_count = defaultdict(int)
    for r in entities:
        seen_sn_count[r[ci["sn"]]["value"]] += 1
    for sn, n in seen_sn_count.items():
        if n > 1:
            multi_entity_snames.add(sn)

    reclass_fallback_used = 0
    reclass_fuzzy_used = 0
    for r in entities:
        eid = r[ci["id"]]
        sn = r[ci["sn"]]["value"]
        pop_desc = r[ci["desc"]] or ""
        pop_norm = norm_pop(pop_desc)
        key = (sn, pop_norm)
        reclass_hist = list(reclass_by_key.get(key, []))
        if not reclass_hist and sn not in multi_entity_snames:
            reclass_hist = list(reclass_by_sciname.get(sn, []))
            if reclass_hist:
                reclass_fallback_used += 1
        if not reclass_hist and sn in multi_entity_snames:
            fuzzy = jaccard_match(sn, pop_norm)
            if fuzzy:
                reclass_hist = list(fuzzy)
                reclass_fuzzy_used += 1
        reclass_hist.sort(key=lambda h: h["date"] or "")

        rec = {
            "id": eid,
            "sid": r[ci["sid"]],
            "cn": r[ci["cn"]],
            "sn": sn,
            "group": r[ci["gn"]],
            "status": r[ci["status"]],
            "status_category": r[ci["status_category"]],
            "pop": pop_desc,
            "is_dps": bool(r[ci["dps"]]),
            "listing_date": mmddyyyy_to_iso(r[ci["listing_date"]]),
            "agency": r[ci["agency"]],
            "country": r[ci["country"]],
            "is_foreign": bool(r[ci["is_foreign"]]),
            "recovery_priority": r[ci["recovery_priority_number"]],
            "vipcode": r[ci["vipcode"]],
            "profile_url": r[ci["sn"]]["url"],
        }
        if r[ci["status_category"]] == "Delisted" and eid in delisting_by_id:
            rec["delisting"] = delisting_by_id[eid]
        if reclass_hist:
            rec["reclassifications"] = reclass_hist
        if eid in fyr_by_id:
            rec["five_year_reviews"] = sorted(fyr_by_id[eid], key=lambda x: x["completed"] or "")
        if eid in ch_by_id:
            rec["critical_habitat"] = ch_by_id[eid]
        if eid in rp_by_id:
            rec["recovery_plans"] = rp_by_id[eid]
        species.append(rec)

    print(f"reclassification records matched: {sum(1 for s in species if 'reclassifications' in s)}"
          f" ({reclass_fallback_used} via sciname fallback, {reclass_fuzzy_used} via fuzzy match)")
    print(f"delisted with a delisting date/reason: {sum(1 for s in species if 'delisting' in s)}"
          f" of {sum(1 for s in species if s['status_category']=='Delisted')} delisted")
    print(f"five-year reviews attached: {sum(1 for s in species if 'five_year_reviews' in s)}")
    print(f"critical habitat attached: {sum(1 for s in species if 'critical_habitat' in s)}")
    print(f"recovery plans attached: {sum(1 for s in species if 'recovery_plans' in s)}")

    # --- supplementary datasets ----------------------------------------------
    candidate_raw = load("candidate.json")
    candidates = [{
        "cn": r["invname"], "sn": r["sciname"], "group": r["group_name"],
        "region": r["lead_region"], "pop": r.get("pop_desc"),
    } for r in candidate_raw["results"]]

    cand_removed_raw = load("candidate_removed.json")
    candidates_removed = [{
        "cn": r["comname"], "sn": r["sciname"], "group": r["group_name"],
        "date": mmddyyyy_to_iso(r["fr_date"]), "reason": r["wreason"],
        "pop": r.get("pop_abbrev"),
    } for r in cand_removed_raw["results"]]

    dps_raw = load("dps.json")
    dps_list = [{
        "cn": r["invname"], "sn": r["sciname"], "group": r["group_text"],
        "pop": r["description"], "abbrev": r["abbrev"], "status": r["status"],
        "listing_date": mmddyyyy_to_iso(r["listing_date"]),
        "lead_region": (r.get("lead_region") or "").strip(),
        "more_info_url": r.get("more_info_url"),
    } for r in dps_raw["results"]]

    by_year_raw = load("by_year.json")
    by_year = sorted(
        [{"year": r["year"], "count": r["spp_count"]} for r in by_year_raw["results"]],
        key=lambda x: x["year"],
    )

    by_state_raw = load("by_state.json")
    by_state = [{
        "state": r["stateName"], "abbrev": r["stateAbbrev"], "count": r["total"],
    } for r in by_state_raw["results"]]

    by_group_raw = load("by_tax_group.json")
    by_group = [{"group": r["groupName"], "children": r["childNames"], "count": r["total"]}
                for r in by_group_raw["results"]]

    boxscore = load("boxscore.json")

    payload = {
        "generated": None,  # filled in by inject.py at splice time
        "species": species,
        "candidates": candidates,
        "candidates_removed": candidates_removed,
        "dps": dps_list,
        "by_year": by_year,
        "by_state": by_state,
        "by_group": by_group,
        "boxscore": boxscore,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"\nwrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
