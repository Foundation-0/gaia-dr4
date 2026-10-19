# Runbook: 25 November to 2 December 2026

The plan for the week the Gaia ESA Archive is down, and for DR4's release day. The names under "Who runs what" are
still to be filled in. The lead confirms the plan once named.

| When | What happens |
|---|---|
| Wednesday 25 November 2026, 12:00 CET (11:00 UTC) | The archive goes down until DR4. |
| Wednesday 2 December 2026, about 12:00 CET (11:00 UTC) | DR4 is released and the archive reopens. |

## Ready before 25 November, 12:00 CET

Nothing can be fetched from the archive again until 2 December, so everything below is downloaded and saved first.

- [ ] Gaia DR3 IDs for every target list, mapped from TIC through `dr2_neighbourhood`
  ([#1](https://github.com/Foundation-0/gaia-dr4/issues/1)).
- [ ] A DataLink fetcher for epoch photometry, tested on DR3 with the new structure names and within the job limits
  ([#2](https://github.com/Foundation-0/gaia-dr4/issues/2)).
- [ ] The list of planets validated by machine learning alone, with sources, cross-matched with DR3 RUWE and binary
  solutions ([#3](https://github.com/Foundation-0/gaia-dr4/issues/3)). RUWE is a number that grows when a star's
  measured positions do not fit a single star.
- [ ] ADQL queries for `vari_eclipsing_binary` and `vari_planetary_transit`, written against the draft DR4 data model
  and tested on DR3 stand-ins ([#4](https://github.com/Foundation-0/gaia-dr4/issues/4)). ADQL is the archive's
  query language, a form of SQL.
- [ ] For question A, what puts a validated planet in doubt: which binary orbits, and how much astrometric noise.
- [ ] For question C, the brightness cut. Gaia does not measure B magnitudes, so "brighter than about B = 13.5"
  needs a conversion or a cross-match to a catalogue that has B.
- [ ] Every person who will run queries has their own archive account and has run the DR3 dry run.
- [ ] Names filled in under "Who runs what" ([#5](https://github.com/Foundation-0/gaia-dr4/issues/5)).

## While the archive is down, 25 November to 2 December

- Rehearse the release-day order on the saved DR3 results.
- List every DR4 table and column the queries rely on, so they can be checked against the published data model in
  step 1 below.

## Release day, 2 December

A proposed order, for the lead to confirm. Small queries come first, because later steps need their output. Epoch
photometry comes last, because it is large and comes only through DataLink.

1. Check that the archive is up, and that the table and column names match the draft data model. If they differ,
   fix the queries before running them.
2. Map DR3 IDs to DR4 IDs through `dr3_neighbourhood`, for every target list. Every later step needs this.
3. Question A: DR4 binary orbits (`nss_two_body_orbit`) and astrometric noise for the hosts of the validated
   planets.
4. Question B: eclipsing-binary and variability flags for the stars in each TESS aperture of eumemic's candidates.
5. Question C: eclipsing binaries from `vari_eclipsing_binary` with periods over 100 days and above the brightness
   cut. The list goes to [plate-eclipses](https://github.com/Foundation-0/plate-eclipses).
6. Question B: epoch photometry for the candidates' target stars, through DataLink.

Every list states the query that made it and the time it ran. Results start as claimed. A person signs before
anything leaves this repository.

## Limits and accounts

From the archive update of 14 Oct, as given in the scouting report and not yet re-checked:

- Each user may run at most 5 jobs at once, with at most 50 queued.
- The DataLink structures RAW and INDIVIDUAL are now called DATAMODEL_GAIA and DATAMODEL_STANDARD.
- DR4 epoch photometry is served only through DataLink, not through TAP.

Rules for everyone running queries:

- Use your own archive account. Never share credentials.
- The limits apply per account, so they cover every script and agent running under it.
- Expect the archive to be busy on release day. After a failed job, wait before trying again.
- Commit queries and the lists they produce. Keep bulk downloads, such as epoch photometry, out of git.

## Who runs what

| Job | Person | Backup |
|---|---|---|
| Lead: confirms the plan, decides changes on the day, signs results | to be named | to be named |
| Step 2: DR3 to DR4 IDs | to be named | to be named |
| Step 3: question A | to be named | to be named |
| Step 4: question B flags | to be named | to be named |
| Step 5: question C, and the hand-over to plate-eclipses | to be named | to be named |
| Step 6: question B epoch photometry | to be named | to be named |
| Release-day status post on the forum | to be named | to be named |
