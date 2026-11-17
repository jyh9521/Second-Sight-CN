# Second Sight localization engineering

Read [the core standard](docs/LOCALIZATION_STANDARD.md), [acceptance gates](docs/ACCEPTANCE.md) and [project adaptation](docs/PROJECT_CONTRACT.md) before engineering work. The adopted baseline is a specification, not evidence that a feature exists. Provenance and conflicts are recorded in [baseline adoption](docs/BASELINE_ADOPTION.md).

## Task routing

- Text extraction, merging or translation: [data contract](docs/DATA_CONTRACT.md), [project data mapping](docs/PROJECT_CONTRACT.md), [workflow](TRANSLATING.md), then the locale style guide. Chinese work requires [STYLE](locales/zh-CN/STYLE.md) and the [glossary](locales/zh-CN/glossary.json).
- Fonts, image lettering or subtitles: [asset requirements](docs/ASSET_LOCALIZATION.md), [project resource inventory](docs/PROJECT_CONTRACT.md), and the relevant research record.
- Formats and runtime: [technical notes](TECHNICAL.md), [formats](docs/FILE_FORMATS.md), [pitfalls](docs/PITFALLS.md), then the specific file under `docs/research/`.
- Builds, installation and packaging: [build instructions](BUILDING.md), [installation standard](docs/INSTALLATION_STANDARD.md), [licensing](LICENSING.md).
- README: [README standard](docs/README_STANDARD.md). Completion or release claims: [acceptance gates](docs/ACCEPTANCE.md), [known issues](docs/KNOWN_ISSUES.md).

## Project constraints

- Do not launch, operate or attach to the game. The owner performs runtime acceptance. Offline tests are not G3 evidence.
- Preserve the original game, FusionFix and ReMade inputs. Work on independent output copies. Never upload full games, extracted source pools, dumps or third-party asset packs.
- Retain stable IDs, source fingerprints and protected native tokens. Generic tooling stays locale-neutral; game adapters live in `tools/` and `src/`, language decisions in `locales/<locale>/`.
- Existing data formats and measured engine contracts take precedence over example schemas. Record differences; do not invent review/runtime states or weaken the owner's punctuation rule.
- Keep only the latest two validated local package versions; validate a replacement before pruning older packages. Do not treat a documentation change as a reason to rebuild or delete a package. Preserve saves and user files. Validate absolute deletion targets first.
- Make small descriptive Git commits and push completed changes to the configured GitHub remote. Public fixtures must be synthetic.

## Before reporting

Run relevant tests and read back changed artifacts. Record exact commands, inputs, literal outputs, exit codes and candidate identities. Keep G1 data, G2 resources, G3 runtime and G4 distribution distinct. Pending editorial findings are build blockers, not an allowlist; do not ask for runtime tests of a new candidate before the agreed text/offline work is complete.
