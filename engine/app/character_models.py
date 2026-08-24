"""F06 本地人物识别模型的下载、校验和路径管理。

职责：
- 固定 YuNet / SFace 的文件名、来源、大小和 SHA-256；
- 把模型保存到应用数据目录 ``models/f06``，不提交 Git；
- 下载时先写 ``.part``，完成大小与 Hash 校验后再原子替换；
- 运行人物识别前只接受已经通过校验的模型文件。

不负责：
- 不执行人脸检测、Embedding、Tracking 或 Clustering；
- 不修改 F04 PyTorch/CUDA 环境；
- 不把网络下载失败伪装成模型推理失败。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import urllib.error
import urllib.request

from engine.app.core.paths import get_app_data_path

MODEL_SOURCE_COMMIT = "47534e27c9851bb1128ccc0102f1145e27f23f98"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120


class CharacterModelError(RuntimeError):
    """F06 模型准备阶段的稳定错误；业务层会转换成 CharacterDetectionError。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CharacterModelSpec:
    """一个不可漂移的 F06 本地模型文件身份。"""

    logical_id: str
    filename: str
    size_bytes: int
    sha256: str
    download_url: str


YUNET_SPEC = CharacterModelSpec(
    logical_id="face_detection.yunet.2023mar",
    filename="face_detection_yunet_2023mar.onnx",
    size_bytes=232_589,
    sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    download_url=(
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
        f"{MODEL_SOURCE_COMMIT}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
)

SFACE_SPEC = CharacterModelSpec(
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


def get_character_model_dir(app_data_path: Path | None = None) -> Path:
    """返回 F06 模型目录；只解析路径，不下载模型。"""

    root = (app_data_path or get_app_data_path()).expanduser().resolve(strict=False)
    return root / "models" / "f06"


def _sha256_file(path: Path) -> str:
    """流式计算模型文件 SHA-256，避免一次把 38MB SFace 全读入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(DOWNLOAD_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_model_file(path: Path, spec: CharacterModelSpec) -> None:
    """强制校验模型大小和 SHA-256；任何一个不符都拒绝使用。"""

    if not path.is_file():
        raise CharacterModelError("CHARACTER_MODEL_MISSING", f"缺少 F06 模型文件：{spec.filename}")
    if path.stat().st_size != spec.size_bytes:
        raise CharacterModelError("CHARACTER_MODEL_INVALID", f"F06 模型大小校验失败：{spec.filename}")
    if _sha256_file(path).lower() != spec.sha256:
        raise CharacterModelError("CHARACTER_MODEL_INVALID", f"F06 模型 SHA-256 校验失败：{spec.filename}")


def require_character_models(app_data_path: Path | None = None) -> dict[str, Path]:
    """返回已经通过完整性校验的 YuNet / SFace 路径。

    该函数绝不自动联网。正式推理如果模型不存在，会明确提示先执行：
    ``python -m engine.app.character_models``。
    """

    model_dir = get_character_model_dir(app_data_path)
    paths: dict[str, Path] = {}
    for spec in MODEL_SPECS:
        path = model_dir / spec.filename
        try:
            _verify_model_file(path, spec)
        except CharacterModelError as exc:
            if exc.code == "CHARACTER_MODEL_MISSING":
                raise CharacterModelError(
                    exc.code,
                    f"{exc.message}。请先执行 python -m engine.app.character_models 下载固定模型",
                ) from exc
            raise
        paths[spec.logical_id] = path
    return paths


def download_character_models(app_data_path: Path | None = None) -> dict[str, Path]:
    """下载并校验 F06 固定模型；已有合法文件直接复用。

    下载过程：
    1. 写入同目录 ``<filename>.part``；
    2. 下载完成校验 size + SHA-256；
    3. ``os.replace`` 原子替换正式文件；
    4. 再做一次正式路径校验。

    中断只会留下可安全删除的 ``.part``，不会把半文件当成可用模型。
    """

    model_dir = get_character_model_dir(app_data_path)
    model_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    for spec in MODEL_SPECS:
        final_path = model_dir / spec.filename
        try:
            _verify_model_file(final_path, spec)
            result[spec.logical_id] = final_path
            continue
        except CharacterModelError:
            pass

        part_path = model_dir / f"{spec.filename}.part"
        part_path.unlink(missing_ok=True)
        request = urllib.request.Request(spec.download_url, headers={"User-Agent": "AI-Drama-Studio/0.6"})
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                with part_path.open("wb") as output:
                    while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                        output.write(chunk)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            part_path.unlink(missing_ok=True)
            raise CharacterModelError("CHARACTER_MODEL_DOWNLOAD_FAILED", f"下载 F06 模型失败：{spec.filename}") from exc

        try:
            _verify_model_file(part_path, spec)
        except CharacterModelError:
            part_path.unlink(missing_ok=True)
            raise

        os.replace(part_path, final_path)
        _verify_model_file(final_path, spec)
        result[spec.logical_id] = final_path

    return result


def main() -> None:
    """命令行模型安装入口：``python -m engine.app.character_models``。"""

    print("正在准备 F06 YuNet / SFace 固定模型…")
    paths = download_character_models()
    for logical_id, path in paths.items():
        print(f"OK  {logical_id}\n    {path}")
    print("F06 模型校验完成。")


if __name__ == "__main__":
    main()
