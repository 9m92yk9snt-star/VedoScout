# Continuous-play arrow scaling correction

The selected product direction is the existing arrow during normal playback. The paused direction export remains an isolated experiment and is not being integrated. This change does not add playback stops, crop, zoom, new ball positions, revised source timing or approval changes.

A raster check of the actual MatchRoomPlayer SVG subtree exposed inconsistent marker/shaft sizing when a referenced non-scaling path and stroke-relative marker are combined. At 360px viewport width the opaque head was only 2px tall versus 10px at 1080px. Use explicit screen-to-SVG conversion for the two shaft widths and markerUnits=userSpaceOnUse. The head still caps at 10 screen pixels or 30% of a short line. The source endpoints, current frame masks, existing gold gradient, core and bounded glow are retained.

Validation: five resvg cases covering mobile portrait, desktop landscape, short line, person mask and diagonal direction pass. Corrected opaque head height is 8px at both long-line sizes; the mask interior has zero alpha including the glow. All six existing Match Room node tests and localization/display-bridge contracts pass. JSX was compiled from the actual component SVG subtree for rasterization. No runtime dependencies added; the optional standalone raster script requires React, React DOM, esbuild and resvg via NODE_PATH.

A Chromium browser run was attempted but the environment denied its process socket; no browser or full React application validation is claimed. Raster verification checks appearance and sizing, not source-ball trajectory accuracy. No merge or deployment.
