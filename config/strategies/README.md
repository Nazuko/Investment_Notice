# Strategy condition files

Drop buy/sell rule files here later. The engine loads enabled strategy ids from `config/settings.yaml` and looks up implementations in `bot/strategies/registry.py`.

This folder is intentionally empty of real rules in the architecture phase so upcoming condition files can be added without rewriting the main loop.

Example (not loaded yet):

```yaml
# config/strategies/example.yaml
id: example
buy:
  - when: price_below_pct_of_cost
    pct: 5
sell:
  - when: price_above_pct_of_cost
    pct: 10
```
