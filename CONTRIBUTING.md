# Contributing

## Development Setup

```bash
git clone https://github.com/tomqwu/aml_open_framework.git
cd aml_open_framework
pip install -e ".[dev,dashboard,api]"
make validate   # check all 5 specs
make test       # run unit + API tests (~20s)
```

## Adding a New Detection Rule

1. Choose a rule logic type: `aggregation_window`, `custom_sql`, `list_match`, or `python_ref`
2. Add the rule to an example spec (e.g., `examples/canadian_schedule_i_bank/aml.yaml`)
3. Include `regulation_refs` with specific citations
4. Add planted positive data in `src/aml_framework/data/synthetic.py`
5. Write a test that verifies the rule fires on the planted data
6. Run `make test` to verify

## Adding a New Dashboard Page

1. Create `src/aml_framework/dashboard/pages/NN_Page_Name.py`
2. Use `page_header()` and `show_audience_context()` for consistency
3. Do NOT import `streamlit` at module level in shared modules (breaks unit tests)
4. Register the page in `src/aml_framework/dashboard/app.py`
5. Add to the `PAGES` list in `tests/test_e2e_dashboard.py`
6. Add to `AUDIENCE_PAGES` in `src/aml_framework/dashboard/audience.py`
7. Take a screenshot and add to `docs/screenshots/`
8. Update page count in README.md and CLAUDE.md

## PR Process

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Write code + tests + docs + screenshots
3. Run locally before pushing:
   ```bash
   ruff format src/ tests/
   ruff check src/ tests/
   pytest tests/ --ignore=tests/test_e2e_dashboard.py -q
   pytest tests/test_e2e_dashboard.py -q   # Playwright (optional, runs in CI)
   ```
4. Push and open a PR against `main`
5. Wait for all 5 CI jobs to pass (lint, unit-tests, api-tests, e2e-dashboard, docker-build)
6. Get review and merge

## Key Rules

- **Never push to main without all tests passing locally**
- **Dashboard modules must lazy-import `streamlit`** — unit-test CI only installs `.[dev]`
- **Tests needing `jwt`, `fastapi`, or `streamlit` must use `pytest.mark.skipif` guards**
- **Every new feature needs: tests, screenshots (if UI), README update, CLAUDE.md update**
