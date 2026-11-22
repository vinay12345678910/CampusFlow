# CampusFlow Bug Report
Generated: 2026-11-22

## Executive Summary
After thorough analysis including code review, static analysis, and runtime testing, I found **1 confirmed bug** and several areas for improvement. The codebase is generally well-written with good validation, but there's one edge case that could cause performance issues.

## Critical Issues

### Bug #1: Missing Validation in prepare() for Lab Periods
**Severity**: Medium  
**Location**: `scheduler.py:119-146` (prepare function)  
**Status**: Confirmed

**Description**:
The `prepare()` function doesn't validate that lab subjects have an even number of periods. While `check_catalog()` performs this validation, `prepare()` can be called with data that bypasses this check in certain code paths.

**Impact**:
- When a lab subject has an odd number of periods (e.g., 1 or 3), `prepare()` succeeds
- The `solve()` function then attempts to schedule these as consecutive pairs
- This results in wasted computation (up to LIMIT backtracks) trying impossible scenarios
- Eventually fails with "search limit reached" instead of immediate validation error

**Reproduction**:
```python
from scheduler import sample, prepare, solve

c = sample()
c['subjects'] = [dict(
    division='Second Year A',
    name='Odd Lab',
    teacher='Mr. Sharma',
    periods=3,  # Odd number - invalid!
    lab='Computer Lab'
)]

# This succeeds when it should fail early
fixed, tasks, features = prepare(c, {}, ['Second Year A'])

# This wastes computation trying impossible placements
result = solve(c, fixed, tasks, limit=1000)
print(result.status)  # "search limit reached" after 1000+ backtracks
```

**Why it's not exploitable**:
In the actual application flow (`app.py:action()`), `store()` is called after `solve()`, and `store()` calls `check_catalog()` which would catch the invalid data before persisting. However, the bug still wastes computation time during the solve phase.

**Recommended Fix**:
Add validation in `prepare()` to check lab periods:
```python
def prepare(c, saved, selected):
    if not selected or not set(selected) <= set(CLASSES):
        raise ValueError("Select at least one valid division.")
    
    # Add this validation block:
    for s in c["subjects"]:
        if s["lab"] and s["periods"] % 2:
            raise ValueError(f"Lab subject '{s['name']}' needs an even number of periods.")
    
    fixed = {d:r for d,r in saved.items() if d not in selected}
    # ... rest of function
```

## Areas Reviewed (No Bugs Found)

### ✓ Time Parsing and Validation
- Correctly handles 24-hour format (00:00 to 23:59)
- Rejects invalid times like 24:00
- Detects overlapping slots
- Validates ordering and zero-duration slots
- Identifies consecutive periods for lab scheduling

### ✓ Database Concurrency
- Optimistic locking with revision numbers prevents race conditions
- `store()` function properly validates before committing
- Connection handling with `closing()` context manager

### ✓ Duplicate Detection
- Case-insensitive duplicate checking for teachers, rooms, days, slots
- Subject uniqueness checked per (division, name) pair
- Whitespace-only names properly rejected

### ✓ Lab Scheduling Logic
- `pair_starts()` correctly identifies consecutive time slots
- Bitmask operations in `solve()` properly check for consecutive availability
- `audit()` validates that scheduled labs are in valid consecutive pairs
- Handles case with no consecutive slots (rejects lab scheduling)

### ✓ Import/Export (Legacy Function)
- Properly validates imported booking coordinates
- Rejects out-of-bounds day/slot indices
- Correctly maps old aliases (SE-A → Second Year A)
- Handles mismatched prefixes by skipping invalid rows
- Slot format conversion handles edge cases

### ✓ Deletion Logic
- Teacher deletion blocked if used by any subject
- Room deletion blocked if used as a lab
- Room deletion clears affected timetables (intentional behavior)
- Subject deletion uses correct index from template loop

### ✓ Capacity Validation
- Room capacity checks in `prepare()`
- Teacher workload validation
- Division schedule load validation
- Handles 100% capacity scenarios

### ✓ CSRF Protection
- `local_requests()` validates Origin header
- Only allows localhost/127.0.0.1
- Blocks cross-origin POST requests

### ✓ Template/JavaScript
- Loop indices correctly map to array positions
- Day filter functionality works correctly
- Form submission handling is safe

## Testing Results

All existing unit tests pass:
```
test_campusflow.py::Practical::test_conflicts_and_independent_validation PASSED
test_campusflow.py::Practical::test_demo PASSED
test_campusflow.py::Practical::test_import PASSED
test_campusflow.py::Practical::test_planning_estimates_and_saved_room_use PASSED

4 passed in 0.52s
```

## Recommendations

1. **Fix Bug #1** (High Priority): Add validation in `prepare()` for lab periods
2. **Add Test Coverage** (Medium Priority): Add test case for odd lab periods scenario
3. **Documentation** (Low Priority): Document that `check_catalog()` must be called before `solve()` to prevent wasted computation

## Code Quality Notes

**Strengths**:
- Comprehensive validation in `check_catalog()` and `audit()`
- Good separation of concerns (scheduler logic separate from web app)
- Proper error handling and user-friendly messages
- Secure defaults (localhost-only, CSRF protection)
- Optimistic locking for concurrent access

**Minor Observations**:
- The error message for room deletion ("Reassign the subject using this teacher or lab first") is teacher-focused but applies to labs too - could be more generic
- The `prediction()` function uses float pack/unpack for feature comparison which seems unnecessary but is harmless
- CSS file has some duplicate/override styles at the end (lines 192-200) but no functional impact

---

**Overall Assessment**: The codebase is well-architected with strong validation layers. The one bug found is relatively minor and can't corrupt data, but should be fixed to avoid wasted computation.
