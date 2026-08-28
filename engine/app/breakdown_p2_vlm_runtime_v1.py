"""P2.4 Qwen3-VL runtime diagnostics compatibility layer.

The frozen provider contract intentionally fail-closes on unusable VLM semantics. This
wrapper keeps that behaviour while preserving short, non-secret diagnostics emitted by
the isolated runner so local Windows acceptance can distinguish the actual failure.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.breakdown_p2_vlm_v1 import (
    Qwen3VLSemanticProvider as _BaseQwen3VLSemanticProvider,
    VLMRuntimeConfig,
)


class Qwen3VLSemanticProvider(_BaseQwen3VLSemanticProvider):
    """Production Qwen3-VL provider with actionable Shot/subprocess diagnostics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("runner_script") is None:
            repo_root = Path(__file__).resolve().parents[2]
            kwargs["runner_script"] = str(repo_root / "scripts" / "run_breakdown_vlm_qwen3_diagnostic.py")
        self._runtime_failure_details: tuple[str, ...] = ()
        self._subprocess_failure_detail: str | None = None
        super().__init__(*args, **kwargs)

    @staticmethod
    def _clean_failure_detail(record: Mapping[str, Any], *, max_len: int = 900) -> str | None:
        error_type = " ".join(str(record.get("error_type") or "").strip().split())
        detail = " ".join(str(record.get("error_detail") or "").strip().split())
        if not error_type and not detail:
            return None
        if detail and error_type and not detail.startswith(error_type):
            text = f"{error_type}: {detail}"
        else:
            text = detail or error_type
        return text[:max_len]

    @staticmethod
    def _clean_subprocess_output(value: Any, *, max_len: int = 1200) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        lines = [" ".join(line.strip().split()) for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        return " | ".join(lines[-4:])[:max_len]

    def _run_subprocess(
        self,
        config: VLMRuntimeConfig,
        shots: Sequence[p2.P2ShotInput],
    ) -> Sequence[Mapping[str, Any]]:
        try:
            records = tuple(super()._run_subprocess(config, shots))
        except subprocess.CalledProcessError as exc:
            self._subprocess_failure_detail = self._clean_subprocess_output(exc.stdout or exc.output)
            raise

        details: list[str] = []
        for record in records:
            if str(record.get("status") or "READY").strip().upper() == "READY":
                continue
            ordinal = int(record.get("ordinal") or 0)
            detail = self._clean_failure_detail(record)
            if detail:
                prefix = f"Shot {ordinal} " if ordinal > 0 else ""
                details.append(prefix + detail)
        self._runtime_failure_details = tuple(details[:12])
        return records

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        self._runtime_failure_details = ()
        self._subprocess_failure_detail = None
        result = super().analyze(context)

        if result.status != "FAILED":
            return result

        warnings = list(result.warnings)
        metadata = dict(result.metadata)
        changed = False

        if self._runtime_failure_details:
            metadata["shot_failure_details"] = list(self._runtime_failure_details)
            enriched: list[str] = []
            detail_by_ordinal: dict[int, str] = {}
            for item in self._runtime_failure_details:
                if item.startswith("Shot "):
                    parts = item.split(" ", 2)
                    try:
                        ordinal = int(parts[1])
                    except (IndexError, ValueError):
                        continue
                    detail_by_ordinal[ordinal] = parts[2] if len(parts) > 2 else item
            for warning in warnings:
                replacement = warning
                if warning.startswith("Shot ") and warning.endswith(" VLM inference failed"):
                    parts = warning.split(" ", 2)
                    try:
                        ordinal = int(parts[1])
                    except (IndexError, ValueError):
                        ordinal = 0
                    detail = detail_by_ordinal.get(ordinal)
                    if detail:
                        replacement = f"Shot {ordinal} VLM inference failed: {detail}"
                enriched.append(replacement)
            warnings = enriched
            for item in self._runtime_failure_details:
                if not any(item in warning for warning in warnings):
                    warnings.append(item)
            changed = True

        if self._subprocess_failure_detail:
            metadata["subprocess_failure_detail"] = self._subprocess_failure_detail
            warnings.append(f"Qwen3-VL subprocess failed: {self._subprocess_failure_detail}")
            changed = True

        if not changed:
            return result

        return p2.P2ProviderResult(
            component=result.component,
            provider=result.provider,
            model=result.model,
            status=result.status,
            evidence=result.evidence,
            metadata=metadata,
            warnings=tuple(dict.fromkeys(warnings)),
        )
