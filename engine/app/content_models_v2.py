"""03 资产本地人物视觉模型准备。

统一管理人物 V4 需要的固定 OpenCV Zoo 模型：
- YuNet：Face Detection；
- SFace：Face Identity；
- YOLOX：Person Detection，回答“画面里有几个人”；
- YoutuReID：Body ReID，补侧脸 / 背影 / 遮挡身份连续性。

模型不提交 Git；显式执行 prepare 后写入 ``data_v2/models/f05``，正式分析时只读本地权重，
不会在业务 Run 中静默联网下载。
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
DOWNLOAD_TIMEOUT_SECONDS = 300


class ContentModelError(RuntimeError):
    """模型准备 / 下载 / 校验阶段错误。"""


class RequiredCharacterModelError(RuntimeError):
    """正式人物 V4 Run 缺少必需模型。

    这个异常故意不继承 ContentModelError：旧 content_analysis_v2 会把 ContentModelError
    当成可降级组件错误并继续生成 Run；人物 V4 不允许这样做，否则可能把“模型没准备”
    错误发布成“0 人物”的新 AUTO 资产版本。
    """


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

# OpenCV Zoo LFS metadata at MODEL_SOURCE_COMMIT：
# oid sha256:c5c2...8063 / size 35,858,002 bytes。
YOLOX_SPEC = ModelSpec(
    logical_id="person_detection.yolox.2022nov",
    filename="object_detection_yolox_2022nov.onnx",
    size_bytes=35_858_002,
    sha256="c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
    download_url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_SOURCE_COMMIT}/models/object_detection_yolox/object_detection_yolox_2022nov.onnx"
    ),
)

# OpenCV Zoo LFS metadata at MODEL_SOURCE_COMMIT：
# oid sha256:0579...580d / size 106,878,407 bytes。
YOUTU_REID_SPEC = ModelSpec(
    logical_id="person_reid.youtu.2021nov",
    filename="person_reid_youtu_2021nov.onnx",
    size_bytes=106_878_407,
    sha256="0579683334d4b9440221606dcb461656dd0dc64143b18f48faedaced9b4f580d",
    download_url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_SOURCE_COMMIT}/models/person_reid_youtureid/person_reid_youtu_2021nov.onnx"
    ),
)

MODEL_SPECS = (YUNET_SPEC, SFACE_SPEC, YOLOX_SPEC, YOUTU_REID_SPEC)


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
    """返回全部人物模型准备状态，不主动联网。"""

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
    return {"ready": all_ready, "profile": "character-v4", "models": models}


def require_models() -> dict[str, Path]:
    """正式人物 Run 的硬门槛。

    输入：本机模型目录；输出：四个已校验模型路径。
    为什么：缺任一 V4 模型时必须让本次 Run 失败，保留旧 Current，禁止降级成空人物结果。
    """

    root = model_dir()
    result: dict[str, Path] = {}
    for spec in MODEL_SPECS:
        path = root / spec.filename
        try:
            _verify(path, spec)
        except ContentModelError as exc:
            raise RequiredCharacterModelError(
                f"人物识别 V4 模型未准备完整：{exc}。请先执行人物模型准备，再重新提取资产。"
            ) from exc
        result[spec.logical_id] = path
    return result


def prepare_models() -> dict[str, object]:
    """显式下载并校验全部人物 V4 模型；已有正确文件直接复用。"""

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
        request = urllib.request.Request(spec.download_url, headers={"User-Agent": "AI-Drama-Studio/2.5"})
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
    print("正在准备资产人物 V4 模型（YuNet / SFace / YOLOX / YoutuReID）…")
    status = prepare_models()
    for item in status["models"]:  # type: ignore[index]
        print(f"OK  {item['filename']}\n    {item['path']}")
    print("资产人物 V4 模型准备完成。")


if __name__ == "__main__":
    main()
