"""CPU inference for the existing pinned models inside owned Match Room workers."""
import os
import cv2


class OnnxCpuNet:
    """Small adapter preserving the existing preprocessing and mask decoder."""
    def __init__(self, path):
        import onnxruntime as ort
        # Disable runtime telemetry before creating any model session. Model
        # inputs, weights, preprocessing and numerical options stay unchanged.
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), sess_options=options,
                                           providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.value = None

    def setInput(self, value):
        self.value = value

    def getUnconnectedOutLayersNames(self):
        return self.output_names

    def forward(self, names):
        return self.session.run(list(names), {self.input_name: self.value})

    def setPreferableBackend(self, backend):
        if backend != cv2.dnn.DNN_BACKEND_OPENCV:
            raise ValueError('Match Room supports CPU inference only')

    def setPreferableTarget(self, target):
        if target != cv2.dnn.DNN_TARGET_CPU:
            raise ValueError('Match Room supports CPU inference only')


def load_cpu_net(path):
    engine = os.environ.get('SCOUTMEPLAY_MATCHROOM_ENGINE', 'opencv')
    if engine == 'onnxruntime':
        return OnnxCpuNet(path)
    if engine == 'opencv':
        return cv2.dnn.readNetFromONNX(str(path))
    raise ValueError('Unsupported Match Room inference engine')
