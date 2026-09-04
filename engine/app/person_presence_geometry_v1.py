"""无运行环境依赖的人物帧级坐标白名单，供 Qwen 子进程和业务层共同使用。"""
import math


def valid_box(box):
    return (isinstance(box, list) and len(box) == 4
            and all(type(v) in (int, float) and math.isfinite(v) for v in box)
            and box[0] >= 0 and box[1] >= 0 and box[2] >= .02 and box[3] >= .02
            and box[0] + box[2] <= 1.001 and box[1] + box[3] <= 1.001)


def frame_boxes(raw):
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw[:12]:
        if (isinstance(item, dict) and type(item.get('frame')) is int
                and 1 <= item['frame'] <= 12 and valid_box(item.get('box'))
                and not any(row['frame'] == item['frame'] for row in result)):
            result.append({'frame': item['frame'], 'box': item['box']})
    return result
