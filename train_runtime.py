"""Fit an offline estimate of solver duration on this machine (requires scikit-learn)."""
import json
import random
from math import exp, log
from pathlib import Path
from statistics import median
from time import perf_counter

from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor

from scheduler import CLASSES, FEATURES, prepare, sample, solve
from train_model import scenario


def main():
    rng = random.Random(312)
    examples = {}
    while len(examples) < 480:
        try:
            if rng.random() < .5:
                catalog, saved, selected = scenario(rng)
            else:
                catalog, saved = sample(), {}
                for subject in catalog["subjects"]:
                    subject["periods"] = 2 if subject["lab"] else rng.randint(1, 6)
                selected = rng.sample(CLASSES, rng.randint(1, len(CLASSES)))
            fixed, tasks, features = prepare(catalog, saved, selected)
        except ValueError:
            continue
        x = tuple(features + [sum(t["periods"] for t in tasks), len(tasks)])
        if x in examples:
            continue
        start = perf_counter()
        solve(catalog, fixed, tasks)
        examples[x] = log(max(perf_counter() - start, 1e-9))

    train, test = train_test_split(list(examples), test_size=.2, random_state=42)
    model = DecisionTreeRegressor(max_depth=6, min_samples_leaf=5, random_state=42)
    model.fit(train, [examples[x] for x in train])
    tree = model.tree_
    errors = [abs(exp(pred) - exp(examples[x])) for pred, x in zip(model.predict(test), test)]
    data = dict(features=FEATURES + ["requested_periods", "subject_assignments"],
                left=tree.children_left.tolist(), right=tree.children_right.tolist(),
                feature=tree.feature.tolist(), threshold=tree.threshold.tolist(),
                seconds=[exp(v[0][0]) for v in tree.value], train=len(train), test=len(test),
                median_absolute_error_seconds=median(errors))
    Path(__file__).with_name("runtime_model.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"{len(train)} training cases, {len(test)} held out; median absolute error {median(errors):.6f} s")


if __name__ == "__main__":
    main()
