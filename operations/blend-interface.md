# Blend-results interface for agreement

Status: preparation for review. No observational result is claimed.

This is an unsent interface proposal. No agreement with eumemic is claimed, and no message is sent by this change.

Proposed output is one row per candidate and aperture-member Gaia source: candidate_id, tic_id, dr2_source_id, dr3_source_id, dr4_source_id, aperture_definition_hash, membership_method, binary_flag_source, variability_table, epoch_product_hash, query_hash, retrieved_utc, quality_notes and reviewer. Missing cross-matches remain explicit rows.

The upstream owner decides the destination path and format, candidate/aperture version, release-day operator, signing person and review process. A binary flag is a triage signal; it is not a demonstrated false positive. Period, epoch, depth dilution and aperture contamination need separate checks.

Acceptance requires written owner confirmation of the interface and named operators, followed by a tiny transfer fixture whose IDs and row count are checked on both sides. Until then shared tooling can be tested locally, while candidate adjudication and publication remain blocked.
