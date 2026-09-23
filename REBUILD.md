# Rebuilding Wherever Found

Enough to reproduce this from scratch with a shell and no other context.

## 1. What this is

Every species entity the U.S. Endangered Species Act has ever listed, delisted or
reclassified, queried live from the Fish and Wildlife Service's own ECOSphere
database rather than a static export someone else cleaned first. The one finding
the page exists to show: **"delisted" is not a synonym for "recovered."** Of 141
delisting entities on record, only 85 (60%) were removed because the species
actually recovered. 32 went extinct first. The other 24 were never validly listed
at all -- a taxonomic reclassification or new information overturned the original
listing decision. A naive reading of "the number of listed species went down" as
an environmental win, without checking which bucket each delisting fell into, is
the trap this build is designed to make impossible.

## 2. Data sources

Everything comes from **undocumented** ECOS report endpoints, found by opening
`https://ecos.fws.gov/ecp/report/<slug>` pages in a real browser and reading the
network tab -- there is no published API reference. These can break without
notice; `src/fetch_species_data.py` is the single point of contact with all of
them.

| file | endpoint | what it gives |
|---|---|---|
| `master.json` | `/ecp/pullreports/catalog/species/report/species/export?format=json&columns=...` | every species entity (11,027 rows, all statuses): common/scientific name, current ESA status, status *category* (Listed/Delisted/Candidate/etc.), population description, listing date, lead agency, foreign/domestic, taxonomic group (`gn`) |
| `delisted.json` | same export, columns joined through `/species/delisting_info` | delisting date + reason for 138 of 141 delisted entities |
| `reclassified.json` | `/ecp/report/speciesReclassified?format=json` | dated uplisting/downlisting history per species (short population label, not the long form) |
| `dps.json` | `/ecp/report/dps?format=json` | Distinct Population Segments: both the short label ("Western DPS") *and* the long-form range description -- the bridge between `reclassified.json`'s vocabulary and `master.json`'s |
| `candidate.json`, `candidate_removed.json` | `/ecp/report/candidateSpecies`, `/ecp/report/speciesCandidateRemovedOrWithdrawn` | species considered for listing, and 204 considered and rejected |
| `boxscore.json` | `/ecp/report/boxscore?format=json` | FWS's own official summary counts, used only to cross-check this build's totals |
| `by_state.json`, `by_tax_group.json`, `by_year.json` | `/ecp/report/speciesListingsBy{StateTotals,TaxGroupTotals,YearTotals}?format=json` | pre-aggregated totals (by_year is *not* used in the final page -- see §3) |
| `five_year_reviews.json` | `/ecp/report/speciesFiveYearReview?format=json` | 1,599 completed 5-year status reviews, each with a PDF link |
| `critical_habitat.json` | `/ecp/report/criticalHabitat?format=json` | 995 critical habitat designations, with acreage/mileage text and Federal Register links |
| `recovery_plans.json` | `/ecp/report/speciesWithRecoveryPlans?format=json` | 1,834 recovery plan documents, linked to a specific entity_id |

NOAA Fisheries' public species directory (`fisheries.noaa.gov/species-directory/
threatened-endangered`) was used only to sanity-check the `agency` field's NMFS
count (its public page states 165 NMFS species as of the page's own snapshot;
this build's live pull gets 167 -- 140 NMFS-only + 27 joint FWS/NMFS -- a
plausible few-species drift given the two were pulled on different dates).

## 3. Processing decisions, and the traps

- **Primary key is `id` (ECOS entity ID), not scientific name.** A single
  species can have several listing entities -- different Distinct Population
  Segments with different statuses. `recovery_plans.json`, `five_year_reviews
  .json` and `critical_habitat.json` all carry this same `entity_id`, and join
  cleanly. `delisted.json`'s `id` column is the same field.
- **`reclassified.json` has no entity_id at all**, only scientific name plus a
  short population label ("Western DPS"), while `master.json`'s population
  field (`desc`) is always the long form ("U.S.A., conterminous... except
  where listed as an experimental population"). `dps.json` is the only report
  that carries both forms for the same population, so it's used as a
  translation table. For the handful that still don't match (a leopard's
  range phrased as a country list in one report and "Gabon to Kenya and
  southward" in another), a last-resort word-overlap match against the
  shared scientific name is used, gated at Jaccard > 0.3. Only 7 of 46 dated
  reclassification records needed that fallback in the 2026-09-22 build; the
  rest matched directly or through the DPS bridge. `build_payload.py` prints
  the exact count on every run -- check it hasn't grown before trusting a
  rebuild.
- **`listing_date` is the *original* listing date, even for a delisted
  entity.** The delisting date and reason live only in the joined
  `delisting_info` sub-table. Conflating the two would silently make every
  delisted species look like it was listed on the day it left the list.
- **The main timeline chart does not use `by_year.json`.** That report is
  pre-filtered to `statusCategory=Listed`, so it undercounts historical
  listings -- a species delisted since 1967 (the bald eagle, the gray wolf's
  Northern Rocky Mountain DPS) would vanish from its own listing year
  entirely. The page instead computes the year histogram itself, client-side,
  from every entity's own `listing_date` regardless of current status. 27
  entities (almost all older foreign listings) carry no listing date at all
  in FWS's own export and are excluded from every date-based chart.
- **Two single-day mass listings dwarf the rest of the timeline**: June 2,
  1970 added 248 species (mostly foreign, under the Act's 1969 predecessor
  law) and June 14, 1976 added 147 more. Verified directly against the
  `listing_date` field, not assumed -- the first draft of this page guessed
  at "a court settlement, a Hawaiian plants notice" without checking, which
  would have been wrong.
- **Critical habitat acreage is parsed from free text** (`crithab_measurement`,
  e.g. `"152190.6 acres"`) with a regex, and is not deduplicated across
  amendments to the same designation -- the habitat section says so.
- **`vipcode`'s first letter is a broad taxonomic code** (V=vertebrate,
  I=invertebrate, P=plant) but the page uses the cleaner `gn` / group_text
  field ("Flowering Plants", "Mammals", etc.) throughout instead.

## 4. The page

One template (`src/template.html`) with a `__PAYLOAD_B64GZ__` placeholder,
spliced by `src/inject.py` into `index.html`. The payload (species records +
candidate/DPS/state/group/boxscore aggregates) is gzipped and base64-embedded;
the page inflates it client-side with `DecompressionStream('gzip')`.

Layout: hero stat row -> intro -> canvas timeline (single accent hue, 1973
marked gold) -> status-category bar list -> the delisting-reasons finding (3
validated categorical colors) -> reclassification list + a gray-wolf callout
(one species, six simultaneous legal statuses, pulled live rather than
hand-typed) -> agency split + a migratory-species card grid (North Atlantic
right whale, sea turtles, Atlantic sturgeon, blue whale) -> a real US state
choropleth (see below) -> critical-habitat ranking -> five-year-review outcome
breakdown -> a full searchable/filterable/sortable explorer table over all
2,619 tracked entities, with a click-to-expand detail row -> methods & limits.

Typography and color tokens follow the shelf's house style (Fraunces serif
display / Archivo sans body / IBM Plex Mono figures; `--paper/--surface/--ink`
custom properties, light+dark via `prefers-color-scheme` and a `data-theme`
toggle). The categorical chart colors are the `dataviz` skill's validated
default 8-hue order (not reordered), checked with `validate_palette.js`
against this page's own surface colors before shipping -- see §5.

**The map** is not a novelty tile-grid guess. It's Wikimedia Commons' "Blank US
Map (states only).svg" (CC0), which encodes each of the 50 states + DC as one
real, geographically accurate `<path class="xx">` in a single flat 959×593
coordinate space -- no `<use>`/`<clipPath>` indirection to get wrong. The raw
SVG is in `src/raw/us_states_map2.svg`; `src/us_states_paths.svg` is the
extracted `<path>` markup actually spliced into `template.html`. Colors are
assigned client-side from `by_state.json` on a 5-step sequential blue ramp.
Puerto Rico, Guam, etc. aren't in this map (states only) and are listed
separately as text.

## 5. Verification checkpoints

Re-running the fetch on a later date **will** produce different numbers as FWS
adds and removes listings -- that's the point of fetching live. These are the
figures as pulled on **2026-09-22** and are the numbers to compare a rebuild
against for a sanity check, not a spec to match exactly:

| check | expected (2026-09-22 build) |
|---|---|
| Total listing entities, status_category = Listed | 2,478 |
| ...distinct species/populations (`sid`) among them | 2,327 |
| Total ever delisted | 141 (138 with a delisting date recorded) |
| Delisted for recovery / extinction / administrative error | 85 / 32 / 24 |
| Listed status breakdown: Endangered / Threatened / Experimental / Similarity-of-Appearance | 1,866 / 519 / 77 / 16 |
| Lead agency, Listed only: FWS / NMFS / FWS+NMFS jointly | 2,311 / 140 / 27 |
| Largest taxonomic group, Listed | Flowering Plants, 893 |
| Dated reclassification events matched to an entity | 51 (44 direct/bridged, 7 fuzzy) |
| Completed five-year reviews / share "No change in status" | 1,596 / 90.4% |
| Critical habitat designations attached to a tracked entity | 965 |
| Largest single critical habitat designation | Polar bear, 119,956,002.6 acres (2010-12-07) |
| Ivory-billed Woodpecker's live status | Endangered (extinction delisting proposed 2021, formally withdrawn 2024) |
| Gray wolf (*Canis lupus*) simultaneous entity statuses | Endangered, Threatened, Experimental Population, and Delisted (Recovery) across 6 total entities |

If any of the four bucket counts in the delisting-reasons row come back very
different, check `status` on the `Delisted` rows in `master.json` first --
FWS occasionally adds a new phrasing to the "Original Data in Error - ..."
family, which `build_payload.py`'s `delistBucket()`-equivalent groups by exact
string match.

## 6. What the page says about its own limits

Stated on the page itself, in "Methods & limits": entity vs. species-count
ambiguity, the reclassification join's fuzzy-match fallback, the 27 entities
with no listing date, non-additive critical-habitat acreage, and the explicit
choice to scope the main explorer to Listed + Delisted only (Candidates and
withdrawn candidates are referenced but not the explorer's unit of record).

## 7. Rebuilding

```
cd src
python fetch_species_data.py   # refetches raw/*.json from live FWS endpoints
python build_payload.py        # merges raw/*.json -> ../payload.json
python inject.py                # splices payload.json into template.html -> ../index.html
                                 # (also runs wrap_for_pages.py and add_catalog_link.py)
```

`raw/*.json` and `payload.json` are gitignored -- they're refetched, not
committed. `src/us_states_paths.svg` (the extracted map geometry) **is** worth
keeping even though it's derived, since re-deriving it means re-parsing
Wikimedia's zebra-striped decorative SVG variant by accident again (see the
build log: the first file tried, "Blank US Map, striped.svg", turned out to
render every state through a `<use>`+`<clipPath>`+`transform` indirection for
a striping gag, not a plain path -- "Blank US Map (states only).svg" is the
one that's actually flat).
