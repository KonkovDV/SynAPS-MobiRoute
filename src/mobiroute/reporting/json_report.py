"""JSON / Markdown / CSV report writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from mobiroute.domain.requests import PlanDiff, PlanningResult


def write_json(result: PlanningResult, path: Path) -> None:
    path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_markdown(result: PlanningResult, path: Path, diff: PlanDiff | None = None) -> None:
    lines = [
        f"# MobiRoute result ({result.solution_type})",
        "",
        f"- plan_id: `{result.plan_id}`",
        f"- event_type: `{result.event_type}`",
        f"- status: `{result.status}`",
        f"- verified_feasible: `{result.verified_feasible}`",
        f"- served: {len(result.served_requests)}",
        f"- rejected: {len(result.rejected_requests)}",
        f"- claim_level: `{result.claim_level}`",
        f"- data_provenance: `{result.data_provenance}`",
        f"- synaps_commit: `{result.synaps_commit}`",
        f"- input_hash: `{result.input_hash[:16]}…`",
        "",
        "## Objectives",
    ]
    for k, v in sorted(result.objective_values.items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Rejected (reason codes)")
    for r in result.rejected_requests:
        lines.append(f"- `{r.trip_id}` → `{r.reason_code}` {r.detail}")
    if not result.rejected_requests:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Fairness")
    fm = result.fairness_metrics
    lines.append(f"- medical_on_time_rate: {fm.medical_on_time_rate}")
    lines.append(f"- jain_index: {fm.jain_index}")
    lines.append(f"- max_disparity: {fm.max_disparity}")
    lines.append(f"- wheelchair_on_time_rate: {fm.wheelchair_on_time_rate}")
    lines.append(f"- p95_waiting: {fm.p95_waiting}")
    lines.append(f"- p95_ride_time: {fm.p95_ride_time}")
    lines.append(f"- service_coverage: {fm.service_coverage}")
    lines.append(f"- fair_by_single_metric: {fm.fair_by_single_metric}")
    if diff:
        lines.append("")
        lines.append("## Plan diff / churn")
        lines.append(f"- added: {diff.added_trips}")
        lines.append(f"- removed: {diff.removed_trips}")
        lines.append(f"- moved: {diff.moved_trips}")
        lines.append(f"- frozen unchanged: {diff.unchanged_frozen_trips}")
        lines.append(f"- churn: {diff.plan_churn}")
    lines.append("")
    lines.append("## Explanations")
    for ex in result.explanations[:12]:
        lines.append(
            f"- `{ex.trip_id}` accepted={ex.accepted} vehicle={ex.vehicle_id} "
            f"driver={ex.driver_id} reason=`{ex.reason_code}` — {ex.why_this_route}"
        )
    if not result.explanations:
        lines.append("- (none)")
    lines.append("")
    lines.append("> Synthetic/algorithmic evidence only unless claim_level says otherwise.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv_metrics(result: PlanningResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["status", result.status])
        w.writerow(["verified_feasible", result.verified_feasible])
        w.writerow(["served", len(result.served_requests)])
        w.writerow(["rejected", len(result.rejected_requests)])
        for k, v in sorted(result.objective_values.items()):
            w.writerow([k, v])
