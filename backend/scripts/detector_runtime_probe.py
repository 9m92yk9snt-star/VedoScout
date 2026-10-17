"""Offline runtime experiment only; never imported by production analysis."""
import logging
import math
import os
from pathlib import Path
import threading

import cv2
import numpy as np

logger = logging.getLogger("elite-scout")


def cpu_threads():
    """Honor container CPU quota rather than the host's visible CPU count."""
    available = max(1, os.cpu_count() or 1)
    try:
        available = min(available, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            available = min(available, max(1, math.floor(int(quota) / int(period))))
    except (OSError, ValueError, ZeroDivisionError):
        pass
    return min(4, available)


class OnnxDetector:
    """Small cv2.Net-compatible adapter; retains the exact input tensor.

    The fallback consumes that same tensor if the optional CPU runtime fails.
    Per-thread inputs avoid mixing callers; the OpenCV fallback is serialized.
    """
    def __init__(self, path):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = cpu_threads()
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or list(inputs[0].shape) != [1, 3, 640, 640]:
            raise ValueError("UNSUPPORTED_DETECTOR_MODEL_SIGNATURE")
        self.input_name = inputs[0].name
        self.path = str(path)
        self.local = threading.local()
        self.lock = threading.Lock()
        self.fallback = None
        self.backend = "onnxruntime_cpu"
        self.threads = options.intra_op_num_threads
        self.rounding_fallbacks = 0

    @staticmethod
    def needs_original_rounding(raw):
        """Avoid a float-runtime change moving a box by one detector pixel.

        This selects the old execution engine, never an event/identity rule.
        Preserve OpenCV around integer-coordinate and confidence boundaries.
        """
        import cv_detect
        rows = np.asarray(raw)[0].T
        if rows.shape[1] < 37:
            return True
        scores = rows[:, 4:]
        relevant = ((scores[:, 0] >= cv_detect.CONF_T*(1-2e-5)) |
                    (scores[:, 32] >= .001*(1-2e-5)))
        selected = rows[relevant]
        if not len(selected):
            return False
        coordinates = np.column_stack((selected[:, 0]-selected[:, 2]/2,
                                       selected[:, 1]-selected[:, 3]/2,
                                       selected[:, 2], selected[:, 3]))
        if np.any(np.abs(coordinates-np.rint(coordinates)) < .001):
            return True
        for cid, thresholds in ((0, (cv_detect.CONF_T,)), (32, (.001, .03, .10))):
            for threshold in thresholds:
                if np.any(np.abs(scores[:, cid]-threshold) <= max(1e-8, threshold*2e-5)):
                    return True
        return False

    def _original_forward(self, tensor, *, sticky=False):
        with self.lock:
            if self.fallback is None:
                self.fallback = cv2.dnn.readNetFromONNX(self.path)
            if sticky:
                self.backend = "opencv_dnn_fallback"
            self.fallback.setInput(tensor)
            return self.fallback.forward()

    def setInput(self, tensor):
        self.local.tensor = tensor

    def forward(self):
        tensor = self.local.tensor
        if self.backend == "onnxruntime_cpu":
            try:
                raw = self.session.run(None, {self.input_name: tensor})[0]
                if self.needs_original_rounding(raw):
                    self.rounding_fallbacks += 1
                    return self._original_forward(tensor)
                return raw
            except Exception:
                # No tensors, source images, or exception text enter logs.
                logger.warning("[detector] CPU runtime failed; using OpenCV with the same model/input")
        return self._original_forward(tensor, sticky=True)


def load_network(path):
    if os.environ.get("SCOUTMEPLAY_DETECTOR_BACKEND", "onnxruntime").lower() != "opencv":
        try:
            return OnnxDetector(path)
        except Exception:
            logger.info("[detector] Optional CPU runtime unavailable; using OpenCV")
    return cv2.dnn.readNetFromONNX(str(path))
