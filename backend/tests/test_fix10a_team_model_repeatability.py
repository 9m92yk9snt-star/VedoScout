"""Identical visual inputs must not depend on other jobs' random state."""
import json
from pathlib import Path

import cv2
import numpy as np

from cv_detect import TeamModel


def test_live_kit_clustering_is_independent_of_process_rng():
    data = json.loads((Path(__file__).parent / "fixtures/live_kit_chroma.json").read_text())
    baseline = None
    for seed in range(20):
        cv2.setRNGSeed(seed)
        model = TeamModel(data["anchor"])
        model.samples = data["samples"]
        model._fit()
        centers = np.array(sorted(tuple(float(v) for v in c) for c in model.centers))
        if baseline is None:
            baseline = centers
        else:
            np.testing.assert_array_equal(centers, baseline)
