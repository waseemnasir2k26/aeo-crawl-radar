## [2026.10] - 2026-10-12

- Public, self-hosted Python 3.11+ CLI (`aeo-crawl-radar`, MIT) that parses web server logs and reports which AI crawlers visited, what they fetched and which pages they never touched; PyYAML is the only runtime dependency.
- October 2026 review: tree, README and last commits re-checked; no parser, bot-list or CLI code changed this month. Last functional commit is still 2026-09-01 (v1).
- README clone URL pointed at `github.com/skynetlabs/aeo-crawl-radar`, which returns 404; corrected to `github.com/waseemnasir2k26/aeo-crawl-radar`. The footer contact links were consolidated into the standard Work with SkynetLabs section.
- Known gaps: `pyproject.toml` `Homepage` still points at the dead `github.com/skynetlabs/aeo-crawl-radar` path (manifest outside this release's allowed file set, left untouched); no CI workflow runs the pytest suite; the bundled bot list ages as new crawlers ship.
