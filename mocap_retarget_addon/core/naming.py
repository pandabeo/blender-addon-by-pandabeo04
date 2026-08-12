import json
import re

import bpy


MIXAMO_NAMES = {
    "hip": "Hips",
    "spine": "Spine",
    "chest": "Spine1",
    "upperChest": "Spine2",
    "neck": "Neck",
    "head": "Head",
    "leftShoulder": "LeftShoulder",
    "leftUpperArm": "LeftArm",
    "leftLowerArm": "LeftForeArm",
    "leftHand": "LeftHand",
    "rightShoulder": "RightShoulder",
    "rightUpperArm": "RightArm",
    "rightLowerArm": "RightForeArm",
    "rightHand": "RightHand",
    "leftUpLeg": "LeftUpLeg",
    "leftLeg": "LeftLeg",
    "leftFoot": "LeftFoot",
    "leftToe": "LeftToeBase",
    "rightUpLeg": "RightUpLeg",
    "rightLeg": "RightLeg",
    "rightFoot": "RightFoot",
    "rightToe": "RightToeBase",
}

for side, side_cap in (("left", "Left"), ("right", "Right")):
    for finger, finger_cap in (("Thumb", "Thumb"), ("Index", "Index"), ("Middle", "Middle"),
                               ("Ring", "Ring"), ("Little", "Pinky")):
        for part, number in (("Proximal", 1), ("Medial", 2), ("Distal", 3)):
            MIXAMO_NAMES[f"{side}{finger}{part}"] = f"{side_cap}Hand{finger_cap}{number}"


def _key(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"^(mixamorig\d*[:_]?)", "", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


ALIASES = {}


def _add(key, *names):
    for name in names:
        ALIASES[_key(name)] = key


_add("hip", "Hips", "Hip", "Pelvis", "LowerBody", "Hips_Root")
_add("spine", "Spine", "Spine0", "UpperBody", "Upper_Body")
_add("chest", "Chest", "Spine1", "Chest1", "Chest_01")
_add("upperChest", "UpperChest", "Spine2", "Chest2", "Upper_Chest")
_add("neck", "Neck")
_add("head", "Head")

for side, cap in (("left", "Left"), ("right", "Right")):
    _add(f"{side}Shoulder", f"{cap}Shoulder", f"{cap}Collar", f"{cap}Clavicle")
    _add(f"{side}UpperArm", f"{cap}UpperArm", f"{cap}Arm", f"{cap}_Arm")
    _add(f"{side}LowerArm", f"{cap}LowerArm", f"{cap}ForeArm", f"{cap}_ForeArm", f"{cap}Elbow")
    _add(f"{side}Hand", f"{cap}Hand", f"{cap}Wrist")
    _add(f"{side}UpLeg", f"{cap}UpperLeg", f"{cap}UpLeg", f"{cap}Thigh")
    _add(f"{side}Leg", f"{cap}LowerLeg", f"{cap}Leg", f"{cap}Calf", f"{cap}Knee")
    _add(f"{side}Foot", f"{cap}Foot", f"{cap}Ankle")
    _add(f"{side}Toe", f"{cap}ToeBase", f"{cap}Toes", f"{cap}Toe")

    for finger, cap_finger in (("Thumb", "Thumb"), ("Index", "Index"), ("Middle", "Middle"),
                               ("Ring", "Ring"), ("Little", "Pinky")):
        for part, number, alt in (("Proximal", 1, "Proximal"), ("Medial", 2, "Intermediate"),
                                  ("Distal", 3, "Distal")):
            key = f"{side}{finger}{part}"
            _add(key,
                 f"{cap}Hand{cap_finger}{number}",
                 f"{cap}{finger}{number}",
                 f"{cap}{finger}{alt}",
                 f"{cap}{finger}{part}")


def canonical_from_name(name):
    """Return the semantic bone key for a bone name, or None."""
    normalized = _key(name)
    if normalized in ALIASES:
        return ALIASES[normalized]
    for key, expected in MIXAMO_NAMES.items():
        if normalized == _key(expected):
            return key
    return None


def desired_name(key, prefix_mode="NONE"):
    name = MIXAMO_NAMES.get(key, "")
    if prefix_mode == "MIXAMO_PREFIX" and name:
        return "mixamorig:" + name
    return name


def rename_armature(armature, prefix_mode="NONE"):
    if not armature or armature.type != "ARMATURE":
        raise ValueError("Source must be an armature")

    original_mode = armature.mode
    original_active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    plans = []
    used_targets = set(b.name for b in armature.data.edit_bones)
    for bone in armature.data.edit_bones:
        key = canonical_from_name(bone.name)
        target = desired_name(key, prefix_mode) if key else ""
        if target and target != bone.name:
            plans.append((bone, key, target))

    target_counts = {}
    for _, _, target in plans:
        target_counts[target] = target_counts.get(target, 0) + 1

    rename_map = {}
    renamed = 0
    skipped = []
    for bone, key, target in plans:
        if target_counts[target] > 1:
            skipped.append(f"{bone.name} -> {target} (duplicate semantic target)")
            continue
        rename_map[bone.name] = target

    # Two-phase rename prevents Blender's automatic .001 suffixes from corrupting the map.
    temporary = []
    for old_name in list(rename_map):
        bone = armature.data.edit_bones.get(old_name)
        if not bone:
            continue
        temp_name = "__MRA_TMP__" + old_name
        while armature.data.edit_bones.get(temp_name):
            temp_name = "_" + temp_name
        bone.name = temp_name
        temporary.append((temp_name, rename_map[old_name], old_name))

    original_data = {}
    for temp_name, target, old_name in temporary:
        bone = armature.data.edit_bones.get(temp_name)
        if bone:
            bone.name = target
            original_data[target] = old_name
            renamed += 1

    bpy.ops.object.mode_set(mode="OBJECT")
    armature["MRA_ORIGINAL_BONE_NAMES"] = json.dumps(original_data, ensure_ascii=False)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in selected:
        if obj and obj.name in bpy.data.objects:
            obj.select_set(True)
    if original_active and original_active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = original_active
    else:
        bpy.context.view_layer.objects.active = armature
    if original_mode != "OBJECT" and bpy.context.view_layer.objects.active == armature:
        try:
            bpy.ops.object.mode_set(mode=original_mode)
        except RuntimeError:
            pass
    return renamed, skipped
