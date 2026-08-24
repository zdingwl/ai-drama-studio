"""F05 V2 本地视觉模型准备。

当前只管理人物视觉识别需要的 YuNet + SFace 固定模型。
模型不提交 Git，下载后写入 ``data_v2/models/f05``，并强制校验大小和 SHA-256。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import urllib.error
import urllib.request

from engine.app.studio_v2 import data_root

MODEL_SOURCE_COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120


class ContentModelError(RuntimeError):
    """F05 模型准备错误。"""


@dataclass(frozen=True)
class ModelSpec:
    logical_id: str
    filename: str
    size_bytes: int
    sha256: str
    download_url: str


YUNET_SPEC = ModelSpec(
    logical_id="face_detection.yunet.2023mar",
    filename="face_detection_yunet_2023mar.onnx",
    size_bytes=232_589,
    sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    download_url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_SOURCE_COMMIT}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
)

SFACE_SPEC = ModelSpec(
    logical_id="face_recognition.sface.2021dec",
    filename="face_recognition_sface_2021dec.onnx",
    size_bytes=38_696_353,
    sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    download_url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_SOURCE_COMMIT}/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
)

MODEL_SPECS = (YUNET_SPEC, SFACE_SPEC)


def model_dir() -> Path:
    path = data_root() / "models" / "f05"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(DOWNLOAD_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, spec: ModelSpec) -> None:
    if not path.is_file():
        raise ContentModelError(f"缺少模型：{spec.filename}")
    if path.stat().st_size != spec.size_bytes:
        raise ContentModelError(f"模型大小校验失败：{spec.filename}")
    if _sha256(path).lower() != spec.sha256:
        raise ContentModelError(f"模型 SHA-256 校验失败：{spec.filename}")


def model_status() -> dict[str, object]:
    root = model_dir()
    models: list[dict[str, object]] = []
    all_ready = True
    for spec in MODEL_SPECS:
        path = root / spec.filename
        ready = True
        error: str | None = None
        try:
            _verify(path, spec)
        except ContentModelError as exc:
            ready = False
            all_ready = False
            error = str(exc)
        models.append({
            "logical_id": spec.logical_id,
            "filename": spec.filename,
            "ready": ready,
            "path": str(path),
            "error": error,
        })
    return {"ready": all_ready, "models": models}


def require_models() -> dict[str, Path]:
    root = model_dir()
    result: dict[str, Path] = {}
    for spec in MODEL_SPECS:
        path = root / spec.filename
        _verify(path, spec)
        result[spec.logical_id] = path
    return result


def prepare_models() -> dict[str, object]:
    root = model_dir()
    for spec in MODEL_SPECS:
        final_path = root / spec.filename
        try:
            _verify(final_path, spec)
            continue
        except ContentModelError:
            pass

        part_path = root / f"{spec.filename}.part"
        part_path.unlink(missing_ok=True)
        request = urllib.request.Request(spec.download_url, headers={"User-Agent": "AI-Drama-Studio/2.0"})
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                with part_path.open("wb") as output:
                    while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                        output.write(chunk)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            part_path.unlink(missing_ok=True)
            raise ContentModelError(f"下载模型失败：{spec.filename}") from exc

        try:
            _verify(part_path, spec)
        except ContentModelError:
            part_path.unlink(missing_ok=True)
            raise
        os.replace(part_path, final_path)
        _verify(final_path, spec)
    return model_status()


def main() -> None:
    print("正在准备 F05 YuNet / SFace 模型…")
    status = prepare_models()
    for item in status["models"]:  # type: ignore[index]
        print(f"OK  {item['filename']}\n    {item['path']}")
    print("F05 人物视觉模型准备完成。")


if __name__ == "__main__":
    main()
