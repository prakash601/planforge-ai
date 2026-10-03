"""One-to-one matching; misses and phantoms never disappear from width scores."""

import numpy as np
from scipy.optimize import linear_sum_assignment


def score_openings(candidates, annotations, width_tolerance):
    """Compare annotated plane-local rectangles in pose units, not centimeters."""
    if not np.isfinite(width_tolerance) or width_tolerance < 0:
        raise ValueError("finite nonnegative pose-unit width tolerance required")
    for item in [*candidates, *annotations]:
        for field in ("interval", "height_interval"):
            value = np.asarray(item[field], float)
            if (
                value.shape != (2,)
                or not np.isfinite(value).all()
                or value[1] <= value[0]
            ):
                raise ValueError("finite ordered opening annotation intervals required")
    costs = np.full((len(annotations), len(candidates)), 1e6)
    for i, truth in enumerate(annotations):
        for j, candidate in enumerate(candidates):
            if truth["surface_id"] != candidate["surface_id"]:
                continue
            intersection = np.prod(
                [
                    max(
                        0,
                        min(truth[field][1], candidate[field][1])
                        - max(truth[field][0], candidate[field][0]),
                    )
                    for field in ("interval", "height_interval")
                ]
            )
            area_a = np.prod(
                [
                    truth[field][1] - truth[field][0]
                    for field in ("interval", "height_interval")
                ]
            )
            area_b = np.prod(
                [
                    candidate[field][1] - candidate[field][0]
                    for field in ("interval", "height_interval")
                ]
            )
            iou = intersection / (area_a + area_b - intersection)
            if iou >= 0.3:
                costs[i, j] = 1 - iou
    rows, columns = linear_sum_assignment(costs)
    matches, matched_a, matched_b = [], set(), set()
    for i, j in zip(rows, columns):
        if costs[i, j] >= 1e6:
            continue
        truth, candidate = annotations[i], candidates[j]
        error = abs(
            (truth["interval"][1] - truth["interval"][0])
            - (candidate["interval"][1] - candidate["interval"][0])
        )
        passed = error <= width_tolerance and truth["kind"] == candidate["kind"]
        matches.append(
            {
                "annotation_index": int(i),
                "candidate_index": int(j),
                "absolute_width_error_pose_units": float(error),
                "class_matches": truth["kind"] == candidate["kind"],
                "passes": bool(passed),
            }
        )
        matched_a.add(i)
        matched_b.add(j)
    misses, phantoms = (
        len(annotations) - len(matched_a),
        len(candidates) - len(matched_b),
    )
    denominator = len(annotations) + phantoms
    return {
        "annotations": len(annotations),
        "candidates": len(candidates),
        "matched": len(matches),
        "misses": misses,
        "phantoms": phantoms,
        "width_tolerance_pose_units": float(width_tolerance),
        "matching_iou_threshold": 0.3,
        "pass_fraction_including_misses_and_phantoms": sum(
            item["passes"] for item in matches
        )
        / denominator
        if denominator
        else None,
        "matches": matches,
        "unmatched_annotations": sorted(set(range(len(annotations))) - matched_a),
        "unmatched_candidates": sorted(set(range(len(candidates))) - matched_b),
        "physical_accuracy_status": "unverified",
    }
