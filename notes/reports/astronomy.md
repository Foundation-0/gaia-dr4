> The full report of the research agent that scouted astronomy and space science for Foundation0 on 19 October 2026, kept as it was written. It is model output: a fact in it was checked against its source only where [fact-check.md](fact-check.md) says so. Paths starting with `scratch/` were the scouting session's temporary folder; see [README.md](README.md) for where those files are now.

## Gaia DR4: checked against primary sources

**Release date.** Wednesday 2 Dec 2026, about 12:00 CET ([DR4 overview](https://www.cosmos.esa.int/web/gaia/data-release-4); [news, 7 May 2026](https://www.cosmos.esa.int/web/gaia/news)).
- DR4 covers 66 months of observations (25 Jul 2014 to 20 Jan 2020), with reference epoch J2017.5 and times in TCB ([DR4 content](https://www.cosmos.esa.int/web/gaia/dr4)).
- ESA says the contents are final only after validation ([release page](https://www.cosmos.esa.int/web/gaia/release)).

**Contents.** From ESA's content table, last updated 14 Sep 2026 ([DR4 content](https://www.cosmos.esa.int/web/gaia/dr4)):
- `vari_planetary_transit` (transit candidates): 1,007 rows, 8.6 MB, queryable with TAP.
- `vari_eclipsing_binary`: 2,392,500 rows, 419 MB, queryable with TAP.
- `epoch_photometry`: 121,845,163,512 rows, 7.2 TB, in the G, BP and RP bands. It is served **through DataLink only, not TAP**.
- `nss_two_body_orbit`: 5,901,111 rows. About 400 TB in total.
- The [draft data model](https://anonftp.cosmos.esa.int/pub/GAIA_PUBLIC_DATA/Gaia_DR4/dr4-prerelease/gaia-dr4-prerelease-draft-data-model_2026-06-26.zip) (June 2026) names the transit table's columns:
  - `transit_reference_time` (BJD-TCB − 2455197.5);
  - `transit_period`;
  - `transit_depth` (mmag);
  - `transit_duration`;
  - `num_in_transit`.

  So the folding checker can be written now.
- DR4 source IDs are "independent from Gaia DR3". A new table, `dr3_neighbourhood`, links the two.

**The 25 Nov date is correct, but yesterday's report cited the wrong source.** The release page it cited does not mention it.
- The [news item of 8 Oct 2026](https://www.cosmos.esa.int/web/gaia/news) says "the Gaia ESA Archive will be down as of Wednesday 25 November 2026 12:00 CET". It reopens Wednesday 2 Dec at 12:00 CET with DR4.
- Separately, an archive update on 14 Oct (same page) did two things:
  - it renamed the DataLink structures RAW and INDIVIDUAL to DATAMODEL_GAIA and DATAMODEL_STANDARD;
  - it limited each user to 5 concurrent jobs and a queue of 50.

**What the closure means for a TESS cross-check:**
1. It is a seven-day outage of ESA's archive, not a DR4 deadline. Nobody outside the Gaia processing consortium (DPAC) gets DR4 before 2 Dec.
2. It is the deadline for preparation that needs ESA's archive:
   - testing the DataLink fetcher under the new names and job limits;
   - downloading the DR3 helper tables, above all `dr2_neighbourhood`. The TESS Input Catalog (TIC v8.2) uses Gaia DR2 IDs, so this table is the first link to DR3.
3. The mapping from TIC to DR4 cannot be finished early. Map TIC to DR3 now, then DR3 to DR4 through `dr3_neighbourhood` on 2 Dec, or match positions at epoch J2017.5.
4. ESA's partner data centres (CDS, ASDC, ARI, AIP and Flatiron) also serve DR4. ESA's notice names only its own archive, so DR3 from a partner should stay reachable during the outage. *Unverified.* TESS data at MAST are unaffected.
5. Only TESS sectors 1–20 overlap DR4's time span; sector 20 ended 20 Jan 2020 ([sectors](https://heasarc.gsfc.nasa.gov/docs/tess/sector.html)). Later sectors test Gaia's ephemeris projected forward.
6. On release day the bottleneck will be epoch photometry: DataLink only, the 5-job cap, and peak load. Keep that target list short.

**Competition is heavier than yesterday's report said:**
- DPAC is writing "[Gaia DR4: New transiting planet candidates and Gaia's view of known exoplanets](https://www.cosmos.esa.int/web/gaia/dr4-papers)".
- The same team has already checked Gaia transit candidates against TESS full-frame images ([Panahi et al. 2022](https://arxiv.org/abs/2205.10197)). It also uses Gaia photometry to vet TESS candidates: 126 were confirmed on target and 124 turned out to be blended background binaries ([2209.05845](https://arxiv.org/abs/2209.05845)).
- There is also the NYC Gaia DR4 Sprint (2–4 Dec, Flatiron) and the three-week "Gaia Relay" ([sprint](https://mailman.sydney.edu.au/pipermail/asa/Week-of-Mon-20260504/007525.html), [relay](https://mailman.sydney.edu.au/pipermail/asa/Week-of-Mon-20260810/007628.html)).

A confirm/refute table for the 1,007 candidates will therefore partly exist on day one. A better use for eumemic is to run the check the other way. For each of eumemic's 665 candidates:
- check Gaia's eclipsing-binary and variability flags on stars inside the TESS aperture, to catch blends;
- check the target's own Gaia light curve.

## Candidates

### 1. plate-novae
- **Question:** Did any known Galactic nova erupt earlier, unnoticed, on the Harvard plates (1890–1989)? If so, it is a recurrent nova.
- **Why now:**
  - DASCH DR7 is the final release. Its API returned a light curve in about 1.3 s today.
  - Pagnotta & Schaefer estimate that 12–35% of known Galactic novae are recurrent ([1405.0246](https://arxiv.org/abs/1405.0246)).
  - Schaefer lists 402 Galactic novae ([2210.03181](https://arxiv.org/abs/2210.03181)).
- **Pilot run today.**
  - **Rule:** at least 3 plates from at least 2 plate series within 60 days, each at least 2 mag above the star's quiet level.
  - **Recovery:** on T Pyx, U Sco and RS Oph it recovered 6 of their 17 known eruptions from 1890–1989: T Pyx 1902, 1920 and 1944; U Sco 1936 and 1945; RS Oph 1933.
    - Four more eruptions show up on single plates.
    - Four of the seven misses fall in the 1953–69 "Menzel gap", when Harvard took few plates ([1601.03256](https://arxiv.org/abs/1601.03256)).
  - **False alarms:** none. I also ran the rule on two classical novae as controls (DQ Her, V603 Aql). Every multi-series cluster it raised, on all five stars, belongs to a known eruption or its decline.
- **A flag to check (unverified).** Relaxed to a single plate series, the rule flags RS Oph from 20 Mar to 18 Apr 1914.
  - Six plates show it at 8.5–9.6 mag, against a century median of about 11.
  - It is not seen on 13 Feb (fainter than 9.1) or on 25 Apr (fainter than 10.5).
  - I found no 1914 eruption in the literature. Schaefer infers hidden eruptions in 1907 and 1945 ([0912.4426](https://arxiv.org/abs/0912.4426)).
  - Against it:
    - five of the six plates are from one low-resolution series, with star images about 2′ across;
    - DASCH's own quality flag rejects two of the six;
    - Schaefer has searched these plates.

  The prior is low. Look at the plate images before anything else.
- **Who else is on it:** Schaefer, one star at a time ([V2487 Oph, 2405.01210](https://arxiv.org/abs/2405.01210); [KT Eri, 2210.10448](https://arxiv.org/abs/2210.10448)). An arXiv search for DASCH with nova(e) finds only two abstracts, from 2011 and 2020. I found no systematic sweep of DR7.
- **How a result is checked:**
  - plate cutouts from the API;
  - agreement across plate series;
  - SkyBoT at the plate's date, to rule out an asteroid;
  - a check of neighbouring stars.

  Report to CBAT, VSX or RNAAS.
- **First step:**
  - run the rule over the 402 Galactic novae and the Magellanic Cloud novae;
  - calibrate it on the 10 known Galactic recurrent novae;
  - inspect cutouts of the top 20 hits and of the 1914 plates.
- **Data and tools:** DASCH DR7 API, daschlab, VSX, Schaefer's 2022 table (VizieR J/MNRAS/517/6150).
- **Fits:** plate-eclipses (same API, same cutout checks).
- **Risks:** fast novae fall between plates; crowding in the Galactic bulge; plate artefacts.
- **Killed if:** the top 20 cutouts are all artefacts.

### 2. lost-eclipses
- **Question:** Which eclipsing binaries in the General Catalogue of Variable Stars (GCVS), most of them found on photographic plates, no longer eclipse in TESS?
- **Why now:**
  - The GCVS has 13,319 eclipsing binaries. 3,280 of them have periods under 10 days and peak brighter than mag 12 (VizieR B/gcvs, queried today), so every TESS sector should show at least two eclipses.
  - Eclipses that vanish mean the orbit plane is precessing, usually because a third star is pulling on it.
  - Borkovits et al. report vanished eclipses in two binaries in TESS's northern continuous viewing zone ([2604.04004](https://arxiv.org/abs/2604.04004)) and in Kepler triple systems ([2502.09480](https://arxiv.org/abs/2502.09480)).
- **Who else is on it:** the Borkovits group (Konkoly), but only within Kepler and TESS continuous-viewing-zone samples. An arXiv search (eclipsing + disappeared/ceased/vanished, 91 hits) found no all-sky search against the old catalogues.
- **How a result is checked:**
  - anyone can open the TESS light curve;
  - the DASCH plates show the old eclipses, which also confirms the right star;
  - Gaia DR4 epoch photometry (2014–20) dates the change.
- **First step:**
  - fix positions with Gaia;
  - pull TESS full-frame light curves (eumemic's set, or QLP/SPOC light curves at MAST);
  - run a box-least-squares search and fold at the GCVS period;
  - flag stars whose eclipse depth is below 20% of the GCVS amplitude;
  - check DASCH for the top flags.
- **Data and tools:** GCVS, VSX, TESS full-frame images, Gaia DR3, DASCH.
- **Fits:** eumemic and plate-eclipses together.
- **Risks:** wrong identifications in the GCVS; ellipsoidal or RS CVn variables misclassified as eclipsing; blended TESS pixels.
- **Killed if:** none of the top 20 flags shows plate eclipses at the right star.

### 3. dr4-long-eclipsers
- **Question:** Which long-period (P > 100 d) Gaia DR4 eclipsing binaries brighter than B ≈ 13.5 show their eclipses on the Harvard plates? Each would give a century-long ephemeris and dated predictions of its next eclipses.
- **Why now:**
  - DR4 brings 2,392,500 eclipsing binaries from 66 months of data. DR3 had 2,184,477 from 34 months ([2211.00929](https://arxiv.org/abs/2211.00929)).
  - VSX lists only 217 Algol-type eclipsing binaries with P > 100 d, and 24 with P > 1,000 d (CDS mirror of 10.3 million entries, queried today).
- **Who else is on it:**
  - DPAC's two DR4 eclipsing-binary papers;
  - ASAS-SN's search for long, deep dimmings ("Big Dippers"), using about a decade of data ([2507.19594](https://arxiv.org/abs/2507.19594));
  - DASCH work on single stars ([1602.06010](https://arxiv.org/abs/1602.06010)).

  No recent arXiv paper on long-period eclipsing binaries uses plates.
- **How a result is checked:**
  - retrodicted eclipses checked against DASCH plates, ASAS-SN, ZTF and ATLAS;
  - predicted eclipses checked by AAVSO observers, and by Rubin's public alerts in the southern sky.
- **First step:** write the TAP query now against the draft schema (`frequency` < 0.01 per day, `reference_time`, `derived_primary_ecl_phase`). Test it on the DR3 table and on VSX's 217 stars.
- **Data and tools:** Gaia DR4, DASCH, ASAS-SN, ZTF.
- **Fits:** plate-eclipses.
- **Risks:**
  - with only about two eclipses in 66 months, periods will be ambiguous (aliased);
  - ESA does not state DR4's maximum period;
  - plates only detect eclipses deeper than 0.3–0.5 mag.
- **Killed if:** there are fewer than about 20 suitable stars.

### 4. dr4-cold-transits
- **Question:** Do any planets or brown dwarfs found by Gaia DR4 astrometry, on orbits seen nearly edge-on, transit in TESS data (2018–26) at the times their Gaia orbits predict?
- **Why now:**
  - DR4 brings 5.9 million two-body orbits and 62 TB of epoch astrometry. The DPAC papers include "The Exoplanet Candidate Catalogue" ([papers](https://www.cosmos.esa.int/web/gaia/dr4-papers)).
  - Gaia orbits predict transit times to within a few months, or a few weeks at best ([Sozzetti et al. 2023](https://arxiv.org/abs/2302.00420)).
  - A transiting cold giant planet whose mass Gaia has measured would be rare and important.
- **Who else is on it:**
  - DPAC;
  - groups doing radial-velocity follow-up of DR3 candidates ([example, Mar 2026](https://astrobiology.com/2026/03/28/a-planetary-illusions-funeral-non-detection-of-a-gaia-dr3-exoplanet-candidate-and-the-role-of-intermediate-precision-radial-velocities-in-gaia-exoplanet-follow-up/));
  - the release-week sprints.

  I found no TESS transit search of the DR3 astrometric orbits.
- **How a result is checked:** look at the TESS light curve at the predicted transit time. Publish the next transit window.
- **First step:** write a calculator for the transit time and its uncertainty window, from the orbital elements and their covariance. Test it on the DR3 orbits.
- **Data and tools:** Gaia DR3 and DR4 orbits, TESS full-frame light curves (eumemic's set).
- **Fits:** eumemic.
- **Risks:**
  - the windows are longer than a TESS sector;
  - at 1 au only about 0.5% of orbits are aligned to transit;
  - some DR3 orbits have proved spurious;
  - crowded on day one.
- **Killed if:** fewer than 10 candidates have an inclination that allows a transit and a window shorter than 27 days.

## Rejected as crowded or closed, or deferred
- **Rubin.** Early Data Preview 2 came out on 27 Jul 2026 and the alert archive on 18 Jun ([RSP](https://rsp.lsst.io/updates/index.html)). Images and catalogues go only to holders of data rights, and data releases stay that way for two years. Only alerts are public worldwide ([policy](https://prompt-products.lsst.io/access/index.html)). This fails f0's open-data requirement.
- **SPHEREx.** Quick Release 2 has come out weekly since Oct 2025, and the mission team is already mapping PAHs, ices and 3I/ATLAS ([2603.25790](https://arxiv.org/abs/2603.25790)). I found no niche with a quick, checkable result.
- **Euclid.** DR1 has been split: about 1,900 deg² in Nov 2026, the rest in mid-2027 ([ESA](https://www.cosmos.esa.int/web/euclid/dr1-timeline)). The consortium owns the obvious science.
- **eROSITA-DE DR2.** Released 31 Jul 2026, catalogues only, western Galactic hemisphere ([MPE](https://erosita.mpe.mpg.de/dr2/)). Yesterday's lead 5 stays moderately crowded.
- **CHIME/FRB Catalog 2** (4,539 bursts, [2601.09399](https://arxiv.org/abs/2601.09399)). Follow-on papers are already out, and positions are only good to about 10′.
- **Gaia compact-object companions checked against TESS.** Already done for DR3 ([2207.05086](https://arxiv.org/abs/2207.05086)), and DR4 has its own team on it.
- **New meteor showers.** The Global Meteor Network team reports them itself within weeks ([eMeteorNews](https://www.emeteornews.net/2025/08/31/new-meteor-shower-in-eridanus/)).
- **Meteorite falls seen by weather radar.** Covered by Marc Fries (NASA) and the American Meteor Society ([ARES](https://ares.jsc.nasa.gov/meteorite-falls/events/amo-in)).
- **Sungrazing comets.** Covered by the Sungrazer Project ([NASA](https://science.nasa.gov/citizen-science/the-sungrazer-project/)).
- **Deferred:**
  - **PLATO's first field (LOPS2).** Launch is March 2027 ([ESA](https://www.cosmos.esa.int/web/plato/status-and-history)), and the known TESS candidates there are already catalogued ([2409.13039](https://arxiv.org/abs/2409.13039)). eumemic's candidates that are not TESS Objects of Interest (TOIs) would be a cheap add-on.
  - **VSX eclipsing binaries without periods.** There are 57,263. AAVSO volunteers already work on them, and the significance is low.

## Files
The pilot scripts for plate-novae are in the scratchpad: `erupt.py` flags eruptions and `fetch.sh` fetches the light curves.
- scratch/scripts/erupt.py
- scratch/scripts/fetch.sh

The light curves they fetched are in scratch/dasch/. Nothing was posted anywhere, and no repository files were changed.
