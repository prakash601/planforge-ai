# Flow - end-to-end pipeline

```
Photos -+                      (2-8 stills/room, iPhone 15+, no depth/poses)
Video ---+--> Spatial reconstruction --> Room geometry --> Property stitching
LiDAR ---+    (depth+poses+intrinsics      (walls, ceiling      (adjacency,
              on Pro devices)               height, floor         multi-room +
                                             area, openings)      drift corr.)
                       |
                       v
                  Measurements (wall lengths, areas, heights, ALL with CI)
                       |
                       v
                  Damage analysis (per-surface regions: class + metric extent;
                                   concealed-damage flags + firing rule;
                                   scope line items keyed to surfaces)
                       |
                       v
                  JSON (published schema) + rendered floor plan
                  (per-room + stitched whole-property plan)
```

## Build order (from build plan - LiDAR first, photos hardest last)
Phase 1 LiDAR single-room geometry -> Phase 2 measurements+evaluation -> Phase 3 openings
-> Phase 4 multi-room + drift correction -> Phase 5 damage -> Phase 6 video
-> Phase 7 photos -> Phase 8 confidence calibration -> Phase 9 production interface
-> Phase 10 benchmark + fix loop.

Architecture principle: all capture types normalize into a common spatial
representation (NormalizedSpatialScene); geometry/measurement/rendering operate
on that, not on capture-specific formats.

## First milestone (deliberately small)
Given one LiDAR scan of one room -> accurate 2D floor plan (wall lengths,
floor area, ceiling height). CLI: `python -m planforge run --input data/raw/single_room --output outputs/single_room`
-> result.json, floor_plan.png, room_mesh.ply, measurements.json, debug/.
No damage/AI-assistant/RAG/frontend before this works.
