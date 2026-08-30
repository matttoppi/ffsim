# Historical point-in-time projection source audit

Goal: obtain player forecasts observable before each historical target draft. These features are required to test projection residuals without using final-season information.

A source passes only if:

1. values are forecasts, not realized statistics;
2. an immutable source timestamp or custody timestamp predates the target draft;
3. rows are eligible only for drafts after that exact timestamp;
4. player identity maps to Sleeper IDs without name-only guessing;
5. personal research use is authorized;
6. the importer preserves raw bytes, source, season, observation time, and hash.

A Git commit can prove when this repository possessed exact bytes. It does not prove the provider's publication time, and it cannot cover drafts before that commit.

Attempts:

1. local 2024 PFF export with Git custody provenance;
2. Sleeper historical projection endpoints;
3. FantasyPros historical season endpoints with the configured personal API key.

No failed or temporally ineligible source enters model training.