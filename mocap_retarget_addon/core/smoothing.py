import math
import re

from mathutils import Quaternion

from .action_utils import get_fcurves


_BONE_PATH = re.compile(r'pose\.bones\["([^"]+)"\]\.([a-z_]+)$')


def _frames(curves):
    frames = set()
    for curve in curves:
        frames.update(round(point.co.x, 6) for point in curve.keyframe_points)
    return sorted(frames)


def _set_value(curve, frame, value):
    for point in curve.keyframe_points:
        if abs(point.co.x - frame) < 0.001:
            point.co.y = value
            return


def _curves_by_path(action):
    result = {}
    for curve in get_fcurves(action):
        match = _BONE_PATH.match(curve.data_path)
        if match:
            result.setdefault((match.group(1), match.group(2)), []).append(curve)
    return result


def _smooth_scalar(curve, strength):
    if len(curve.keyframe_points) < 3:
        return
    points = sorted(curve.keyframe_points, key=lambda p: p.co.x)
    alpha = max(0.03, min(1.0, 1.0 - strength))
    previous = points[0].co.y
    for point in points[1:]:
        previous = previous + (point.co.y - previous) * alpha
        point.co.y = previous


def _smooth_quaternion(curves, strength, outlier_angle):
    if len(curves) < 4:
        return
    curves = sorted(curves, key=lambda c: c.array_index)
    frames = _frames(curves)
    if len(frames) < 2:
        return
    alpha = max(0.03, min(1.0, 1.0 - strength))
    previous = None
    for frame in frames:
        values = [curve.evaluate(frame) for curve in curves[:4]]
        current = Quaternion((values[0], values[1], values[2], values[3]))
        if current.magnitude == 0:
            continue
        current.normalize()
        if previous is None:
            filtered = current
        else:
            if previous.dot(current) < 0:
                current = Quaternion(tuple(-value for value in current))
            if outlier_angle > 0 and previous.rotation_difference(current).angle > math.radians(outlier_angle):
                current = previous.slerp(current, 0.25)
            filtered = previous.slerp(current, alpha)
        previous = filtered
        for index, curve in enumerate(curves[:4]):
            _set_value(curve, frame, filtered[index])


def filter_action(action, strength=0.35, outlier_angle=45.0):
    """Return a copied, filtered action without changing the raw action."""
    if not action:
        raise ValueError("No action to filter")
    filtered = action.copy()
    filtered.name = action.name + "_Cleaned"
    grouped = _curves_by_path(filtered)
    for (_, path), curves in grouped.items():
        if path == "rotation_quaternion":
            _smooth_quaternion(curves, strength, outlier_angle)
        elif path in {"rotation_euler", "location"}:
            for curve in curves:
                _smooth_scalar(curve, strength)
    return filtered
