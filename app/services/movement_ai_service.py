import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException, status

from app.ai.biomechanics.engine import compute_metrics
from app.ai.evidence.generator import generate_flagged_frame, generate_pose_overlay
from app.ai.interpretation.llm import get_interpreter
from app.ai.interpretation.prompts import PROMPT_VERSION
from app.ai.interpretation.schemas import InterpretationInput
from app.ai.phases.factory import get_phase_detector
from app.ai.pose.yolo11 import get_pose_estimator
from app.ai.quality.engine import merge_quality_results, validate_pose_quality, validate_video_metadata
from app.ai.risk.engine import assess_risk
from app.ai.tracking.smoothing import smooth_pose
from app.core.config import get_settings
from app.core.enums import QualityStatus
from app.models.movement import MovementScreening
from app.services.cloudinary_service import download_movement_video, upload_movement_artifact


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _video_adapter(screening: MovementScreening) -> SimpleNamespace:
    metadata = screening.video_metadata or {}
    return SimpleNamespace(
        width=metadata.get("width"),
        height=metadata.get("height"),
        fps=metadata.get("fps") or metadata.get("frame_rate") or 30,
        duration_seconds=metadata.get("duration_seconds") or metadata.get("duration"),
        format=metadata.get("format") or "mp4",
        bytes=metadata.get("bytes"),
        cloudinary_secure_url=screening.video_url,
        cloudinary_public_id=screening.video_public_id,
    )


def _mean_pose_confidence(sequence: Any) -> float | None:
    values = [point.confidence for frame in sequence.frames for point in frame.keypoints.values()]
    return sum(values) / len(values) if values else None


async def run_movement_analysis(screening: MovementScreening) -> dict[str, Any]:
    if not screening.video_url:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload a screening video before analysis")

    settings = get_settings()
    work_dir = Path(settings.movement_temp_dir) / str(screening.id)
    work_dir.mkdir(parents=True, exist_ok=True)
    video_path = work_dir / f"original.{(screening.video_metadata or {}).get('format') or 'mp4'}"

    try:
        video = _video_adapter(screening)
        metadata_quality = validate_video_metadata(video)
        if metadata_quality.status == QualityStatus.RETAKE_REQUIRED:
            return {
                "model": "SafeSport Movement AI",
                "status": "RETAKE_REQUIRED",
                "quality": _json(metadata_quality),
                "summary": "Video quality did not meet the movement-screening requirements. A retake is required before AI analysis.",
                "findings": [],
                "limitations": ["No risk signal is produced for inadequate video quality."],
            }

        await download_movement_video(screening.video_url, str(video_path))
        sequence = await asyncio.to_thread(get_pose_estimator().estimate_video, str(video_path))
        pose_quality = validate_pose_quality(sequence)
        quality = merge_quality_results(metadata_quality, pose_quality)
        if quality.status == QualityStatus.RETAKE_REQUIRED:
            return {
                "model": sequence.model_metadata.get("model_name", "YOLO11 Pose"),
                "status": "RETAKE_REQUIRED",
                "quality": _json(quality),
                "pose_model": sequence.model_metadata,
                "summary": "Pose quality did not meet the movement-screening requirements. A retake is required before clinical interpretation.",
                "findings": [],
                "limitations": ["No risk signal is produced for inadequate pose quality."],
            }

        sequence = smooth_pose(sequence)
        phases = get_phase_detector(screening.drill).detect(sequence)
        metrics = compute_metrics(screening.drill, sequence, phases)
        metrics["_phase_detection"] = phases.model_dump(mode="json")
        risk = assess_risk(screening.drill, metrics)

        evidence: list[dict[str, Any]] = []
        overlay_path = await asyncio.to_thread(generate_pose_overlay, str(video_path), sequence, work_dir / "pose-overlay.mp4")
        overlay = await upload_movement_artifact(str(overlay_path), str(screening.id), "overlays", "pose-overlay")
        evidence.append({
            "evidence_type": "POSE_OVERLAY_VIDEO",
            "cloudinary_public_id": overlay.get("public_id"),
            "cloudinary_secure_url": overlay.get("secure_url"),
            "metadata": {"model": sequence.model_metadata},
        })

        for metric_name, metric in metrics.items():
            if metric_name.startswith("_") or not isinstance(metric, dict):
                continue
            metric_evidence = metric.get("evidence") or {}
            frame_number = metric_evidence.get("frame")
            if frame_number is None:
                continue
            frame_path = await asyncio.to_thread(generate_flagged_frame, str(video_path), sequence, int(frame_number), work_dir / f"{metric_name}-{frame_number}.jpg")
            if frame_path is None:
                continue
            uploaded = await upload_movement_artifact(str(frame_path), str(screening.id), "evidence", f"{metric_name}-{frame_number}")
            evidence.append({
                "evidence_type": "FLAGGED_FRAME",
                "timestamp_ms": metric_evidence.get("timestamp_ms"),
                "frame_number": frame_number,
                "cloudinary_public_id": uploaded.get("public_id"),
                "cloudinary_secure_url": uploaded.get("secure_url"),
                "finding_code": metric_name,
                "metadata": {"metric": metric_name, "value": metric.get("value")},
            })

        context = InterpretationInput(
            athlete={"id": screening.athlete_safesport_id, "name": screening.athlete_name, "sport": screening.sport, "team": screening.team},
            screening={"drill": screening.drill, "camera_view": screening.camera_view, "quality": quality.status.value if hasattr(quality.status, "value") else str(quality.status)},
            metrics=metrics,
            risk=_json(risk),
            evidence=evidence,
        )
        interpretation = await get_interpreter().interpret(context)
        observations = interpretation.model_dump(mode="json").get("observations", [])
        findings = [item.get("finding", "") for item in observations if item.get("finding")]
        if not findings:
            findings = [rule.get("metric", "Movement metric") + f" signal: {rule.get('classification', 'observed')}" for rule in risk.get("triggered_rules", [])]

        return {
            "model": sequence.model_metadata.get("model_name", "YOLO11 Pose"),
            "model_family": sequence.model_metadata.get("model_family", "YOLO11"),
            "provider": sequence.model_metadata.get("provider", "ultralytics"),
            "prompt_version": PROMPT_VERSION,
            "status": "AI_COMPLETE",
            "risk_signal": _json(risk.get("risk_signal")),
            "risk_score": risk.get("risk_score"),
            "confidence": risk.get("confidence") or _mean_pose_confidence(sequence),
            "quality": _json(quality),
            "pose_model": sequence.model_metadata,
            "metrics": _json(metrics),
            "risk": _json(risk),
            "interpretation": interpretation.model_dump(mode="json"),
            "summary": interpretation.summary,
            "findings": findings,
            "limitations": interpretation.limitations,
            "evidence": evidence,
            "video": {"url": screening.video_url, "public_id": screening.video_public_id, "metadata": screening.video_metadata or {}},
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
