"""Start the offline CampusFlow app with python app.py."""
import csv
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from math import ceil
from pathlib import Path
from struct import pack, unpack
from time import perf_counter
from urllib.parse import urlsplit

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from scheduler import ALIASES, CLASSES, FEATURES, SLOTS, audit, check_catalog, prepare, sample, solve

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(DATABASE=os.getenv("CAMPUSFLOW_DB", str(ROOT/"campusflow.sqlite3")), MAX_CONTENT_LENGTH=2_000_000)
MODEL = json.loads((ROOT/"difficulty_model.json").read_text())
RUNTIME = json.loads((ROOT/"runtime_model.json").read_text())



@app.before_request
def local_requests():
    if request.host.split(":")[0] not in {"localhost","127.0.0.1"}:
        abort(403)
    origin = request.headers.get("Origin")
    if request.method == "POST" and origin and urlsplit(origin).netloc != request.host:
        abort(403)


def database():
    db = sqlite3.connect(app.config["DATABASE"], timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, revision INTEGER, catalog TEXT, tables_json TEXT)")
    db.execute("INSERT OR IGNORE INTO workspace VALUES (1,0,?,?)", (json.dumps(sample()),"{}"))
    db.commit()
    return db


def read(db):
    revision, catalog, tables = db.execute("SELECT revision,catalog,tables_json FROM workspace WHERE id=1").fetchone()
    return revision, json.loads(catalog), json.loads(tables)


def store(db, revision, catalog, tables):
    check_catalog(catalog)
    issues = audit(catalog,tables)["issues"]
    if issues:
        raise ValueError(issues[0])
    changed = db.execute("UPDATE workspace SET revision=revision+1,catalog=?,tables_json=? WHERE id=1 AND revision=?",
                         (json.dumps(catalog),json.dumps(tables),revision))
    if not changed.rowcount:
        raise ValueError("Another tab saved changes. Refresh and retry.")
    db.commit()


def model_leaf(tree, features):
    node = 0
    while tree["left"][node] != -1:
        value = unpack("f",pack("f",features[tree["feature"][node]]))[0]
        side = "left" if value <= tree["threshold"][node] else "right"
        node = tree[side][node]
    return node


def prediction(features):
    tree = MODEL["tree"]
    assert tree["features"] == FEATURES
    easy, difficult = tree["leaf_counts"][str(model_leaf(tree, features))]
    return round(100 * difficult / (easy + difficult))


def duration(seconds):
    if seconds < 1:
        return "under a second"
    return f"{seconds:.1f} seconds"


def planning_time(minutes):
    if minutes < 1:
        return "less than a minute"
    hours, remainder = divmod(round(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if remainder:
        parts.append(f"{remainder} minute" + ("s" if remainder != 1 else ""))
    return " ".join(parts)


def workload(tasks, fixed, features):
    divisions = defaultdict(set)
    for task in tasks:
        divisions[task["teacher"]].add(task["division"])
    for division, rows in fixed.items():
        for row in rows:
            divisions[row["teacher"]].add(division)
    shared = {teacher for teacher, groups in divisions.items() if len(groups) > 1}
    shared_periods = sum(t["periods"] for t in tasks if t["teacher"] in shared)
    periods = sum(t["periods"] for t in tasks)
    assert RUNTIME["features"] == FEATURES + ["requested_periods", "subject_assignments"]
    leaf = model_leaf(RUNTIME, features + [periods, len(tasks)])
    seconds = RUNTIME["seconds"][leaf]
    # Planning allowance only: these weights have not been timed with human planners.
    room_utilization = features[FEATURES.index("room_utilization")]
    lab_pairs = sum(t["periods"] // 2 for t in tasks if t["lab"])
    manual_seconds = periods * (30 + 30 * room_utilization) + 20 * shared_periods + 30 * lab_pairs
    manual = manual_seconds / 60
    return dict(shared_periods=shared_periods, shared_percent=round(100 * shared_periods / periods),
                lab_pairs=lab_pairs, seconds_per_period=round(manual_seconds / periods),
                runtime=duration(seconds), manual=planning_time(manual),
                saving=planning_time(max(0, manual - seconds / 60)))


def screen(revision,c,tables,**kwargs):
    division = request.values.get("view",CLASSES[0])
    slots = {r["slot"]:r for r in tables.get(division,[])}
    tab = request.values.get("tab", "welcome" if request.method == "GET" else "schedule")
    selected = kwargs.pop("selected", CLASSES)
    summary = None
    if tab == "schedule":
        if request.method == "GET" and request.args.get("choose"):
            selected = list(dict.fromkeys(request.args.getlist("selected")))
        try:
            fixed, tasks, features = prepare(c, tables, selected)
            periods = sum(s["periods"] for s in tasks)
            held = [r for rows in fixed.values() for r in rows]
            labs = sorted({s["lab"] for s in tasks if s["lab"]})
            week = len(c["days"]) * len(c["slots"])
            needed = max(ceil((periods + len(held)) / week),
                         len(set(labs) | {r["room"] for r in held}))
            summary = dict(score=prediction(features), periods=periods, rooms=needed, labs=labs,
                           teachers=len({s["teacher"] for s in tasks}), held=len(held),
                           **workload(tasks, fixed, features))
        except ValueError as exc:
            kwargs.setdefault("error", str(exc))
    room_counts = Counter(r["room"] for rows in tables.values() for r in rows)
    busy = Counter(r["slot"] for rows in tables.values() for r in rows)
    peak_slot = min(busy, key=lambda slot: (-busy[slot], slot)) if busy else None
    return render_template("campus.html", c=c, tables=tables, division=division, slots=slots,
                           classes=CLASSES, rev=revision, tab=tab, selected=selected, plan=summary,
                           room_counts=room_counts, peak=busy[peak_slot], peak_slot=peak_slot, **kwargs)


@app.get("/")
def home():
    with closing(database()) as db:
        return screen(*read(db))


def legacy(payload, catalog_only=False):
    old = payload["data"]
    slots = old["slots"]
    if slots == SLOTS[:3]+["12:15 - 01:15","02:00 - 03:00","03:00 - 04:00"]:
        slots = SLOTS.copy()
    subjects = [dict(division=ALIASES.get(s["className"],s["className"]),name=s["name"],teacher=s["teacher"],
                     periods=s["periods"],lab=s.get("labRoom","")) for s in old["subjects"]]
    c = dict(subjects=subjects,teachers=[t["name"] for t in old["teachers"]],rooms=old["rooms"],days=old["days"],slots=slots)
    check_catalog(c)
    tables = {}
    if catalog_only:
        return c,tables
    for short, table in payload.get("timetables",{}).items():
        division = ALIASES.get(short,short)
        rows = []
        for key,item in table.items():
            prefix, address = key.split("|")
            if prefix != short:
                continue
            day,period = map(int,address.split("-"))
            if not (0<=day<len(c["days"]) and 0<=period<len(slots)):
                raise ValueError("A saved booking falls outside the imported week.")
            rows.append(dict(slot=day*len(slots)+period,subject=item["subject"],teacher=item["teacher"],room=item["room"]))
        tables[division]=rows
    return c,tables


def edit(c,tables,form):
    op = form["action"]
    if op in ("add_teacher","add_room","delete_teacher","delete_room"):
        field = "teachers" if op.endswith("teacher") else "rooms"
        name = form["name"].strip()
        if op.startswith("add"):
            c[field].append(name)
        else:
            if any(name == s["teacher" if field=="teachers" else "lab"] for s in c["subjects"]):
                raise ValueError("Reassign the subject using this teacher or lab first.")
            c[field].remove(name)
            if field=="rooms":
                for d,rows in list(tables.items()):
                    if any(r["room"]==name for r in rows):
                        del tables[d]
    elif op in ("subject","delete_subject"):
        original = form.get("index","")
        if original:
            index = int(original)
            if not 0 <= index < len(c["subjects"]):
                raise ValueError("Unknown subject.")
            old = c["subjects"].pop(index)
            tables.pop(old["division"],None)
        if op=="subject":
            s = {k:form[k].strip() for k in ("division","name","teacher","lab")}
            s["periods"] = int(form["periods"])
            c["subjects"].insert(int(original) if original else len(c["subjects"]),s)
            tables.pop(s["division"],None)
    elif op == "timing":
        days = [s.strip() for s in form["days"].split(",") if s.strip()]
        slots = [s.strip() for s in form["slots"].splitlines() if s.strip()]
        if days!=c["days"] or slots!=c["slots"]:
            tables.clear()
            c.update(days=days,slots=slots)
    else:
        raise ValueError("Unknown action.")


@app.post("/action")
def action():
    form = request.form
    with closing(database()) as db:
        rev,c,tables = read(db)
        try:
            if int(form["rev"])!=rev:
                raise ValueError("This page is out of date. Review the latest data and retry.")
            op = form["action"]
            selected = list(dict.fromkeys(form.getlist("selected")))
            if op in ("preview","generate"):
                fixed,tasks,_ = prepare(c,tables,selected)
                if op=="preview":
                    return screen(rev,c,tables,selected=selected)
                start = perf_counter()
                result = solve(c,fixed,tasks)
                elapsed = duration(perf_counter() - start)
                outcome = f"Saved {len(selected)} weekly timetable{'s' if len(selected) != 1 else ''} in {elapsed}."
                if result.tables is None:
                    outcome = ("We ran out of time trying arrangements." if result.status == "search limit reached"
                               else "These classes cannot fit in the available slots.")
                    outcome += f" Search took {elapsed}. Review teachers, lab rooms and weekly periods in College details."
                    return screen(rev,c,tables,error=outcome,selected=selected)
                store(db,rev,c,result.tables)
                return screen(rev+1,c,result.tables,message=outcome,report=audit(c,result.tables),selected=selected)
            if op=="validate":
                return screen(rev,c,tables,report=audit(c,tables),message="Saved timetable validation" if tables else "Generate a timetable first.")
            if op=="import":
                if not form.get("replace"):
                    raise ValueError("Confirm replacement before importing.")
                c,tables = legacy(json.load(request.files["file"]),bool(form.get("catalog_only")))
            else:
                edit(c,tables,form)
            store(db,rev,c,tables)
            return redirect(url_for("home",tab="manage",saved=1),code=303)
        except (ValueError,KeyError,TypeError,AttributeError,IndexError) as exc:
            return screen(*read(db),selected=form.getlist("selected"),error=str(exc) or "Check the submitted values."),400


@app.get("/download.csv")
def download():
    with closing(database()) as db:
        _,c,tables = read(db)
    report = audit(c,tables)
    if report["issues"]:
        abort(409,report["issues"][0])
    division = request.args.get("division")
    selected = [division] if division else [d for d in CLASSES if d in tables]
    if not selected or any(d not in tables for d in selected):
        abort(404,"Generate the timetable first.")
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["Class","Day","Time","Subject","Teacher","Classroom"])
    for d in selected:
        for row in sorted(tables[d],key=lambda r:r["slot"]):
            day,p = divmod(row["slot"],len(c["slots"]))
            writer.writerow([d,c["days"][day],c["slots"][p],row["subject"],row["teacher"],row["room"]])
    return Response(out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":'attachment; filename="CampusFlow timetable.csv"'})


if __name__=="__main__":
    app.run(host="127.0.0.1",port=int(os.getenv("CAMPUSFLOW_PORT","5000")))
