# Scoring + constraints

## Weights
- 30% walk-in test (cold run vs laser) - catches systems working only on author data
- 25% fix-loop delta - catches diagnosis instead of repair
- 15% verified benchmark accuracy across all three tiers - catches evaporating claims
- 10% compliance matrix coverage - catches building a different product
- 10% head-to-head vs incumbent (e.g. magicplan/poly.cam) - catches benchmark avoidance
- 5% capture route quality (install time, protocol clarity, non-engineer UX) - catches no path to user hands
- 5% process evidence - catches unauditable single-commit repos

## Constraints
- Handheld consumer capture only
- Any pretrained model/dataset/API with disclosure
- Everything runs without calling your infrastructure
- Weights/large binaries fetched by script or volume
- Real properties contain mirrors, glass, wet-look surfaces, low light - cover them
