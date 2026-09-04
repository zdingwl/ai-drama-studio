"""动作表演专项入口，复用已验收的视频窗口与 exact-Shot 采样。"""
from __future__ import annotations

import run_breakdown_vlm_fast_grounded_qwen3_timed_v5 as production

_base_prompt = production.exact_v3._prompt


def performance_prompt(*args, **kwargs):
    return _base_prompt(*args, **kwargs) + """
本次重点复核当前镜头的动作与表演：activity、expression、posture、gaze、interaction。
不要只用“说话”代替可见的动作、表情细节。描述嘴部、眉眼、头部、手势、身体姿态及其可见变化。
无明显动作变化可以如实写“保持站姿，未见明显动作变化”，但只有画面支持时才能写。
看不清、被遮挡、无法判断必须留空，不得编造心理、动机或邻镜动作。
多人时以可见外观或画面位置区分动作主体，不猜人物姓名，不修改人物身份、台词或说话人。
仍严格遵守原 JSON schema，不要输出解释文字。
"""


production.exact_v3._prompt = performance_prompt

if __name__ == "__main__":
    raise SystemExit(production.timed.main())
