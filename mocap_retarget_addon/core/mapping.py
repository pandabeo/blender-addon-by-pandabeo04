from .naming import MIXAMO_NAMES, canonical_from_name


BODY_KEYS = [
    "hip", "spine", "chest", "upperChest", "neck", "head",
    "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
    "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
    "leftUpLeg", "leftLeg", "leftFoot", "leftToe",
    "rightUpLeg", "rightLeg", "rightFoot", "rightToe",
]

FINGER_KEYS = [
    f"{side}{finger}{part}"
    for side in ("left", "right")
    for finger in ("Thumb", "Index", "Middle", "Ring", "Little")
    for part in ("Proximal", "Medial", "Distal")
]


def _find_bones(armature):
    return list(armature.pose.bones) if armature else []


def _score(name, key):
    expected = MIXAMO_NAMES.get(key, "")
    if name == expected or name == "mixamorig:" + expected:
        return 100
    if canonical_from_name(name) == key:
        return 50
    return 0


def detect_map(source, target, include_fingers=False):
    keys = BODY_KEYS + (FINGER_KEYS if include_fingers else [])
    result = []
    source_candidates = {}
    target_candidates = {}

    for bone in _find_bones(source):
        key = canonical_from_name(bone.name)
        if key:
            source_candidates.setdefault(key, []).append((_score(bone.name, key), bone.name))
    for bone in _find_bones(target):
        key = canonical_from_name(bone.name)
        if key:
            target_candidates.setdefault(key, []).append((_score(bone.name, key), bone.name))

    for key in keys:
        sources = sorted(source_candidates.get(key, []), reverse=True)
        targets = sorted(target_candidates.get(key, []), reverse=True)
        source_name = sources[0][1] if sources else ""
        target_name = targets[0][1] if targets else ""
        confidence = 1.0 if source_name and target_name else 0.0
        if confidence and (sources[0][0] < 100 or targets[0][0] < 100):
            confidence = 0.75
        result.append((key, source_name, target_name, confidence))
    return result


def mapping_summary(items):
    mapped = sum(1 for item in items if item.source_name and item.target_name and item.enabled)
    missing = sum(1 for item in items if item.enabled and (not item.source_name or not item.target_name))
    targets = [item.target_name for item in items if item.enabled and item.target_name]
    duplicates = len(targets) - len(set(targets))
    return mapped, missing, duplicates
