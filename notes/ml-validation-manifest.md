# ML-validation planet manifest

Status: preparation for review. No observational result is claimed.

One row represents one planet, rather than one host. Required fields are planet_name, host_name, validating_bibcode, paper_table_row, validation_method, ml_only_decision, decision_reason, gaia_dr3_source_id, ruwe, nss_solution_type, source_query_sha256 and retrieved_utc. Unknown values remain null; duplicate host names do not collapse planets.

Export NASA's planetary-system table with its reference fields and preserve the exact TAP query and response hash. A paper-level classification is required: machine learning used in detection is not automatically machine-learning-only validation. Treat the scouting counts 301, 69, 50 and 118 as reconciliation targets, not an additive accepted total. A planet appearing in multiple papers gets one row with multiple provenance records.

For each accepted host ID, join DR3 gaia_source for RUWE and retain every nss_two_body_orbit solution. An absent solution is not evidence of singleness. Keep the binary interpretation separate from the planet-validation decision.

Before any DR4 comparison, reproduce the K2-256 b known-answer case from its cited study and record the source ID, solution type and reasoning. The K2-399 claim also needs a primary-paper check. No live query, planet list or refutation is claimed by this packet.
