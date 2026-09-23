# 🦊 Wherever Found

**Every species the Endangered Species Act has ever listed, delisted or reclassified, verified live against both agencies' own databases — plus who the money actually goes to. NOAA Fisheries leads 7% of the list and absorbs two-thirds of the spending.**

→ **[Open it](https://tnriley.github.io/wherever-found/)**

The Fish and Wildlife Service's ECOSphere database and NOAA Fisheries' own ESA directory, queried live and merged with four years of the spending report Congress is sent: 2,478 currently listed entities, 141 ever delisted, 965 critical habitat designations, 1,596 five-year status reviews, and $734 million of reported FY2022 expenditure parsed out of a PDF that has no machine-readable release. Two findings carry the page. First, of 141 delisted entities only 85 (60%) were removed because they recovered — 32 went extinct first and 24 were never validly listed. Second, NOAA Fisheries leads 167 of 2,478 listing entities and takes 64% of every dollar reported spent, because recovering a Columbia Basin salmon run means operating a hydroelectric system: the three most expensive species in the country are all salmon or steelhead. Alongside them sits the North Atlantic right whale, whose sustainable human-caused death limit is 0.73 animals a year against 14.8 actually killed — one of 15 Atlantic marine mammal stocks dying faster than NOAA's own arithmetic allows. A searchable explorer covers every entity with its spending history; a second table covers NOAA's 105 species with their recovery-plan status, global NatureServe rank and live Federal Register document counts; and a state choropleth, a critical-habitat ranking and a live rulemaking feed round it out.

## Running it

One self-contained HTML file. No build step, no server, no network access at runtime — open `index.html` in a browser, or serve the directory with any static host.

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## Rebuilding it from scratch

[REBUILD.md](REBUILD.md) is written for an LLM with a shell and nothing else: the data sources and their quirks, the processing decisions, the page's structure and interactions, and a table of expected values to check the result against.

## Source

The full build pipeline is in [`src/`](src/), with a README describing how to regenerate the page from scratch.

## Data

- **[U.S. Fish & Wildlife Service, ECOSphere (Environmental Conservation Online System) — species listings, delistings, reclassifications, five-year reviews, critical habitat and recovery plans, fetched live at build time via undocumented report endpoints](https://ecos.fws.gov/ecp/)** — US Government public domain
- **[NOAA Fisheries, ESA Species Directory — the agency's own list of the 105 species and 258 listed entities it leads, with region, recovery plan status and critical habitat status, taken from the directory's JSON export](https://www.fisheries.noaa.gov/species-directory/threatened-endangered)** — US Government public domain
- **[U.S. Fish & Wildlife Service, Federal and State Endangered and Threatened Species Expenditures — Reports to Congress, fiscal years 2019–2022; per-entity spending parsed from Table 2 of each PDF](https://www.fws.gov/library/collections/endangered-and-threatened-species-expenditures-reports)** — US Government public domain
- **[NOAA Fisheries, 2024 U.S. Atlantic and Gulf of America Marine Mammal Stock Assessments — abundance, Potential Biological Removal and human-caused mortality for 116 stocks, parsed from the report's Table 1](https://www.fisheries.noaa.gov/national/marine-mammal-protection/marine-mammal-stock-assessment-reports)** — US Government public domain
- **[Office of the Federal Register, Federal Register API — ESA rulemaking counts by agency, type and year, per-species document counts, and a live feed of each agency's most recent filings](https://www.federalregister.gov/developers/documentation/api/v1)** — US Government public domain
- **[NatureServe Explorer — global (G1–G5) and US national conservation ranks for every NOAA-managed species, via the public species search API](https://explorer.natureserve.org/)** — NatureServe Network Biodiversity Location Data, used under NatureServe's terms for non-commercial reference
- **[Blank US Map (states only).svg, Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Blank_US_Map_(states_only).svg)** — CC0 1.0 Universal (public domain dedication)

Every figure on the page is computed from the data shipped with it. Check the page's own methods panel for how each number is derived and where it should not be pushed.

## Built with

python 3 stdlib, pypdf, undocumented ECOS pull-reports REST API, NOAA Fisheries species-directory JSON export, self-validating PDF table parsers (reconciled against each report's own printed total), entity_id / scientific-name join with a DPS-label bridge, a taxonomic-synonym bridge and word-overlap fallbacks, vanilla JS, canvas timeline, inline SVG choropleth, gzip + base64 payload.

## Licence

Code is MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source, listed above.

---

Part of [Quick Projects](https://github.com/TNRiley/quick-projects) — one self-contained thing, built in one session. First published 2026-09-22.
