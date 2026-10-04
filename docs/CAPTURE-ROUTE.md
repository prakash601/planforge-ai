# Capture Route and Device Matrix

Deliverable #2. Chooses a capture route and specifies which tier runs on which
hardware with an honest accuracy statement per tier.

> **Status: Route 2 chosen as the target. Only the LiDAR tier is implemented.**
> The photo and video paths below are the intended protocol, not working code
> today. Accuracy figures are targets, not measured results: the supplied
> captures have no ground truth. See [COMPLIANCE.md](COMPLIANCE.md).

## Route decision

**Route 2 - stock capture protocol.** A dedicated iOS app (Route 1) would take
days of ARKit work that this submission does not have. Route 2 gets an evaluator
from phone to files without any build install, which is also the better product
story: a non-engineer can follow one page.

### Tool

| Tier | Tool | Notes |
| --- | --- | --- |
| LiDAR | A LiDAR logging app that exports depth, confidence, per-frame poses, intrinsics, IMU and RGB video in the layout below | The three supplied captures use this layout; it is the one format the pipeline ingests today |
| Video | Built-in iPhone Camera app | Single handheld walkthrough clip |
| Photos | Built-in iPhone Camera app | 2-8 stills per room, one folder per room |

The exact app name/version must be filled in before submission once the LiDAR
export tool is confirmed against the sample files. The protocol below is written
so the LiDAR walk matches the format the pipeline expects.

## One-page protocol (non-engineer)

### Before you walk

1. Close other apps. Start at ~90% battery; LiDAR capture drains fast.
2. Turn on the lights. Open curtains. Avoid mirrors, glass and wet floors where
   you can; if present, walk past them slowly and do not dwell.
3. Hold the phone at chest height, screen toward you, steady. Move your whole
   body, not just your wrist.

### LiDAR tier

1. Open the LiDAR logging app and start a new capture.
2. Stand in a corner. Sweep slowly left to right across the wall, then step and
   sweep again. Keep moving; do not stop and stare.
3. Walk the room perimeter once, then cross the middle once. About 30-60 seconds
   per room. Longer is better than faster.
4. For multiple rooms, walk through the doorway into the next room without
   stopping the capture. Keep each room's surfaces in view for a few seconds.
5. Stop the capture. Export depth, confidence, odometry, IMU, camera matrix and
   the RGB video into one folder named after the room or property.
6. Hand the whole folder to the pipeline unchanged.

### Video tier

1. Open the Camera app, switch to Video, 1080p or higher.
2. Same walk as the LiDAR tier: perimeter once, across the middle once, 30-60
   seconds per room, one continuous clip for the property.
3. Transfer the `.mov`/`.mp4` file unchanged.

### Photo tier

1. One folder per room. Name it after the room.
2. 2-8 stills per room. Stand near a corner and take overlapping photos around
   the room, each including part of the previous one. Include one shot of each
   wall and the ceiling.
3. Do not zoom. Do not use portrait mode.
4. Hand over the folders unchanged.

### What to avoid

- Fast spinning, stopping mid-sweep, or holding still for long stretches.
- Covering the camera or depth sensor with a finger.
- Dark rooms, direct mirror shots, shooting straight through glass.
- Editing, cropping or re-encoding any file after capture.

## Device matrix

| Tier | Hardware | Capture | Implemented today | Honest accuracy today |
| --- | --- | --- | --- | --- |
| LiDAR | iPhone Pro (LiDAR) | depth + poses + intrinsics + IMU + RGB | Yes | Unverified. Candidate geometry only; no metric accuracy claim |
| Video | iPhone 15 or newer | single handheld clip | No (not started) | Target +/-3% wall lengths, calibrated. Not measured |
| Photos | iPhone 15 or newer | 2-8 stills per room, per-room folders | No (not started) | Target +/-8% wall lengths, calibrated. Not measured |

## What this unlocks and what it does not

Writing this page satisfies the *capture route quality* deliverable (5%) and is
the precondition the walk-in test names. It does **not** make the walk-in test
pass: that needs all three tiers runnable cold, and only LiDAR exists. It also
does not create the benchmark set or any measured accuracy.
