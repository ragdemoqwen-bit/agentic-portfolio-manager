# Setting up CI

The OAuth app used in this environment doesn't have the `workflow` scope, so
the CI config is documented here instead of being committed. Paste the YAML
below into `.github/workflows/ci.yml` and push it yourself.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Lint
        run: ruff check portfolio_manager tests
      - name: Tests
        run: pytest -q
```
