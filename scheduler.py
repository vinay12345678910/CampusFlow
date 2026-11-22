"""College timetabling with a deterministic, bounded backtracking search."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import re

CLASSES = ["Second Year A", "Second Year B", "Third Year A", "Third Year B"]
ALIASES = dict(zip(["SE-A", "SE-B", "TE-A", "TE-B"], CLASSES))
ROOMS = ["Room 101", "Room 102", "Room 103", "Computer Lab"]
SLOTS = ["09:00 - 10:00", "10:00 - 11:00", "11:15 - 12:15",
         "12:15 - 13:15", "14:00 - 15:00", "15:00 - 16:00"]
FEATURES = ["room_utilization", "peak_teacher_utilization", "lab_period_fraction",
            "fixed_period_fraction", "periods_per_day", "selected_divisions", "lab_pair_capacity"]
LIMIT = 2500


def sample():
    teachers = ["Mr. Sharma", "Mrs. Patil", "Mr. Deshmukh", "Mrs. Joshi", "Mr. Kulkarni", "Mrs. More"]
    names = [["Python Programming", "Data Structures", "Mathematics", "Database Systems", "Computer Networks", "Operating Systems"],
             ["Machine Learning", "Artificial Intelligence", "Statistics", "Data Analytics", "Software Engineering", "Machine Learning Lab"]]
    subjects = []
    for i, division in enumerate(CLASSES):
        for j, name in enumerate(names[i//2]):
            periods = [6, 6, 6, 5, 5, 2][j] if i >= 2 else 5
            subjects.append(dict(division=division, name=name, teacher=teachers[j], periods=periods,
                                 lab="Computer Lab" if i >= 2 and j == 5 else ""))
    return dict(teachers=teachers, rooms=ROOMS.copy(), days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                slots=SLOTS.copy(), subjects=subjects)


def clock_ranges(slots):
    ranges = []
    for slot in slots:
        match = re.fullmatch(r'([01]\d|2[0-3]):([0-5]\d)\s*[-–]\s*([01]\d|2[0-3]):([0-5]\d)', slot)
        if not match:
            raise ValueError("Use 24-hour times, for example 14:00 - 15:00.")
        h, m, h2, m2 = map(int, match.groups())
        start, end = h*60+m, h2*60+m2
        if start >= end or (ranges and start < ranges[-1][1]):
            raise ValueError("Periods must be ordered and cannot overlap.")
        ranges.append((start, end))
    return ranges


def check_catalog(c):
    for field in ("teachers", "rooms", "days", "slots"):
        items = c[field]
        if not isinstance(items,list) or not all(isinstance(x,str) and x.strip() for x in items):
            raise ValueError("Invalid "+field+".")
        if len(set(x.casefold() for x in items)) != len(items):
            raise ValueError("Duplicate entry in "+field+".")
    if not c["rooms"] or not c["days"] or not c["slots"]:
        raise ValueError("Keep at least one room, day and period.")
    if len(c["days"]) > 7 or len(c["slots"]) > 24:
        raise ValueError("Use up to seven working days and 24 daily periods.")
    clock_ranges(c["slots"])
    seen = set()
    for s in c["subjects"]:
        key = (s["division"], s["name"].casefold())
        if key in seen or not s["name"].strip() or key[0] not in CLASSES or s["teacher"] not in c["teachers"]:
            raise ValueError("Check the subject name, division and teacher.")
        if type(s["periods"]) is not int or not 1 <= s["periods"] <= 168:
            raise ValueError("Enter a positive whole weekly period count (up to 168).")
        if s["lab"] and (s["lab"] not in c["rooms"] or s["periods"] % 2):
            raise ValueError("A double lab requires an existing room and an even period count.")
        seen.add(key)


def pair_starts(c):
    ranges = clock_ranges(c["slots"])
    return {d*len(ranges)+p for d in range(len(c["days"])) for p in range(len(ranges)-1)
            if ranges[p][1] == ranges[p+1][0]}


def audit(c, tables):
    """Inspect saved rows independently of the search's occupancy masks."""
    issues = []
    checked = {}
    total = len(c["days"])*len(c["slots"])
    pairs = pair_starts(c)
    bookings = {label: Counter() for label in ("teacher", "room", "division")}
    required = scheduled = 0
    subjects = {(s["division"], s["name"]): s for s in c["subjects"]}
    for division, rows in tables.items():
        if division not in CLASSES or not rows:
            issues.append("Invalid or empty division schedule.")
        counts, labs = Counter(), defaultdict(list)
        for row in rows:
            scheduled += 1
            index, name = row["slot"], row["subject"]
            if type(index) is not int or not 0 <= index < total:
                issues.append("Booking outside the working week.")
                continue
            counts[name] += 1
            s = subjects.get((division,name))
            if not s or row["teacher"] != s["teacher"] or row["room"] not in c["rooms"]:
                issues.append(f"Outdated booking in {division}: {name}.")
            if s and s["lab"]:
                labs[name].append(index)
                if row["room"] != s["lab"]:
                    issues.append(f"{name} requires {s['lab']}.")
            for label, value in (("teacher",row["teacher"]),("room",row["room"]),("division",division)):
                bookings[label][value,index] += 1
        for (div,name), s in subjects.items():
            if div == division:
                required += s["periods"]
                if counts[name] != s["periods"]:
                    issues.append(f"{division}: {name} has {counts[name]} of {s['periods']} periods.")
        for name, indices in labs.items():
            indices.sort()
            if len(indices)%2 or any(i not in pairs or j != i+1 for i,j in zip(indices[::2],indices[1::2])):
                issues.append(f"{division}: {name} needs consecutive lab periods.")
    for label, counts in bookings.items():
        checked[label] = sum(n-1 for n in counts.values())
        if checked[label]:
            issues.append(f"{checked[label]} {label} clashes.")
    return dict(required=required, scheduled=scheduled, clashes=checked, issues=issues)


def prepare(c, saved, selected):
    if not selected or not set(selected) <= set(CLASSES):
        raise ValueError("Select at least one valid division.")
    fixed = {d:r for d,r in saved.items() if d not in selected}
    problems = audit(c,fixed)["issues"]
    if problems:
        raise ValueError(problems[0])
    tasks = [s for s in c["subjects"] if s["division"] in selected]
    # Validate lab subjects have even periods to avoid wasting computation in solve()
    for s in tasks:
        if s["lab"] and s["periods"] % 2:
            raise ValueError(f"Lab subject '{s['name']}' needs an even number of periods.")
    total = len(c["slots"])*len(c["days"])
    rows = [r for group in fixed.values() for r in group]
    demand = len(rows) + sum(s["periods"] for s in tasks)
    capacity = total*len(c["rooms"])
    if demand > capacity:
        raise ValueError(f"Room capacity is {capacity} periods for {demand} required. Short by {demand-capacity} room-periods.")
    for d in selected:
        load = sum(s["periods"] for s in tasks if s["division"] == d)
        if not 0 < load <= total:
            raise ValueError(f"{d} requests {load} periods. Choose between 1 and {total}.")
    teachers = Counter(r["teacher"] for r in rows)
    for s in tasks:
        teachers[s["teacher"]] += s["periods"]
    for teacher, load in teachers.items():
        if load > total:
            raise ValueError(f"{teacher} needs {load} periods but has only {total}.")
    labs = sum(s["periods"] for s in tasks if s["lab"])
    features = [demand/capacity, max(teachers.values())/total, labs/demand, len(rows)/capacity,
                len(c["slots"]), len(selected), len(pair_starts(c))/total]
    return fixed, tasks, features


@dataclass
class Result:
    tables: dict | None
    backtracks: int
    status: str


def solve(c, fixed, tasks, limit=LIMIT):
    width = len(c["slots"])
    total = len(c["days"])*width
    week = (1 << total)-1
    pairs = sum(1 << i for i in pair_starts(c))
    occupied = defaultdict(int)
    tables = {**fixed, **{s["division"]: [] for s in tasks}}
    for d, rows in fixed.items():
        for r in rows:
            for resource in (("d",d),("t",r["teacher"]),("r",r["room"])):
                occupied[resource] |= 1 << r["slot"]
    remaining = [s["periods"] for s in tasks]
    resources = []
    for s in tasks:
        rooms = [s["lab"]] if s["lab"] else c["rooms"]
        resources.append((("d",s["division"]),("t",s["teacher"]),[("r",r) for r in rooms]))
    backtracks = 0

    def search():
        nonlocal backtracks
        best = None
        for k, need in enumerate(remaining):
            if not need:
                continue
            division, teacher, rooms = resources[k]
            free = week & ~(occupied[division] | occupied[teacher])
            options, union = [], 0
            for room in rooms:
                mask = free & ~occupied[room]
                if tasks[k]["lab"]:
                    mask &= (mask >> 1) & pairs
                options.append((room,mask))
                union |= mask
            span = 2 if tasks[k]["lab"] else 1
            if union.bit_count()*span < need:
                return False
            score = sum(m.bit_count() for _,m in options)*span/need
            if best is None or score < best[0]:
                best = score,k,span,options
        if best is None:
            return True
        _, k, span, options = best
        s = tasks[k]
        division, teacher, _ = resources[k]
        # Try slots in fixed order. Ordinary rooms with identical occupancy are interchangeable,
        # except rooms reserved by any lab, which must remain distinct.
        seen = set()
        for room, mask in options:
            signature = (occupied[room], room if room[1] in lab_rooms else None)
            if signature in seen:
                continue
            seen.add(signature)
            while mask:
                bit = mask & -mask
                mask ^= bit
                pos = bit.bit_length()-1
                used = bit if span == 1 else bit | (bit << 1)
                for resource in (division,teacher,room):
                    occupied[resource] |= used
                remaining[k] -= span
                if search():
                    for index in range(pos,pos+span):
                        tables[s["division"]].append(dict(slot=index, subject=s["name"],teacher=s["teacher"],room=room[1]))
                    return True
                remaining[k] += span
                for resource in (division,teacher,room):
                    occupied[resource] ^= used
                backtracks += 1
                if backtracks >= limit:
                    return False
        return False

    lab_rooms = {s["lab"] for s in tasks if s["lab"]}
    success = search()
    if success:
        for d in {s["division"] for s in tasks}:
            tables[d].sort(key=lambda r:r["slot"])
        return Result(tables,backtracks,"completed")
    return Result(None,backtracks,"search limit reached" if backtracks>=limit else "no valid placement")
