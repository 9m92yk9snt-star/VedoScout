# Pre-shot receiver-side follow-up — 2026-11-07

User clarified that the passer is occluded but the receiver is briefly visible with the ball before shooting. Previous backward seed at 50.648 s was too late for testing the receiving phase. Inspected 36 lossless frames at 50.015–50.598 s.

Manually localized visible ball candidate at 50.431 s, (371,1060), and ran the same exploratory LK checks backward. Four proposals reach 50.365 s; consistency fails at 50.348 s. Unlike the previous experiment, this starts before the outgoing shot. This is progress in locating a receiver-side anchor, not proof of the exact first touch, automatic player identity or a complete pass trajectory. Some early proposals are partially occluded; numerical consistency is not visual confirmation. Forward trajectory still ends at 49.731 s. No bridge is constructed across the gap. No LLM, production change, merge, deploy or arrow approval.

Reproduce run.py from the workspace parent containing source_audit/video and receiver_probe/. Result includes the canonical source hash. Dependencies OpenCV, NumPy, Pillow.
