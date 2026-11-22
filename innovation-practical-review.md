# CampusFlow — college innovation practical

## 22 November 2026 · Project review

Vinay supplied a friend's single-file timetable prototype for inspection. This entry records the reviewer's tests in an isolated browser profile. Student execution, authorship of changes and viva recall have yet to be assessed. The review left Index.html intact.

| Test | Observed result |
|---|---|
| Open View Timetables on a fresh start | The selected class had a blank output area. Clicking its class button invokes the missing render. |
| Generate all four default classes | 120 lectures scheduled. An independent count found zero repeated teacher or room bookings in the same indexed slot. The combined CSV routine supplied 121 rows including the header. The downloaded file itself was not tested. |
| Keep those timetables and regenerate SE-A alone | The interface reported success. The four visible schedules together had 12 repeated teacher bookings and 18 repeated room bookings in that run. Counts depend on random choices. |
| Delete a classroom after generation | The combined CSV routine still returned 29 lectures in the deleted room in this run. Subject changes use the same save-without-invalidation pattern. |
| Save Monday with overlapping periods 09:00–10:00 and 09:30–10:30 | Both periods were accepted. Saving cleared the stored schedules while leaving the previous table displayed. |

## Proposed practical scope

1. Reserve all existing bookings for unselected classes during regeneration. Validate the combined schedule before saving. If regeneration fails, retain the last valid schedule.
2. Invalidate affected schedules when requirements or resources change. Refresh the viewer on entry and after invalidation. Parse 24-hour time ranges and reject overlaps, duplicate days and reversed ranges.
3. Add teacher and room capacity checks before search. With four default classes, 120 lectures and three rooms, only 90 room-periods are available. State the 30-period shortage directly.
4. Compare the existing greedy algorithm with constraint-based search. Choose a lecture with the fewest legal placements and backtrack when a choice blocks completion. Report completed lectures, clashes, runtime and success rate on identical inputs across repeated runs. These are proposed features and experiments.
5. An optional AI/ML department example is a two-period Machine Learning Lab that requires a computer lab. A separate ML experiment could predict whether the baseline scheduler succeeds within a fixed time from demand and resource counts. Compare against predicting the most common outcome and hold out entire timetable configurations for evaluation.

Suggested first student exercise if adopted: generate all four classes, regenerate only SE-A, and identify one conflicting teacher or room booking in the combined output. No revision exercise or implementation was completed in this review.

## 22 November 2026 · Implementation and browser verification

Implemented the constraint scheduler, independent validation, explicit capacity checks, clock-time validation, affected-schedule invalidation, viewer refresh and configurable double labs in the standalone Index.html. Fresh sample data allocates two TE-A periods to Machine Learning Lab. Existing saved catalogues retain their subjects and rooms.

Assistant-run verification in a temporary browser profile: 12 fresh generations completed with 120/120 periods. Downloaded and parsed the combined CSV, verified 120 distinct teacher/time and room/time combinations, and observed both ML lab periods in the Computer Lab on Tuesday from 14:00 to 16:00 in the final test. Reload preserved all four schedules. Regenerating SE-A left the other three tables identical. Overlapping times were rejected and deleting an ordinary room produced the 30-period shortage. The solver has a bounded search time and can report a timeout on harder inputs.

Next student step: generate all divisions, inspect TE-A's double lab, then regenerate SE-A and explain why the validator still checks all four divisions. Student demonstration and viva recall are pending.

## 22 November 2026 · Python app and ML practical

**Run the project.** From the project folder run `python app.py` and open http://127.0.0.1:5000/. Flask is the only additional runtime dependency. SQLite is included with Python. If preparing another computer, install the dependencies in requirements.txt before going offline. The fitted decision tree is bundled in difficulty_model.json. Retraining is optional and uses `python train_model.py` with scikit-learn (tested with 1.9.0). SQLite creates campusflow.sqlite3 on first access. Keep this file to retain the workspace.

**Exam demonstration.** Select all four divisions, predict difficulty, then generate. The default predicts “Likely straightforward” and completes with zero backtracks. Inspect the two Machine Learning Lab periods for each third-year division. Regenerate Second Year A alone and validate all divisions. For the shortage demonstration, remove Room 101 in College details and request all four divisions. The app reports a 30-period shortage. Add Room 101 again and regenerate afterwards. To import previous data, open Index.html at its old file location in the same browser profile, export JSON, then use College details → Import. Importing replaces the current workspace after confirmation.

**What the ML model learned.** A depth-limited decision tree estimates whether the deterministic solver will exceed 100 backtracks. The training script generated 1,600 distinct simulated configurations, including partial regeneration. It measures each configuration directly, stopping early once its label is known. Inputs include room and teacher utilization, the proportion of lab periods, fixed bookings, and week shape. Search outcomes and backtrack counts are excluded from the inputs. The 1,200 training and 400 held-out configurations use a reproducible stratified split. The deployed solver stops after a bounded search and reports its outcome separately from the forecast.

| Held-out result | Decision tree | Always predict straightforward |
|---|---:|---:|
| Correct predictions | 359 / 400 (89.75%) | 386 / 400 (96.5%) |
| Difficult cases detected | 13 / 14 | 0 / 14 |
| Straightforward cases incorrectly flagged | 40 / 386 | 0 / 386 |

Only 13 of 53 difficulty warnings were correct on this synthetic test set. Treat the warning as an estimate; all selections still go through the solver. Performance on real college schedules is unmeasured.

**Verification and progress.** Assistant-run regression tests verified 120/120 periods, subject counts, teacher/room/division clashes, mandatory lab pairs, preservation of unselected timetables, shortages, timing rejection, stale forms, and legacy subject-name import. A headless browser exercised prediction and generation, then opened a saved third-year timetable after an actual Python server restart and downloaded the 120-row CSV. All verification used temporary databases. Run `python -m unittest -v test_campusflow` to repeat the regression checks. Vinay’s independent operation and viva recall are pending. Next practical step: run the all-division demo and explain the difference between a predicted difficulty and a verified clash count.
