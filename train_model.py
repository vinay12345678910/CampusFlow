"""Rebuild the bundled decision tree from deterministic solver measurements."""
import hashlib
import json
import random
from pathlib import Path
from collections import Counter

from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, accuracy_score
from scheduler import sample, CLASSES, FEATURES, solve, prepare

ROOT = Path(__file__).parent


def scenario(rng):
    c = sample()
    n = rng.randint(2,4)
    width = rng.randint(2,6)
    c["days"] = c["days"][:rng.randint(2,4)]
    c["slots"] = c["slots"][:width]
    c["rooms"] = c["rooms"][:n-1]+["Computer Lab"]
    subjects = []
    for d in CLASSES[:n]:
        pool = rng.sample(c["teachers"],rng.randint(2,5))
        total = width*len(c["days"])
        remaining = rng.randint(max(2,total//2),total)
        for j,teacher in enumerate(pool):
            if remaining == 0:
                break
            periods = remaining if j == len(pool)-1 else rng.randint(1,remaining)
            lab = "Computer Lab" if periods%2==0 and rng.random()<0.35 else ""
            subjects.append(dict(division=d,name=f"Subject {j+1}",teacher=teacher,periods=periods,lab=lab))
            remaining -= periods
    c["subjects"] = subjects
    selected = CLASSES[:n]
    fixed = {}
    if rng.random()<0.35:
        f,t,_ = prepare(c,{},selected[:1])
        partial = solve(c,f,t,limit=101)
        if partial.tables:
            fixed = partial.tables
            selected = selected[1:]
    return c,fixed,selected


def main():
    rng = random.Random(719)
    rows = {}
    while len(rows) < 1600:
        try:
            c,saved,selected = scenario(rng)
            fixed,tasks,features = prepare(c,saved,selected)
        except ValueError:
            continue
        fingerprint = hashlib.sha256(json.dumps([c,saved,selected],sort_keys=True).encode()).hexdigest()
        if fingerprint in rows:
            continue
        # Crossing the threshold already determines the label; long runs need no further search.
        result = solve(c,fixed,tasks,limit=101)
        rows[fingerprint] = features,int(result.backtracks>100)
    X,y = zip(*rows.values())
    train,test = train_test_split(range(len(y)),test_size=.25,random_state=19,stratify=y)
    tree = DecisionTreeClassifier(max_depth=5,min_samples_leaf=8,class_weight="balanced",random_state=19)
    tree.fit([X[i] for i in train],[y[i] for i in train])
    actual = [y[i] for i in test]
    pred = tree.predict([X[i] for i in test])
    majority = Counter(y[i] for i in train).most_common(1)[0][0]
    nodes = tree.tree_
    # Portable representation of this fitted sklearn tree; inference only needs Python.
    model = dict(features=FEATURES, left=nodes.children_left.tolist(),right=nodes.children_right.tolist(),
                 feature=nodes.feature.tolist(),threshold=nodes.threshold.tolist(),
                 label=[int(tree.classes_[v[0].argmax()]) for v in nodes.value])
    # Count actual examples in each leaf without the class weights used for training.
    leaf_counts = {}
    for index, leaf in zip(train, tree.apply([X[i] for i in train])):
        counts = leaf_counts.setdefault(str(leaf), [0, 0])
        counts[y[index]] += 1
    model["leaf_counts"] = leaf_counts
    metrics = dict(train=len(train),test=len(test),accuracy=accuracy_score(actual,pred),
                   confusion=confusion_matrix(actual,pred,labels=[0,1]).tolist(),
                   baseline_accuracy=actual.count(majority)/len(actual),baseline_label=majority)
    (ROOT/'difficulty_model.json').write_text(json.dumps(dict(tree=model,evaluation=metrics),indent=2)+'\n')
    print(metrics)


if __name__=="__main__":
    main()
