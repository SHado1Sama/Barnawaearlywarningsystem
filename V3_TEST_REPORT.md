# Barnawa EWS v3 (bounded cumulative abstraction): build and test report

Built and tested locally on 8 Nov 2026, then pushed to GitHub the same
day at the owner's go-ahead: v3 is live on the dashboard as a
supplementary experimental advisory. The primary model remains v2, and
v3 never drives the headline level.

## What was built (folder: barnawa-cumulative-v3)

- cumulative.py: the bounded cumulative abstraction model. amc.py and
  forecast.py are byte-for-byte copies of the v2 files on GitHub, so the
  comparison isolates the one change.
- test_cumulative.py: unit checks. Result: PASS. They prove (1) a one-day
  spell reproduces v2 exactly, (2) Ia is charged once per spell, so two
  15 mm days that each give zero in v2 give runoff together in v3,
  (3) mass balance inside a spell, increments sum to the cumulative runoff
  and never exceed the rain, (4) the 6-day cap bites, a 12-day wet run is
  charged Ia twice and yields less than the unbounded formula.
- replay_v3.py plus daily_replay_v3.csv and replay_v3_summary.json: the
  full 36-year replay, scored with the identical definitions as the v2
  replay (alert day, verified within the 7-day horizon, episode caught if
  an alert was issued within 7 days before the peak). Scoring rule, stated
  once here and used for every false-alarm figure in this report: a false
  alarm day is an alert day after which no day at or above the Watch
  discharge (1,836 m3/s) occurs within the following 7 days. The figures
  count DAYS under that rule. Counting clusters or occasions instead
  gives different numbers; the occasion counts printed on the dashboard
  are defined in Addendum 4.

## The bound that was chosen, and why

From a sweep of spell caps (3 to 14 days), dry breaks (1 and 2 days) and
abstraction-store recovery rates (the cap by dry-gap sweep is
reproducible with sensitivity_grid.py in this repo),
the selected design is: spell cap 6 days, dry break 1 day, lambda 0.20.
Six days is the storm day plus the 5 antecedent days the AMC logic already
treats as the soil's memory, so the accumulation window is the model's own
timescale, not a new free parameter. The store variants caught nothing
extra at any recovery rate, so they were dropped.

## Results, same scoring for all three models (floor ON)

| Model | Alert days | Verified | False alarm days | Episodes caught |
|---|---|---|---|---|
| v2 (current, GitHub) | 12 | 10 | 2 | 2 of 6 (2004, 2012) |
| v3 raw cumulative (unbounded) | 588 | 25 | 563 | 5 of 6 |
| v3 bounded (this build) | 68 | 16 | 52 | 4 of 6 (1999, 2004, 2012, 2014) |

Episode detail for v3 bounded, floor on: 1999 caught, 2 days lead; 2004
caught, 2 days lead; 2012 caught, 3 days lead; 2014 caught with 0 days
lead (the first alert is on the peak day itself, so it is detection on
the day, not advance warning); 2008 and 2024 still missed. Best forecast
in the 14 days before the 2024 peak: about 86 m3/s against a 342 trigger,
better than v2's 67 (baseflow only) but nowhere near catching it. Without
the wet-season floor, v3 catches only 2 of 6, so the floor remains
load-bearing.

## Regression found in the case studies

Under v3, the 2022 case season produces 6 alert days (3 to 8 Sep 2022)
where v2 produces none. The 2022 observed peak was 1,634 m3/s, below the
Watch threshold, so those are false alerts in the very season v2's
baseflow-aware triggers were designed to keep quiet. The 2012 case season
behaves correctly under v3 (alerts 24 to 29 Aug, peak caught).

## Verdict

The acceptance criteria set in the design note were: more episodes
caught, alert days kept in the tens, and no unrelated false alarm events.
The bounded build meets the first two (4 of 6, 68 alert days) and fails
the third (52 false alarm days, including a false alert spell in 2022).
Recommendation: do NOT replace v2 with v3, and do not push v3 as the
model. v3 is a detection-first variant: it would suit a setting where
missing a flood costs far more than a false alert, and it is kept here,
tested and ready, if that trade is ever wanted. The 2024 problem is not
solved by any abstraction variant tested; the evidence still points to
the observed 2024 rise being a cumulative flow response that a quickflow
SCS model with a fixed monthly baseflow does not represent.

## Addendum, 8 Nov 2026: what the 52 false alarm days are

The 52 false alarm days (floor on) fall in 14 clusters, not 52 separate
incidents. Every cluster follows genuinely extreme rain: in all 14 cases
more than 120 mm fell in the prior 10 days (range 122 to 189 mm), and all
are in the peak wet season. None is a dry-weather phantom. They divide
into three groups:

Trailing or same-event alerts, 18 days, defensible:
- 30 Jul 1999 (1 day, the day after the 1999 peak; river still at 75% of Watch)
- 28 to 29 Aug 2004 (2 days after the 2004 episode ended; river at 72%)
- 23 to 31 Aug 2008 (9 days starting two days after the 2008 peak; the
  river reached 93% of Watch again on 25 Aug during the cluster)
- 28 to 29 Aug 2012 (2 days after the 2012 episode ended; river at 81%)
- 18 to 19 and 23 to 24 Aug 2014 (4 days after the 2014 episode; the
  river rose again to 1,815.6 m3/s on 26 Aug, 99% of the 1,836 Watch
  threshold, missing it by about 1%)
These count as false only because scoring looks 7 days forward from each
alert; the flood they belong to was just behind them or, in 2014, a
whisker below the threshold ahead of them.

Near misses, 16 days, understandable but still false as Watch alerts:
- 28 to 30 May 1991 (river reached 76% of Watch, the 1991 annual maximum)
- 18 to 23 Aug 1993 (65% of Watch)
- 21 to 27 Jul 1998 (66% of Watch)
Heavy rain, a real river response, but only about two-thirds of the way
to Watch. As advisories these would have been reasonable; as Watch
alerts they are false.

Genuine overforecasts, 18 days, not justifiable:
- 18 to 19 Aug 1995 (river reached only 39% of Watch)
- 28 to 30 Jul 2001 (40%)
- 20 to 23 Aug 2007 (52% in the alert horizon)
- 25 to 27 Aug 2018 (44%)
- 27 Aug to 1 Sep 2021 (37%; the worst cluster, forecast up to 127% of
  its trigger while the river stayed at about a third of Watch)

Root cause, common to all three groups: once Ia is paid inside a spell,
later moderate rain converts to runoff at a high marginal rate, and
back-to-back spells stack unit hydrographs, so sustained wet spells are
translated into Watch-level quickflow even when the real river, which
loses much of that water to storage and slow pathways, responds far less.
The triggers, scaled on the single storm-driven 2004 event, do not
correct for this in volume-driven spells.

## Addendum 2, 8 Nov 2026: can the false alarms be fixed, and is the floor still needed?

Fixes tested against the same replay scoring (v3, floor on, baseline
68 alert days, 52 false, 4 of 6 caught):

1. Raise the triggers. A margin on the triggers, or recalibrating them
   on v3's own 2004 forecast (v3 predicts 2004 at 926 m3/s, so its
   quickflow factor is 0.220, not v2's 0.155): at a 1.5x margin the
   false days fall to 4, but the catches fall back to 2 of 6, the same
   as v2. At recalibrated triggers: 28 alerts, 18 false, still 2 of 6.
   Reason: the extra catches (1999 barely over its trigger, 2014 caught
   on its peak day) are the same forecast strength as the false
   clusters, which reach up to 1.7x trigger (1998). No threshold
   separates them; a threshold only slides along the trade.
2. Slow routing. Routing only the accumulated part of v3's runoff
   through a slow reservoir instead of the quickflow unit hydrograph,
   keeping v2's storm runoff on the hydrograph: tau 5 days gives
   41 alerts, 29 false, 3 of 6 caught; tau 10 and 20 days fall back to
   2 of 6. A better trade point, but the same trade.
3. Hybrid (v2 alerts OR v3 alerts at recalibrated triggers): 28 alerts,
   18 false, 2 of 6. No gain over v2 alone.

What would actually change the trade rather than slide along it:
- Two-tier alerting, available today with no model change: v3 alerts
  are issued as Advisory (prepare, monitor), and only v2 alerts, or a
  v3 alert confirmed by the river itself rising through the Advisory
  flow (1,357.7 m3/s, which the live dashboard already monitors), are
  issued as Watch. Every v3 catch survives as at least an advisory;
  Watch keeps v2's discipline (12 alerts, 2 trailing false days).
- Hourly rainfall. The false clusters and the real events have similar
  DAILY totals, but real events are storm-driven and the false ones are
  volume spells. Intensity is the difference, and only sub-daily data
  carries it. The case studies already run on hourly rain; a 36-year
  hourly ERA5 series is the data upgrade most likely to separate them.
- Continuous moisture-varying retention (SWAT, Mishra-Singh) in place
  of the three-step AMC, a research change, unproven on this record.

Is the wet-season floor still necessary under cumulative abstraction?
Partly, and its job has changed. Numbers (episodes caught):
    v2: floor off 1 of 6, floor on 2 of 6 (the floor alone saves 2012)
    v3: floor off 2 of 6, floor on 4 of 6 (adds 1999 and 2014)
The floor's original job, the 2012 miss, is now done by accumulation
alone: v3 catches 2012 with the floor off. But the floor still earns
its place in v3, because the curve number is fixed at spell start from
the 5 days before the spell. A spell that starts after five dry-ish
days in August still starts at AMC I (Ia 53.5 mm) and stays there for
six days; 1999 and 2014 were exactly such dry-start wet-season spells.
The floor is a patch for the AMC rule's five-day amnesia: after five
dry days in September it calls the soil dry even in a wet season. A
moisture store with a longer memory would make the floor redundant
naturally, and retiring it should be tested on the replay at that
point. Until then, removing it costs catches in both models.

## Addendum 3, 8 Nov 2026: sensitivity of the two design settings, and the in-sample warning

The user asked for a pre-push check on the two settings chosen for this
model, spell cap and dry gap, and on how the result may honestly be
stated. Grid over the same replay (floor on throughout):

    cap  gap   alert days   false days   caught   episodes
      4    1           36           26      2/6    2004, 2012
      4    2           44           34      2/6    2004, 2012
      6    1           68           52      4/6    1999, 2004, 2012, 2014
      6    2           73           59      3/6    1999, 2004, 2012
      8    1          117          100      5/6    1999, 2004, 2008, 2012, 2014
      8    2          174          154      5/6    1999, 2004, 2008, 2012, 2014

Reading: 4 of 6 does NOT hold across the grid, so the result is not
robust in that strong sense. But there is no knife edge at exactly
6 and 1 either: catches rise smoothly with the cap (2, 4, 5 of 6) and
false days rise with it, so (6, 1) is a middle point on a smooth trade,
chosen for the balance, not a magic setting. One genuine sensitivity:
at cap 6 the 2014 catch depends on gap 1; with gap 2 it is lost. At
cap 8 the model also catches 2008, at the price of 100 false days.

In-sample warning, which must travel with this model wherever it is
shown: v3 was designed after studying why the six recorded events were
missed, and then scored on those same six events. The honest claim is
"built to catch build-ups, and it does on the record it was designed
on". It is not a proven 4 of 6. Only future flood seasons test it.

Occasion count for plain-language use: the 68 alert days group into
14 occasions (clusters). A flood followed on 4 of those occasions;
on 10 occasions no flood followed. (Counting clusters of false days
alone gives 14, because the trailing days after the 1999, 2004, 2012
and 2014 floods form their own clusters; the occasion count of 10
unnecessary advisories is the cleaner figure.)

## Addendum 4, 8 Nov 2026: the record at the Advisory trigger, and a citation correction

The dashboard card signals at the Advisory trigger, so it must print
the record at that trigger, not the Watch-trigger record. Scored at
the Advisory trigger (forecast triggers scaled to the Advisory design
flow of 1,357.7 m3/s), floor on, same replay:
- 206 alert days in 31 occasions (occasions split when the gap between
  alert days exceeds 2 days; this definition is now used for both
  tiers, and the Watch-tier occasion count is unchanged by it:
  14 occasions, a flood following on 4, not on 10).
- A signal in 19 of 36 years, about once a year; alert days by month:
  August 129, September 47, July 23, May 7.
- Episodes preceded: 5 of 6 (1999, 2004, 2008, 2012, 2014). At this
  level only 2024 is missed; the earlier statement "missing 2008 and
  2024" is correct only at the Watch trigger.
- Scored against the Advisory flow itself: on 13 of the 31 occasions
  the river went on to reach 1,357.7 m3/s within the alert window, and
  on 10 of the other 18 occasions it still rose to between 1,000 and
  1,357.7 m3/s. On 8 occasions it stayed below 1,000 m3/s.
The card and README now print this tier's record first, with the
Watch-trigger record as a secondary line.

Citation correction: the cumulative procedure is NRCS National
Engineering Handbook, Part 630, Chapter 10, section 630.1002(c)
("Runoff during a storm"), worked as Example 10-6. Earlier drafts
cited "Part 630, Subpart H", which does not appear in the chapter.
The handbook applies the procedure within a single storm; extending
it across the days of a wet spell, and the 6-day cap and 1-day dry
break, are this project's own heuristics, and the code and README
now say so.
