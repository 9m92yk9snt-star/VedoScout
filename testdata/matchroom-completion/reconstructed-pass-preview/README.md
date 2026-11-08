# Reconstructed pass-arrow video preview — 2026-11-07

User requested a visual arrow that starts with the pass while the passer is occluded, is hidden behind blue players, and ends before the receiver shoots. This preview is an illustration, not a newly verified trajectory. User has not yet explicitly approved its playback.

Render uses a manually estimated start at source 50.015 s (448,1082) and a receiver-side flow candidate at 50.381 s (381.36,1065.05). Background affine transforms align the coordinates as the camera moves. Interpolation from 49.900 to 50.381 s is a visual reconstruction, not measured ball motion or a verified release time. Overlay ends 50.398 s. These values must not enter automatic evidence or approval fields.

Solid pale-gold shaft and triangular head follow the existing Match Room palette. Conservative HSV grass visibility, eroded by 5 pixels, hides overlay outside grass. This is not a person-segmentation mask and has not been validated across other clips; do not deploy it as a general occlusion solution. 30 overlay frames, 21 with visible pixels. Visual inspection of frame 58 shows the shaft between players and the head mostly hidden. Previous rejected playback remains rejected in production data.

Run render.py from the parent directory of VedoScout/ with the canonical source at source_audit/video/ and an existing arrow_preview/ directory. Produces raw.mp4, render.json. OpenCV, NumPy and existing motion_compensation code required. No LLM or external inference. A separate review export shows normal speed, half speed, and a 2-second freeze of frame 58. No merge/deploy.
