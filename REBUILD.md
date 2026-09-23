# Rebuilding Wherever Found

Enough to reproduce this from scratch with a shell and no other context.

## 1. What this is

Every species entity the U.S. Endangered Species Act has ever listed, delisted or
reclassified, queried live from the two agencies' own databases rather than a
static export someone else cleaned first, and crossed against what was actually
spent on each one.

Two findings carry the page.

**"Delisted" is not a synonym for "recovered."** Of 141 delisting entities on
record, only 85 (60%) were removed because the species actually recovered. 32
went extinct first. The other 24 were never validly listed at all -- a taxonomic
reclassification or new information overturned the original listing decision. A
naive reading of "the number of listed species went down" as an environmental
win, without checking which bucket each delisting fell into, is the first trap
this build is designed to make impossible.

**NOAA Fisheries leads 7% of the list and absorbs two-thirds of the money.** 167
of 2,478 listing entities are NMFS-led or joint. In FY2022, $468m of the $734m
reported spent on listed species went to those species -- and in every one of
the four years parsed, the NOAA share runs between 58% and 64%. The three most
expensive species in the country are all Columbia Basin salmon or steelhead,
because recovering them means operating, and sometimes not operating, a
hydroelectric system. This is invisible in any listing count, which is why the
page exists.

## 2. Data sources

Three of the six are undocumented, one is PDF-only, and exactly one
(the Federal Register) is a real documented API.

### 2a. FWS ECOS (`src/fetch_species_data.py`)

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

### 2b. The NOAA and money sources (`src/fetch_noaa_data.py`)

| file | source | what it gives |
|---|---|---|
| `noaa_species_directory.json` | `https://www.fisheries.noaa.gov/species-directory/threatened-endangered-json` | **NOAA's own ESA list.** 105 species, 258 separately listed entities. The directory page offers CSV/JSON/XML exports of itself; this is the JSON one. Carries three fields ECOS has no column for: NOAA region, recovery plan status (Final / Draft / Under Development / blank), critical habitat status (Final / Proposed / Not Prudent / No / blank). |
| `expenditures_fy2019..2022.pdf` | `fws.gov` (four separate, inconsistently named URLs -- see the script) | The **Report to Congress on Federal and State Endangered and Threatened Species Expenditures**, required by ESA §18. Table 2 of each is a ranked list of every dollar any federal agency or state reported spending on each listed entity. ~25-30 MB each. No machine-readable release exists. |
| `sar_atlantic_2024.pdf` | `https://www.fisheries.noaa.gov/s3/2026-04/atlantic_2024_mmsars.pdf` | The Atlantic volume of NOAA's **2024 Marine Mammal Stock Assessment Reports**. Its Table 1 gives minimum abundance, Potential Biological Removal and observed human-caused mortality for 116 Atlantic and Gulf stocks. |
| `federal_register.json` | `https://www.federalregister.gov/api/v1/...` | ESA documents per agency: the `documents/facets/yearly` and `documents/facets/type` endpoints (which return counts without paging, unlike `documents.json`, which caps at 10,000 results over 50 pages), plus the 40 most recent documents each. |
| `federal_register_species.json` | same API, one call per species | how many FR documents name each NOAA species by its scientific name. |
| `natureserve.json` | `POST https://explorer.natureserve.org/api/data/speciesSearch` | global (G1-G5) and US national conservation rank per NOAA species. Public, unauthenticated, fast. 53 of the 105 come back ranked. |

**Which SAR volumes exist matters.** The 2024 Pacific and Alaska volumes are
*revision* volumes -- they contain only the 21 stocks revised that cycle and
have no cross-stock summary table at all. The full 2023 Pacific and Alaska
volumes (`Pacific_SARs_Final_2023.pdf`, `Alaska_SARs_Final_2023.pdf`, both under
`fisheries.noaa.gov/s3/2024-12/`) exist and are complete, but neither carries an
Atlantic-style summary table either, so this build is **Atlantic and Gulf only**
and the page says so in three places. Do not quietly present its counts as
national.

### 2c. What was looked at and rejected

Worth writing down so a rebuild does not spend the afternoon rediscovering it:

- **Stock SMART** (`apps-st.fisheries.noaa.gov/stocksmart`) is NOAA's fish stock
  assessment portal, but it covers commercially managed stocks, not ESA-listed
  ones. Wrong universe.
- **The InPort "SAR data" release** (`storage.googleapis.com/nmfs_odp_nefsc/PARR/READ/PSB/23307/23307_SAR_Data.zip`)
  is real, downloads cleanly, and contains a genuinely nice abundance / PBR /
  bycatch time series back to 1990 -- for 91 Atlantic stocks, last updated
  around 2015-2017. Too stale for a page whose whole claim is that it fetched
  live.
- **NOAA per-species pages** (`fisheries.noaa.gov/species/<slug>`) carry no
  structured data at all -- no JSON-LD, no consistent markup for the population
  estimate. Scraping 105 of them for a number is not worth the fragility.
- **The IUCN Red List API** needs a token. NatureServe does not, and answers a
  similar question.

## 3. Processing decisions, and the traps

### ECOS joins

- **Primary key is `id` (ECOS entity ID), not scientific name.** A single
  species can have several listing entities -- different Distinct Population
  Segments with different statuses. `recovery_plans.json`,
  `five_year_reviews.json` and `critical_habitat.json` all carry this same
  `entity_id`, and join cleanly. `delisted.json`'s `id` column is the same field.
- **`reclassified.json` has no entity_id at all**, only scientific name plus a
  short population label ("Western DPS"), while `master.json`'s population
  field (`desc`) is always the long form ("U.S.A., conterminous... except where
  listed as an experimental population"). `dps.json` is the only report that
  carries both forms for the same population, so it's used as a translation
  table. For the handful that still don't match (a leopard's range phrased as a
  country list in one report and "Gabon to Kenya and southward" in another), a
  last-resort word-overlap match against the shared scientific name is used,
  gated at Jaccard > 0.3. Only 7 of 46 dated reclassification records needed
  that fallback in the 2026-09-22 build. `build_payload.py` prints the exact
  count on every run -- check it hasn't grown before trusting a rebuild.
- **`listing_date` is the *original* listing date, even for a delisted entity.**
  The delisting date and reason live only in the joined `delisting_info`
  sub-table. Conflating the two would silently make every delisted species look
  like it was listed on the day it left the list.
- **The main timeline chart does not use `by_year.json`.** That report is
  pre-filtered to `statusCategory=Listed`, so it undercounts historical
  listings -- a species delisted since 1967 (the bald eagle, the gray wolf's
  Northern Rocky Mountain DPS) would vanish from its own listing year entirely.
  The page instead computes the year histogram itself, client-side, from every
  entity's own `listing_date` regardless of current status. 27 entities (almost
  all older foreign listings) carry no listing date at all in FWS's own export
  and are excluded from every date-based chart.
- **Two single-day mass listings dwarf the rest of the timeline**: June 2, 1970
  added 248 species (mostly foreign, under the Act's 1969 predecessor law) and
  June 14, 1976 added 147 more. Verified directly against the `listing_date`
  field, not assumed -- the first draft of this page guessed at "a court
  settlement, a Hawaiian plants notice" without checking, which would have been
  wrong.
- **Critical habitat acreage is parsed from free text** (`crithab_measurement`,
  e.g. `"152190.6 acres"`) with a regex, and is not deduplicated across
  amendments to the same designation -- the habitat section says so.
- **`vipcode`'s first letter is a broad taxonomic code** (V=vertebrate,
  I=invertebrate, P=plant) but the page uses the cleaner `gn` / group_text
  field ("Flowering Plants", "Mammals", etc.) throughout instead.

### Parsing the expenditure PDFs (`src/parse_esa_pdfs.py`)

Table 2 of each report is one row per listing entity:

```
<rank> <common name> (<scientific name>) - <population> <status> $<total> $<cumulative>
```

wrapped across up to five lines by the PDF's own layout. Do not try to
reconstruct the line breaks.

- **Flatten the table to one string and anchor on the pair of dollar figures.**
  Every row ends with exactly one `$x $y` pair and nothing else in the table
  does. The text between one pair and the previous one is the row.
- **The cumulative column validates the parse for free**, and this is the
  single most important thing in the file. Cumulative is a running sum, so it
  must never decrease, and the last row's cumulative must equal the sum of every
  total. FY2019 prints cents and reconciles to the penny; FY2020-22 print whole
  dollars and drift by a few dollars of rounding. The parser exits rather than
  write a year that does not reconcile. **A truncated parse of this table looks
  completely plausible** -- an early draft silently kept 3 rows out of 1,697 and
  printed a believable-looking total.
- **Trap: the tolerance cannot be exact for the rounded years.** An early
  version required `cum == prev + total` to the cent and broke at row 4 of
  FY2020, where 168,230,213 + 41,291,966 = 209,522,179 against a printed
  209,522,180. The fix is not a bigger epsilon but the weaker invariant above
  (monotone cumulative + a row that looks like a species), checked against the
  printed grand total at the end.
- **Trap: FY2021 prints two paragraphs of preamble between the table title and
  its first row.** Skip everything until the `Rank Species (50 CFR Part 17)`
  column header appears, or the preamble's mention of "Table 1" gets glued to
  the front of rank 1 and takes a $61m row's name with it.
- **Trap: ranks are not unique and not contiguous.** Entities with identical
  totals share a rank, which is why FY2019 has 2,061 rows but the rank column
  stops at 1,071. Do not key on rank, and do not "repair" the gaps.
- **Trap: the scientific name contains nested parentheses.** `Physeter catodon
  (=macrocephalus)`, `Dipodomys stephensi (incl. D. cascus)`. Scan for balanced
  parentheses and take the first group that opens with a capitalised genus; a
  non-greedy regex takes the wrong half. Four FY2019 rows have a genuinely
  unbalanced name in the source PDF and end up with no scientific name; all four
  are $7,488 foreign-species rows and do not matter.
- **Trap: FY2021 and FY2022 append `- See 50 CFR 223.102` to the population
  cell** for every NMFS-led entity. Strip it or the population join fails for
  exactly the species this page is about.

### Parsing the SAR summary table (`src/parse_esa_pdfs.py`)

The columns are `Updated? | Nest | CV | Nmin | Rmax | Fr | PBR | total M/SI |
fisheries M/SI | Strategic? | SAR year | last survey year | NMFS centre`, and
pypdf returns the species/stock/area cells as a run of one- and two-word
fragments followed by one line holding every numeric column. Anchor on the
numeric block; everything since the last anchor is the name.

Real values that each silently dropped rows in an earlier draft:

| in the PDF | why it breaks a naive parser |
|---|---|
| `3, 391` | a thousands separator that kept its space |
| `12.2-21.5` | an en-dashed range instead of a point estimate |
| `0 - -` | hyphens standing in for unknown |
| `7.6M` | millions, for the harp seal |
| `18 (0.09)` | a parenthesised CV riding along with the value |
| `1980- 2008` | a survey *period* rather than a survey year |
| `unk`, `undet` | unknown and undetermined, which are not the same as zero |

**The worst trap here is a number regex that allows an optional space before a
three-digit group** (added to cope with `3, 391`). Without requiring the comma,
`0 367` parses as one number and every column to its right shifts by one -- the
North Atlantic right whale comes out with PBR 14.8 instead of 0.73, which is
wrong in the most flattering possible direction and looks entirely reasonable.
Require the comma. The parser also refuses to write unless it recovers at least
95% of the rows its own ID column runs to.

Where the report gives a mortality range, the **low** end is used, so every
stock the page shows as over PBR is over PBR on NOAA's own most generous
estimate.

### Joining NOAA to FWS (`src/merge_noaa.py`)

- **The two agencies do not use the same scientific names.** FWS still calls the
  Hawaiian monk seal *Monachus schauinslandi*, NOAA calls it *Neomonachus
  schauinslandi*; the giant manta ray is *Manta birostris* to FWS and *Mobula
  birostris* to NOAA; the totoaba is *Cynoscion macdonaldi* to one and *Totoaba
  macdonaldi* to the other. Eight of NOAA's 105 species fail a literal match.
  The bridge is a species-epithet match **restricted to entities ECOS itself
  records as NMFS-led** -- an unrestricted epithet match marries the ringed seal
  (*Pusa hispida*) to a Hawaiian mint (*Phyllostegia hispida*).
- **`(=synonym)` forms have to be indexed both ways.** `Physeter catodon
  (=macrocephalus)` is one name to FWS and two to everyone else.
- **`Sousa chinensis taiwanensis` (Taiwanese humpback dolphin) is genuinely
  absent** from the FWS export under any name. It is not a bridging failure.
- **"NOAA-led" for spending is the union of both sources**, because either alone
  undercounts: ECOS misses species under the names NOAA uses, and NOAA's
  directory is species-level while money is reported per entity.
- **The ranked money lists on the page come from the report, not from the
  join.** 89-96% of each year's dollars join to a specific ECOS entity; the
  remainder is mostly taxonomic drift on the FWS side (*Picoides* vs *Dryobates
  borealis*). Deriving the rankings from the joined set instead would quietly
  drop $10-75m a year from the picture.

## 4. The page

One template (`src/template.html`) with a `__PAYLOAD_B64GZ__` placeholder,
spliced by `src/inject.py` into `index.html`. The payload is gzipped and
base64-embedded; the page inflates it client-side with
`DecompressionStream('gzip')`.

Layout: hero stat row (five stats) -> intro -> canvas timeline (single accent
hue, 1973 marked gold) -> status-category bar list -> the delisting-reasons
finding -> reclassification list + a gray-wolf callout -> agency split +
migratory-species card grid -> **the money section** (share bar, per-year tabs,
top-20 ranked bars with NOAA entities in the accent hue) -> **NOAA's own list**
(recovery plan and critical habitat bar lists, the taxonomy-disagreement
callout, the NatureServe G-rank scale, and a sortable 8-column table of all 105
species) -> **PBR** (the stocks over their limit, with the right whale callout)
-> **Federal Register** (per-agency year histograms, document-type split, live
recent-filings feed) -> a real US state choropleth -> critical-habitat ranking
-> five-year-review outcomes -> the full searchable explorer over all 2,619
tracked entities, each detail row now showing its per-year spending -> methods
& limits.

Typography and colour tokens follow the shelf's house style (Fraunces serif
display / Archivo sans body / IBM Plex Mono figures; `--paper/--surface/--ink`
custom properties, light+dark via `prefers-color-scheme` and a `data-theme`
toggle). The categorical chart colours are the `dataviz` skill's validated
default 8-hue order.

**One thing to know about colour in this file.** The original sections resolve
palette tokens to literal hex at render time (`cssvar('--c1')`), which means a
theme toggle after first paint leaves those colours stale until reload. The
sections added later emit `var(--c1)` into the inline style instead, so the
browser re-resolves them on toggle. The share bar in particular *must* stay
live: it prints `var(--ink)` text on its fill, and a stale fill under live ink
is unreadable. The canvas timeline and the map's sequential ramp genuinely need
resolved values and keep using `cssvar`.

**The map** is not a novelty tile-grid guess. It's Wikimedia Commons' "Blank US
Map (states only).svg" (CC0), which encodes each of the 50 states + DC as one
real, geographically accurate `<path class="xx">` in a single flat 959x593
coordinate space -- no `<use>`/`<clipPath>` indirection to get wrong. The raw
SVG is in `src/raw/us_states_map2.svg`; `src/us_states_paths.svg` is the
extracted `<path>` markup actually spliced into `template.html`. Colours are
assigned client-side from `by_state.json` on a 5-step sequential blue ramp.
Puerto Rico, Guam, etc. aren't in this map (states only) and are listed
separately as text.

## 5. Verification checkpoints

Re-running the fetch on a later date **will** produce different numbers as FWS
adds and removes listings -- that's the point of fetching live. These are the
figures as pulled on **2026-09-22** and are the numbers to compare a rebuild
against for a sanity check, not a spec to match exactly.

### ECOS

| check | expected (2026-09-22 build) |
|---|---|
| Total listing entities, status_category = Listed | 2,478 |
| ...distinct species/populations (`sid`) among them | 2,327 |
| Total ever delisted | 141 (137 with a delisting date recorded) |
| Delisted for recovery / extinction / administrative error | 85 / 32 / 24 |
| Listed status breakdown: Endangered / Threatened / Experimental / Similarity-of-Appearance | 1,866 / 519 / 77 / 16 |
| Lead agency, Listed only: FWS / NMFS / FWS+NMFS jointly | 2,311 / 140 / 27 |
| Largest taxonomic group, Listed | Flowering Plants, 893 |
| Dated reclassification events matched to an entity | 51 (44 direct/bridged, 7 fuzzy) |
| Completed five-year reviews / entities carrying one / share "No change in Status" | 1,596 / 1,595 / 90.4% |
| Critical habitat designations attached to a tracked entity | 950 |
| Largest single critical habitat designation | Polar bear, 119,956,002.6 acres (2010-12-07) |
| Ivory-billed Woodpecker's live status | Endangered (extinction delisting proposed 2021, formally withdrawn 2024) |
| Gray wolf (*Canis lupus*) simultaneous entity statuses | Endangered, Threatened, Experimental Population, and Delisted (Recovery) across 6 total entities |

### Expenditures

Each year's row total is printed by the report itself as "Total Ranked Species
Expenditures", and the parser will not write a year that misses it.

| fiscal year | entities | total reported | NOAA-led share |
|---|---|---|---|
| 2019 | 2,061 | $699,937,817 | $407,304,152 (58.2%) |
| 2020 | 1,697 | $1,083,913,007 | $697,808,654 (64.4%) |
| 2021 | 1,757 | $1,254,161,100 | $743,465,436 (59.3%) |
| 2022 | 1,685 | $734,489,243 | $468,326,140 (63.8%) |

Recognisable checkpoints: FY2019 rank 1 is Snake River fall-run Chinook at
$124,131,944 and rank 2 is Lower Columbia River steelhead at $111,152,581.
FY2022 rank 1 is Middle Columbia River steelhead at $42,178,771 and rank 4 is
the North Atlantic right whale at $29,440,195. 2,212 of the 2,619 tracked
entities end up with at least one year of spending attached.

### NOAA directory, SAR, Federal Register, NatureServe

| check | expected (2026-09-22 build) |
|---|---|
| NOAA species / separately listed entities | 105 / 258 |
| NOAA entities with no recovery plan recorded | 86 (33.3%) |
| NOAA entities where critical habitat was found "Not Prudent" | 9 |
| NOAA species needing a taxonomic-synonym bridge to reach ECOS | 6, plus 2 with no ECOS row at all |
| NOAA species ECOS credits to FWS alone | 3 (Chinese river dolphin, Indus river dolphin, vaquita) |
| Atlantic SAR stocks parsed / with both PBR and mortality / over PBR | 116 / 69 / 15 |
| North Atlantic right whale | Nmin 367, PBR 0.73, human-caused deaths 14.8/yr (10.8 from fishing gear) |
| Worst PBR ratio | Cuvier's and Gervais' beaked whales, Gulf of America: PBR 0.1 against 5.2 deaths/yr |
| Federal Register ESA documents, FWS / NOAA | 5,924 / 3,667 |
| FR document mix, NOAA | 74.1% notices, 15.4% proposed rules, 10.5% rules |
| FR document mix, FWS | 41.6% proposed rules, 38.9% notices, 19.5% rules |
| NatureServe ranks returned / G4 or G5 | 53 of 105 / 19 |
| All five Pacific salmon and steelhead species' global rank | G5 (secure), across 69 separately listed runs |

If the four bucket counts in the delisting-reasons row come back very different,
check `status` on the `Delisted` rows in `master.json` first -- FWS occasionally
adds a new phrasing to the "Original Data in Error - ..." family, which
`build_payload.py`'s `delistBucket()`-equivalent groups by exact string match.

## 6. What the page says about its own limits

Stated on the page itself, in "Methods & limits": entity vs. species-count
ambiguity, the reclassification join's fuzzy-match fallback, the 27 entities
with no listing date, non-additive critical-habitat acreage, the explicit choice
to scope the main explorer to Listed + Delisted only, and then for the new
sources: that the expenditure figures are self-reported and unaudited and
FY2022-latest; that "NOAA-led" is a union of two sources that disagree; that the
PBR comparison is Atlantic and Gulf only and that a stock with no PBR is not
therefore safe; that the Federal Register counts are a keyword search rather
than a register of ESA actions; and that a G5 global rank is not an argument
against a listing, because the Act's unit is the population.

## 7. Rebuilding

```
cd src
python fetch_species_data.py   # refetches raw/*.json from live FWS endpoints
python fetch_noaa_data.py      # NOAA directory, 4 expenditure PDFs, SAR PDF,
                               #   Federal Register facets + per-species counts,
                               #   NatureServe ranks. ~115 MB of PDFs, a few minutes.
python parse_esa_pdfs.py       # PDFs -> raw/expenditures.json, raw/sar_atlantic.json
                               #   exits nonzero rather than write a table that
                               #   does not reconcile against the document's own total
python build_payload.py        # merges everything -> ../payload.json
python inject.py               # splices payload.json into template.html -> ../index.html
                               #   (also runs wrap_for_pages.py and add_catalog_link.py)
```

`pypdf` is the one non-stdlib dependency (`pip install pypdf`).

`raw/*` and `payload.json` are gitignored -- they're refetched, not committed.
`src/us_states_paths.svg` (the extracted map geometry) **is** worth keeping even
though it's derived, since re-deriving it means re-parsing Wikimedia's
zebra-striped decorative SVG variant by accident again (the first file tried,
"Blank US Map, striped.svg", turned out to render every state through a
`<use>`+`<clipPath>`+`transform` indirection for a striping gag, not a plain
path -- "Blank US Map (states only).svg" is the one that's actually flat).

To check a rebuild without a browser: `node --check` on the extracted `<script>`
catches syntax errors, and the numbers each parser prints on stdout are the ones
in §5.
