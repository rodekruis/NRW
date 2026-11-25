# Analysis

One-off research analyses that support a decision, such as a spike or the choice of a threshold. They are not part of the deployed pipelines.

- **One folder per analysis**, with its own `README.md`: the question, how to rerun it, and which data the committed results were made with.
- **Results are tracked:** tables, figures and the [Marp](https://marp.app) source of a slide deck, in `results/`. PDF exports of the decks are not tracked.
- **Dependencies** that only an analysis needs go in the `dev` group of `pyproject.toml`, and in the `DEP004` ignores of `[tool.deptry]`.
- **Checks:** ruff, vulture and deptry cover this folder through `python-knip.py`. Tests of an analysis are not run in CI.

Run a script from `data/`:

```bash
uv run python -m analysis.<folder>.<script>
```
