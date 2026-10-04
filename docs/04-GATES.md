# Gates

Round-1 gates apply, plus 5 additions where the field collectively failed:

1. Openings: widths within 2 cm on >=85% of openings. Detection itself scored: missed opening and phantom opening each count as a miss.
2. Ceiling height: within 1.5 cm per room; where a room is captured more than once, spread across captures <= 1 cm. Repeatable-but-biased and unrepeatable both fail; report says which.
3. Repeatability: two captures of same room at same tier agree within 1 cm or 0.5% per wall. Same room in, same plan out.
4. Drift accountability: report states what you do about accumulated drift on multi-room capture (loop closure, pose graph, plane-anchored correction, anything), and an ablation shows stitched footprint with it ON and OFF. "Poses used as-is" = automatic fail on this row.
5. Photo-tier whole-property stitch: per-room photo folders produce ONE stitched plan with correct adjacency and no room overlaps; footprint within +/-8% with calibrated intervals. Photo path handling single rooms only fails this row.

Looser photo/video gates: photo wall lengths within +/-8% with calibrated intervals; video +/-3%. But calibration is scored at EVERY tier - confident garbage on thin input caps total score.
