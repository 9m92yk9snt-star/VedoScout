# Validate recovery source before loading the medium model

Recovery previously verified the 105 MB model asset and constructed an OpenCV network before checking the decoded source. Move those operations after the existing minimum-frame, anchor proximity, frame-spacing and scene-cut gates. Invalid clips now return the same empty recovery result without model verification/loading. An expired deadline raises the existing caught TimeoutError before loading. Valid source uses the same pinned weights, loader, selected seed frames, inference, masks and identity gates.

60 recovery, contour, tracking and inference tests pass. Added checks cover too few frames, unavailable seed frame, timestamp gap, duplicate timestamp, scene cut, expired deadline, and verification-before-load for valid input. No live timing improvement is claimed: this saves model setup only on rejected/expired recovery attempts, not inference on successful clips.

The writer/localizer overlap remains unenabled. Final selection depends on report mentions and naive speculative work can consume the budget needed by other selected clips. This change is independent of that integration.
