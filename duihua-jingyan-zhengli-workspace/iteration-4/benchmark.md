# Skill Benchmark: duihua-jingyan-zhengli

**Model**: <model-name>
**Date**: 2026-04-24T15:06:52Z
**Evals**: 1, 2, 3, 4 (1 run each per configuration)

## Summary

| Metric | Old Skill | With Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 52% ± 27% | 100% ± 0% | -0.48 |
| Time | 0.0s ± 0.0s | 0.0s ± 0.0s | +0.0s |
| Tokens | 1070 ± 713 | 2057 ± 1593 | -987 |

## Notes

- With-skill runs pass all 23 expectations; old_skill misses 11 of 23, so the new skill is materially more complete on this eval set.
- Eval 4 is the strongest discriminator because only the new skill covers post-edit closure and `skill-creator` compliance audit.
- Time metrics are unavailable in this round, so wall-clock comparisons are not meaningful.
- Token figures are output-size proxies from grading artifacts, not true model token telemetry.
