# Deterministic query paraphrase audit

The 2026-10-21 audit used the checked-in CSV snapshot and an offline runtime. These
questions are independent regression inputs, not additions to the retrieval corpus
or the existing evaluation benchmarks. Results below were checked directly against
`fact_daily_peak` joined to `dim_b_column`, separately from the router and its SQL.

| Question | Before | After |
| --- | --- | --- |
| `2026/07台中#2非零出力幾天` | 182: parsed the whole year | 31: July only |
| `2026-07台中#2非零出力幾天` | 182: parsed the whole year | 31: July only |
| `20260709台中第2號機尖峰出力多少` | No offline candidate | 2026-07-09, 28.4 萬瓩 |
| `2026年7月9號台中第２號機的尖峰出力` | No offline candidate | 2026-07-09, 28.4 萬瓩 |
| `2026年7月9日出力前2名有哪些` | No offline candidate | 太陽能發電 844.2; 大潭 (#1-#9) 659.0 萬瓩 |
| `２０２６年７月９日出力最高的２名有哪些` | No offline candidate | Same two ranked results |
| `2026年7月9日非零出力由低到高排前兩名` | No offline candidate | 水里 0.7; 碧海 1.1 萬瓩 |
| `2026年7月台中#2有發電幾天` | 0: counted zero-power observations | 31 positive peak observations |
| `2026年7月台中#2總發電量多少度？` | Generic offline generation failure | `PEAK_SUM_ACROSS_DAYS` semantic refusal |

## Scope and meaning

The changes recognize numeric calendar months, compact day routing, `號` as a day
suffix, Arabic ordinal and fullwidth unit numbers, numeric top-N forms, and
`由低到高`. Unit aliases still resolve only against available column names. Ambiguous
`興達第3號機` / `興達第３號機` requests require clarification, preserving the distinction
between the coal unit and combined-cycle aggregate.

`有發電幾天` follows the existing positive-power-day intent: it counts days whose
recorded **system-peak-time** output is positive. A zero observation does not prove
the unit generated no energy throughout that day. Neither count measures energy.
Monthly energy requests now receive the existing refusal when an explicit
multi-day period and `發電量` are present. Monthly averages, counts, annual costs,
daily observations, and same-day power aggregation retain their existing guard
behavior. This is a narrow extension of the existing guard; it does not claim to
recognize every possible energy paraphrase.

The router, SQL validator and semantic SQL guard remain in the execution path.
The audit does not add quarter/date-interval interpretation, infer unavailable
unit data, or turn instantaneous peak observations into energy. Existing fallback
behavior applies to unsupported question shapes.

## Reproduce

```powershell
python -m pytest tests/test_query_paraphrases.py -q
```

The tests build SQLite from the checked-in sources, use the real offline runtime,
assert literal answer rows, verify that all three guards ran, and assert that the
successful paraphrases are absent from the retrieval examples. Additional cases
check ambiguity, date bounds, negative-day counts, energy refusals, and supported
metrics that must not be blocked.
