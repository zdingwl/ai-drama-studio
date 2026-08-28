#!/usr/bin/env python3
"""CLI for complete Breakdown P2 execution, runtime preflight and acceptance reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app import studio_v2
from engine.app.breakdown_p2_acceptance_v1 import (
    build_acceptance_report,
    collect_p2_runtime_preflight,
    compare_acceptance_reports,
    write_acceptance_report,
)
from engine.app.breakdown_p2_asr_v1 import FasterWhisperASRProvider
from engine.app.breakdown_p2_ocr_v1 import RapidOCROCRProvider
from engine.app.breakdown_p2_pipeline_v1 import run_episode_breakdown_p2
from engine.app.breakdown_p2_vlm_v1 import Qwen3VLSemanticProvider


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是 object: {path}")
    return value


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _providers(args: argparse.Namespace) -> tuple[Any, ...]:
    return (
        FasterWhisperASRProvider(
            model_name=args.asr_model,
            device=args.asr_device,
            compute_type=args.asr_compute_type,
        ),
        RapidOCROCRProvider(
            model_type=args.ocr_model_type,
            device=args.ocr_device,
            sample_interval_us=args.ocr_sample_interval_us,
            max_frames_per_shot=args.ocr_max_frames_per_shot,
            text_score=args.ocr_text_score,
        ),
        Qwen3VLSemanticProvider(
            model_name=args.vlm_model,
            model_path=args.vlm_model_path,
            device=args.vlm_device,
            video_fps=args.vlm_fps,
            max_new_tokens=args.vlm_max_new_tokens,
            max_pixels=args.vlm_max_pixels,
        ),
    )


def cmd_preflight(args: argparse.Namespace) -> int:
    report = collect_p2_runtime_preflight()
    _dump(report)
    return 0 if report.get("ready") or not args.strict else 2


def cmd_run(args: argparse.Namespace) -> int:
    studio_v2.init_database()

    def progress(percent: float, stage: str, message: str) -> None:
        if not args.quiet:
            print(f"[{percent:6.2f}%] {stage}: {message}", file=sys.stderr, flush=True)

    run = run_episode_breakdown_p2(
        args.episode_id,
        providers=_providers(args),
        progress=progress,
    )
    output: dict[str, Any] = {
        "run_id": run.id,
        "episode_id": run.episode_id,
        "status": run.status,
        "pipeline_profile": run.pipeline_profile,
    }
    if args.acceptance or args.review_json or args.report_output:
        review = _read_json(args.review_json)
        report = build_acceptance_report(
            run.id,
            human_review=review,
            include_preflight=not args.no_report_preflight,
        )
        report_path = write_acceptance_report(report, output_path=args.report_output)
        output["acceptance_status"] = report["assessment"]["status"]
        output["acceptance_report"] = str(report_path)
    _dump(output)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    studio_v2.init_database()
    review = _read_json(args.review_json)
    report = build_acceptance_report(
        args.run_id,
        human_review=review,
        include_preflight=not args.no_preflight,
    )
    path = write_acceptance_report(report, output_path=args.output)
    _dump({"report_path": str(path), "assessment": report["assessment"]})
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    reports = [_read_json(path) for path in args.reports]
    ranked = compare_acceptance_reports([item for item in reports if item is not None])
    _dump(ranked)
    return 0


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--asr-model")
    parser.add_argument("--asr-device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--asr-compute-type")
    parser.add_argument("--ocr-model-type", choices=("small", "medium"))
    parser.add_argument("--ocr-device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--ocr-sample-interval-us", type=int)
    parser.add_argument("--ocr-max-frames-per-shot", type=int)
    parser.add_argument("--ocr-text-score", type=float)
    parser.add_argument("--vlm-model")
    parser.add_argument("--vlm-model-path")
    parser.add_argument("--vlm-device", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--vlm-fps", type=float)
    parser.add_argument("--vlm-max-new-tokens", type=int)
    parser.add_argument("--vlm-max-pixels", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Drama Studio Breakdown P2 local runner")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="check local runtime/model readiness without inference")
    preflight.add_argument("--strict", action="store_true", help="return exit code 2 when readiness checks fail")
    preflight.set_defaults(func=cmd_preflight)

    run = sub.add_parser("run", help="run complete ASR -> OCR -> VLM -> Fusion for one Episode")
    run.add_argument("--episode-id", required=True)
    run.add_argument("--quiet", action="store_true")
    run.add_argument("--acceptance", action="store_true", help="write an acceptance report after publish")
    run.add_argument("--review-json", help="optional human review JSON")
    run.add_argument("--report-output", help="optional acceptance report output path")
    run.add_argument("--no-report-preflight", action="store_true")
    _add_provider_args(run)
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="build/rebuild acceptance report from an existing Breakdown Run")
    report.add_argument("--run-id", required=True)
    report.add_argument("--review-json")
    report.add_argument("--output")
    report.add_argument("--no-preflight", action="store_true")
    report.set_defaults(func=cmd_report)

    compare = sub.add_parser("compare", help="rank existing acceptance JSON reports without rerunning models")
    compare.add_argument("reports", nargs="+")
    compare.set_defaults(func=cmd_compare)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
