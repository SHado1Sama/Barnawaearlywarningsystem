"""
Checks for cumulative.py (the supplementary model). Run: python test_cumulative.py
Prints PASS and exits 0 when all checks hold.
"""
import sys, os
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amc, cumulative

def D(mm_list, start=date(2024, 7, 1)):
    return {start + timedelta(days=i): v for i, v in enumerate(mm_list)}

cn = dict(zip(("I", "II", "III"), amc.curve_numbers()))

# 1. One-day spell: a single wet day gives exactly the SCS runoff at the fixed CN II
series = D([0, 0, 0, 0, 0, 0, 96.3])
out = cumulative.effective_runoff_series(series)
assert abs(out[date(2024, 7, 7)] - amc.runoff_mm(96.3, cn["II"])) < 1e-9, out

# 2. Ia charged once, not daily: two 15 mm days give zero each in v2 (Ia 22.5) but runoff in v3
assert amc.runoff_mm(15.0, cn["II"]) == 0.0
series = D([0, 0, 0, 0, 0, 15.0, 15.0])
out = cumulative.effective_runoff_series(series)
assert out[date(2024, 7, 6)] == 0.0 and out[date(2024, 7, 7)] > 0.0, out

# 3. Mass balance inside a spell: increments sum to cumulative runoff, never exceed the rain
series = D([0, 0, 0, 0, 0, 11.25, 12.83, 3.13, 1.03, 11.75])
out = cumulative.effective_runoff_series(series)
S = amc.retention(cn["II"]); Pc = 11.25 + 12.83 + 3.13 + 1.03 + 11.75
assert abs(sum(out.values()) - cumulative.cumulative_runoff(Pc, S)) < 1e-9
assert sum(out.values()) <= Pc

# 4. The bound bites: a 12-day wet run is charged Ia twice (spell cap 6 days)
series = D([0, 0, 0, 0, 0] + [20.0] * 12)
out = cumulative.effective_runoff_series(series)
assert 0 < sum(out.values()) < cumulative.cumulative_runoff(12 * 20.0, S)

# 5. A July-2024-like pattern (moderate rain every day, none above Ia) yields runoff in v3
series = D([0.17, 15.07, 2.02, 6.01, 5.65, 5.73, 0.41, 9.54, 0.08, 6.63, 1.22, 0.20, 3.06, 7.81,
            11.25, 12.83, 3.13, 1.03, 11.75, 13.38, 3.73, 6.88, 0.75], start=date(2024, 7, 1))
out = cumulative.effective_runoff_series(series)
assert sum(out.values()) > 0.0, out

print("PASS")

# 6. The curve number no longer depends on the antecedent rain: the same spell
# after five very wet days and after five dry days gives identical runoff
spell = [12.0, 14.0, 13.0, 15.0]
wet_first = D([25.0] * 5 + [0.0] + spell, start=date(2024, 1, 1))
dry_first = D([0.0] * 5 + [0.0] + spell, start=date(2024, 1, 1))
out_wet = cumulative.effective_runoff_series(wet_first)
out_dry = cumulative.effective_runoff_series(dry_first)
spell_days = [date(2024, 1, 7) + timedelta(days=k) for k in range(4)]
assert all(out_wet[d] == out_dry[d] for d in spell_days), (out_wet, out_dry)
assert sum(out_wet[d] for d in spell_days) > 0.0

# 7. No wet-season floor anywhere in this model: a January one-day spell also
# gives the CN II runoff (in v2 the floor applies only in July to September)
series = D([0, 0, 0, 0, 0, 0, 96.3], start=date(2024, 1, 1))
out = cumulative.effective_runoff_series(series)
assert abs(out[date(2024, 1, 7)] - amc.runoff_mm(96.3, cn["II"])) < 1e-9, out
