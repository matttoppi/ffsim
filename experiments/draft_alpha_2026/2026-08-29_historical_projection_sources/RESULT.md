# Result

No tested source is eligible for leakage-safe historical projection features.

| Attempt | Data found | Point-in-time result |
|---|---:|---|
| Local PFF 2024 export | 514 rows | Rejected. Exact bytes exist and Git added them before kickoff, but no authoritative provider publication or download timestamp is retained. No provider player ID is present. |
| Sleeper 2024 and 2025 projection endpoints | 9,152 and 9,295 rows | Rejected. Available rows were modified in January after each season. They do not reconstruct preseason state. |
| FantasyPros personal API | 598 and 729 rows | Rejected. Historical season responses contain no observation timestamp. FantasyPros assigns historical and bulk access to its Commercial plan. |

Official access references checked on 2026-08-29:

- FantasyPros API access and licensing: https://www.fantasypros.com/api-data/
- Sleeper API non-commercial terms and rate guidance: https://docs.sleeper.com/

The repository must not train a historical projection feature from these responses. A future source needs immutable preseason timestamps, authorized historical access, and deterministic Sleeper identity mapping.