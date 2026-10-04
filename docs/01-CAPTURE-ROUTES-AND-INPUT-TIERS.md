# Part 1 - Capture routes and input tiers

## No captures provided
Like incumbent scanning apps, you own the problem from the phone's sensors onward.

## Two legitimate capture routes (choose one)
- Route 1: Own iOS capture app. ARKit, RoomPlan, raw LiDAR depth, camera, IMU, whatever from the SDK. Ship as TestFlight or dev build installable on evaluator device in under 10 minutes.
- Route 2: Stock capture protocol. Name the off-the-shelf capture tool (LiDAR logging app, native camera, anything installable from App Store) and write the one-page protocol a non-engineer follows: what to install, how to walk, how long, what to avoid, how to hand files to the pipeline. At defense they follow the page literally - ambiguity shows up in the capture.

## Three mandatory input tiers, same output contract
Intervals must widen honestly as sensor data thins.

1. Photos: 2-8 stills per room from any iPhone 15 or newer, no depth, no poses. A set of photo folders (one folder per room) must produce the same stitched whole-property plan the other tiers produce, intervals widened accordingly. Floor: any picture in, results out.
2. Video: handheld walkthrough clip from any iPhone 15 or newer.
3. LiDAR: depth, poses and intrinsics on Pro-class devices.

Submit a device matrix stating which tier runs on which hardware and what accuracy each tier honestly delivers.
