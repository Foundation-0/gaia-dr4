# gaia-dr4

**Which earlier claims hold up once Gaia's fourth data release (DR4) is out?**

| Date | What happens |
|---|---|
| **Wednesday 25 November 2026, 12:00 CET** | The Gaia ESA Archive goes down until DR4. |
| **Wednesday 2 December 2026, about 12:00 CET** | DR4 is released and the archive reopens. |

Everything that needs ESA's archive must be ready before 25 November. The plan for that week is in
[RUNBOOK.md](RUNBOOK.md). The issues labelled
[`time-critical`](https://github.com/Foundation-0/gaia-dr4/issues?q=is%3Aopen+label%3Atime-critical) list what is
still to do.

Gaia is a spacecraft of the European Space Agency (ESA). It measured the positions, motions and brightness of about
two billion stars. Its fourth data release adds five and a half years of measurements, including each star's
brightness over time and the orbits of many binary stars (pairs of stars that orbit each other). Claims made before
DR4 can now be checked against it. This project asks three questions:

- **A. Planets validated by machine learning alone.** A validated planet is one accepted as real because the other
  explanations, such as a pair of eclipsing stars, were judged unlikely. Its mass was not measured. The scouting
  report counts about 540 planets validated by machine-learning models alone (not yet re-checked). Do they survive
  DR4's binary orbits and astrometric noise (extra scatter in a star's measured position, a sign of an unseen
  companion)? The answers feed Foundation0's [Ledger](https://fdn0.org/ledger/), its record of what AI has helped
  discover.
- **B. Blends among eumemic's TESS candidates.** NASA's TESS satellite finds planets by the small dip in a star's
  light when a planet passes in front of it. It sums the light in a small patch of pixels around each star, called
  the aperture. A faint eclipsing binary inside the same aperture can mimic a planet. This is a blend. Are any of the
  665 candidates of [eumemic/exoplanets](https://github.com/eumemic/exoplanets) (as of 14 Oct 2026) blends? Gaia's
  eclipsing-binary and variability flags for the stars in each aperture, and the target's own Gaia light curve,
  can tell.
- **C. Old eclipses on Harvard plates.** Which DR4 eclipsing binaries with periods over 100 days, and brighter than
  about B = 13.5 (brightness in blue light, where a smaller number means brighter), show eclipses on the Harvard
  photographic plates? The list goes to [plate-eclipses](https://github.com/Foundation-0/plate-eclipses).

Part of Foundation0's astronomy work ([astr0](https://github.com/Foundation-0/astr0)). It began in Foundation0's
[scouting](https://github.com/Foundation-0/f0/tree/main/deep-fields) of 18–19 October 2026.

**Status: preparing. No results yet.**

## What is known

Checked against their sources on 19 Oct 2026:

- The two dates at the top, from ESA's [Gaia news page](https://www.cosmos.esa.int/web/gaia/news).
- DR4's table of planetary-transit candidates, `vari_planetary_transit`, has 1,007 rows. Its table of eclipsing
  binaries, `vari_eclipsing_binary`, has 2,392,500 rows ([Gaia DR4](https://www.cosmos.esa.int/web/gaia/dr4)).

From the scouting report, not yet re-checked:

- DR4 covers 66 months, from 25 Jul 2014 to 20 Jan 2020. TESS observes in sectors of about 27 days each, and only
  sectors 1–20 overlap that span.
- Epoch photometry (each star's brightness over time) has about 121.8 billion rows, 7.2 TB. It is served only
  through DataLink, the archive's file service, and not through TAP, its query service. DR4 is about 400 TB in all.
- DR4 source IDs are independent of DR3. A table, `dr3_neighbourhood`, links them. The TESS Input Catalog
  (TIC v8.2) uses Gaia DR2 IDs. So a TESS target reaches DR4 in three steps: TIC to DR2, DR2 to DR3 through
  `dr2_neighbourhood`, then DR3 to DR4.
- On 14 Oct the archive renamed its DataLink structures, and limited each user to 5 concurrent jobs and a queue of 50.
- Gaia DR3's binary solutions refuted the validated planet K2-256 b
  ([arXiv:2310.12380](https://arxiv.org/abs/2310.12380)), and K2-399 b was demoted (A&A 2024).

The full list, with every source, is in [notes/scouting-2026-10-19.md](notes/scouting-2026-10-19.md). The complete scouting reports behind it are in [notes/reports/](notes/reports/README.md).

## Who else is working on this

From the scouting report, not yet re-checked:

- Gaia's own data processing team (DPAC) is writing "Gaia DR4: New transiting planet candidates and Gaia's view of
  known exoplanets" ([DR4 papers](https://www.cosmos.esa.int/web/gaia/dr4-papers)). It has already checked Gaia
  transit candidates against TESS (Panahi et al. 2022, [arXiv:2205.10197](https://arxiv.org/abs/2205.10197)).
- A Gaia DR4 sprint runs on 2–4 December at the Flatiron Institute in New York.

## What this project does not do

- It does not check DR4's 1,007 transit candidates against TESS. Gaia's own team is doing that.
- It does not run the blend checks for eumemic's candidates here. That work belongs in eumemic/exoplanets. This
  repository holds only the shared tools.

## How a result is checked

- Before release day, every query runs without error against the DR3 tables that stand in for DR4.
- Every list states the query that made it and the date it ran.
- A known answer comes first. The check for question A must recover the DR3 refutation of K2-256 b before its DR4
  results count.
- What puts a validated planet in doubt (which binary orbits, how much astrometric noise) is written down before
  release day.
- On release day, table and column names are compared with the published DR4 data model before any query runs.

## How to contribute

Take an [open issue](https://github.com/Foundation-0/gaia-dr4/issues). AI agents start with [AGENTS.md](AGENTS.md)
and Foundation0's [JOIN.md](https://github.com/Foundation-0/f0/blob/main/JOIN.md). Agents coordinate in
[st0a](https://github.com/Foundation-0/st0a). Questions and ideas go to the
[forum](https://github.com/Foundation-0/f0/discussions). The lead is to be named. A person signs for every result.

## Files

| path | what |
|---|---|
| `README.md` | this page |
| `RUNBOOK.md` | the plan for 25 November to 2 December: what must be ready, the order of queries, limits, who runs what |
| `AGENTS.md` | the guide for AI agents |
| `CLAUDE.md` | makes Claude Code read AGENTS.md |
| `notes/scouting-2026-10-19.md` | the research so far, with sources |
| `notes/reports/` | the complete scouting reports, kept as written, and the fact-check |
| `.github/` | the pull request template and the task issue form |
| `LICENSE` | Apache License 2.0 |

## Licence

Apache License 2.0 ([LICENSE](LICENSE)), as for Foundation0's other repositories.
