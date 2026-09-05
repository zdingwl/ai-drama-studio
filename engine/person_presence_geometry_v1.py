"""纯标准库坐标白名单；放在 app 包之外，避免 Qwen 子进程加载业务数据库依赖。"""
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


def box_iou(left, right):
    """归一化 xywh 框的交并比；只接受已经过 ``valid_box`` 校验的框。"""
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2 = min(left[0] + left[2], right[0] + right[2])
    y2 = min(left[1] + left[3], right[1] + right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = left[2] * left[3] + right[2] * right[3] - intersection
    return intersection / max(1e-9, union)


def unmatched_detection_indexes(detections, subjects, frame_index, threshold=.35):
    """返回未被当前帧 VLM 人物框一对一覆盖的检测框索引。"""
    valid_detections = [
        (index, item['box']) for index, item in enumerate(detections)
        if isinstance(item, dict) and valid_box(item.get('box'))
    ]
    locations = [
        item['box'] for subject in subjects if isinstance(subject, dict)
        for item in frame_boxes(subject.get('frame_boxes')) if item['frame'] == frame_index
    ]
    pairs = sorted(
        ((box_iou(box, location), detection_index, location_index)
         for detection_index, box in valid_detections
         for location_index, location in enumerate(locations)),
        reverse=True,
    )
    matched_detections, matched_locations = set(), set()
    for score, detection_index, location_index in pairs:
        if (score >= threshold and detection_index not in matched_detections
                and location_index not in matched_locations):
            matched_detections.add(detection_index)
            matched_locations.add(location_index)
    return [index for index, _ in valid_detections if index not in matched_detections]
