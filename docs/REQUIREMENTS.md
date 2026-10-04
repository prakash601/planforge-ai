# PlanForge AI - Requirements (from Case Study PDF)

Source: `source/Applied-AI-Case-Study.pdf` (Applied AI Engineer Case Study, Aug 2026, 6 pages).
Extracted text: `source/casestudy-extracted.txt`.
Project name: **PlanForge AI - Multi-Modal Spatial Reconstruction & Property Assessment**.

This index is the entry point. Each file below is a faithful distillation of the PDF.
Three local LiDAR captures are available; see `DATASET_ANALYSIS.md` for inspection evidence.

Build order and progress: [ROADMAP.md](ROADMAP.md). Architecture: [12-DESIGN.md](12-DESIGN.md).
Calibration findings: [CALIBRATION_ANALYSIS.md](CALIBRATION_ANALYSIS.md).
Reconstruction evidence: [RECONSTRUCTION_ANALYSIS.md](RECONSTRUCTION_ANALYSIS.md).
Candidate geometry: [GEOMETRY_ANALYSIS.md](GEOMETRY_ANALYSIS.md).
Measurements and provisional uncertainty: [MEASUREMENT_ANALYSIS.md](MEASUREMENT_ANALYSIS.md).
Rendered plans and combined LiDAR command: [PLAN_PIPELINE_ANALYSIS.md](PLAN_PIPELINE_ANALYSIS.md).
Candidate openings and annotation scoring: [OPENING_ANALYSIS.md](OPENING_ANALYSIS.md).

- `01-CAPTURE-ROUTES-AND-INPUT-TIERS.md` - Part 1: no captures provided, 2 capture routes, 3 mandatory input tiers, device matrix.
- `02-OUTPUT-CONTRACT.md` - Part 2: full per-capture output contract, stitched plan as product surface.
- `03-BENCHMARK-SET.md` - Self-built benchmark composition (cannot be flattered).
- `04-GATES.md` - Round-1 gates + 5 additions (openings, ceiling, repeatability, drift, photo stitch, looser photo/video gates + calibration).
- `05-HEAD-TO-HEAD.md` - Part 3: vs one consumer scanning app on 2 rooms, >=70% shared dimensions.
- `06-FIX-LOOP.md` - Part 4: fix loop, 25% of score, before/after regenerable + readable diff.
- `07-PROCESS-EVIDENCE.md` - Part 5: commit as you work, AI tools allowed, live defense with tools closed.
- `08-DELIVERABLES.md` - 8 deliverables (compliance matrix, capture route, repo+README, reproduction bundle, benchmark report, fix-loop bundle, technical report max 6pp, raw data).
- `09-WALKIN-TEST.md` - Walk-in test: unseen space, own iPhone 15+, laser-measured, cold run.
- `10-SCORING-AND-CONSTRAINTS.md` - Scoring weights (30/25/15/10/10/5/5) + constraints (handheld consumer capture, disclosure, offline, weights by script/volume, mirrors/glass/low-light).
- `11-FLOW-PIPELINE.md` - End-to-end flow: Photos/Video/LiDAR -> reconstruction -> geometry -> stitching -> measurements -> damage -> JSON + rendered plan; phased build order (LiDAR first, photos hardest last).

Status: docs are published in-repo (since 2026-10-04). `data/` and `outputs/` remain gitignored.
Sample data: three captures under gitignored `data/`; room identities and ground truth remain unconfirmed.
