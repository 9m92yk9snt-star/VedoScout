# Original input for the bounded sequence experiment

The owner explicitly approved publishing this test video and the ten original
user selections on 2026-10-18 so the existing source can be analysed by the
configured model in GitHub Actions. No production deployment is involved.

The 43 binary transport parts are consecutive slices of the original video,
750,000 bytes each except the last part. Concatenation restores the exact
31,896,745 source bytes; no transcoding, cropping or time adjustment occurs.
The workflow verifies the complete source and original anchor checksums before
preparation. The source lasts about 76.76 seconds.

The model input uses only that source and the original human selections.
Historical reports, tracking results and model replies are not included.
Expected action counts and reference times are read only after the model run
by the separate evaluator. They never enter the image requests.
