# Changelog

All notable changes to this project are documented in this file.

## [2026.10] - 2026-10-12

- Public, self-hosted Python 3.11+ CLI (`aeo-crawl-radar`, MIT) that parses web server logs and reports which AI crawlers visited, what they fetched and which pages they never touched; PyYAML is the only runtime dependency.
- October 2026 review: tree, README and last commits re-checked; no parser, bot-list or CLI code changed this month. Last functional commit is still 2026-09-01 (v1).
- README clone URL pointed at `github.com/skynetlabs/aeo-crawl-radar`, which returns 404; corrected to `github.com/waseemnasir2k26/aeo-crawl-radar`. The footer contact links were consolidated into the standard Work with SkynetLabs section.
- Known gaps: `pyproject.toml` `Homepage` still points at the dead `github.com/skynetlabs/aeo-crawl-radar` path (manifest outside this release's allowed file set, left untouched); no CI workflow runs the pytest suite; the bundled bot list ages as new crawlers ship.

## [2026.09] - 2026-09-16

- Maintenance review of aeo-crawl-radar — a public, self-hosted Python CLI that parses web server logs and reports which AI crawlers visited a site, what they fetched, and which pages they never touched.
- Status: single-package Python 3.11+ project (`src/aeo_crawl_radar`, version 0.1.0, MIT, PyYAML the only runtime dependency) with modules for bot identification, log parsing, DNS verification, sitemap-gap reporting, storage/diffing and the CLI, plus a pytest suite of five test modules with fixtures. Published as the console script `aeo-crawl-radar`.
- Reviewed September 2026: README Status section added and a CHANGELOG created; the repo is versioned as v2026.09. No parser, bot-list or CLI behaviour was changed, and the packaged version in `pyproject.toml` was intentionally left at 0.1.0.
- Known gaps: no CHANGELOG before this release; no CI workflow to run the pytest suite; the README notes the bundled bot list ages as new crawlers ship, so it needs periodic refresh; the `Homepage` URL in `pyproject.toml` points at `github.com/skynetlabs/aeo-crawl-radar`, which is not this repository's path.
