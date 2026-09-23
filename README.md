# 🦊 Wherever Found

**Every species the Endangered Species Act has ever listed, delisted or reclassified, verified live against the government's own database. Delisted doesn't mean recovered — less than two-thirds of the time it does.**

→ **[Open it](https://tnriley.github.io/wherever-found/)**

The Fish and Wildlife Service's ECOSphere database, queried live and merged into one page: 2,478 currently listed entities, 141 ever delisted, 51 dated reclassifications, 965 critical habitat designations and 1,596 five-year status reviews, each linking back to the government's own document. The flagship finding sits in the government's own bookkeeping: of 141 delisted entities, only 85 (60%) were removed because they recovered — 32 went extinct first, and 24 were never validly listed in the first place. The most-listed group of organisms in the country is not an animal: 893 flowering plants outnumber all mammals and birds combined. One species, the gray wolf, is simultaneously endangered, threatened, an experimental population and delisted-as-recovered depending on which state line you're standing next to. A fully searchable explorer covers every entity; a state-by-state map, a critical-habitat ranking topped by the polar bear's 120 million acres, and a spotlight on migratory ocean species NOAA Fisheries manages round it out.

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
- **[NOAA Fisheries, ESA Species Directory (marine and anadromous species jurisdiction, cross-checked against FWS's own agency field)](https://www.fisheries.noaa.gov/species-directory/threatened-endangered)** — US Government public domain
- **[Blank US Map (states only).svg, Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Blank_US_Map_(states_only).svg)** — CC0 1.0 Universal (public domain dedication)

Every figure on the page is computed from the data shipped with it. Check the page's own methods panel for how each number is derived and where it should not be pushed.

## Built with

python 3 stdlib, undocumented ECOS pull-reports REST API, entity_id / scientific-name join with a DPS-label bridge and word-overlap fallback, vanilla JS, canvas timeline, inline SVG choropleth, gzip + base64 payload.

## Licence

Code is MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source, listed above.

---

Part of [Quick Projects](https://github.com/TNRiley/quick-projects) — one self-contained thing, built in one session. First published 2026-09-22.
