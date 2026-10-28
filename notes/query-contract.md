# Query execution contract

Status: preparation for review. No observational result is claimed.

The committed ADQL is a DR3 preparation artifact, not a successful archive run. The DR3 frequency and reference_time fields are documented at https://gaia.aip.de/metadata/gaiadr3/vari_eclipsing_binary/. Each execution needs UTC time, exact query hash, archive release, uploaded-table hash, row count and response hash.

Question B needs a candidate-to-aperture-member table from the upstream owner. Target-only membership is insufficient to rule out a blend. Join all aperture members and preserve candidate IDs and angular positions.

Question C selects positive frequencies below 0.01 per day. Brightness requires a separately validated B catalogue cross-match or colour conversion with its calibration domain and uncertainty; no universal G-to-B offset is assumed.

The planetary-transit query cannot be accepted from guessed DR4 column names. Compare the published schema to the draft transit fields, including the BJD-TCB time origin and mmag depth units, then commit the query and its DR3 stand-in execution log. Independent reruns and row counts remain acceptance requirements.
