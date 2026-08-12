import copy
import math

import bpy
from mathutils import Matrix, Vector

from .action_utils import get_fcurves, ensure_fcurve


RETARGET_ID = "_MRA_RETARGET"


def _set_active(obj):
    obj.select_set(True)
    obj.hide_set(False)
    bpy.context.view_layer.objects.active = obj


def _mat3_to_vec_roll(mat):
    """Port of Rokoko's utils.mat3_to_vec_roll."""
    target = Vector((0, 0.1, 0))
    normal = mat.col[1].normalized()
    axis = target.cross(normal)
    if axis.dot(axis) > 0.0000000001:
        axis.normalize()
        theta = target.angle(normal)
        base = Matrix.Rotation(theta, 3, axis)
    else:
        updown = 1 if target.dot(normal) > 0 else -1
        base = Matrix.Scale(updown, 3)
        base[2][2] = 1.0
    roll_matrix = base.inverted() @ mat
    return math.atan2(roll_matrix[0][2], roll_matrix[2][2])


def _valid_retarget_items(scene, source, target):
    result = []
    seen = {}
    for item in scene.mra_mapping:
        if not item.enabled or not item.source_name or not item.target_name:
            continue
        if not source.pose.bones.get(item.source_name) or not target.pose.bones.get(item.target_name):
            continue
        seen[item.target_name] = seen.get(item.target_name, 0) + 1
        result.append(item)
    duplicates = [name for name, count in seen.items() if count > 1]
    if duplicates:
        raise ValueError("Duplicate target bone entries: " + ", ".join(duplicates))
    return result


def _find_root_bones(target, retarget_items):
    # Exact traversal used by Rokoko's find_root_bones.
    root_bones = [bone for bone in target.pose.bones if not bone.parent]
    target_names = [item.target_name for item in retarget_items]
    root_bones_animated = []
    while root_bones:
        for bone in copy.copy(root_bones):
            root_bones.remove(bone)
            if bone.name in target_names:
                root_bones_animated.append(bone.name)
            else:
                root_bones.extend(bone.children)
    return root_bones_animated


def _reset_pose_rotations(armature):
    # Exact behavior of Rokoko's get_and_reset_pose_rotations.
    _set_active(armature)
    bpy.ops.object.mode_set(mode="POSE")
    pose_rotations = {}
    for bone in armature.pose.bones:
        if bone.rotation_mode == "QUATERNION":
            pose_rotations[bone.name] = copy.deepcopy(bone.rotation_quaternion)
            bone.rotation_quaternion = (1, 0, 0, 0)
        else:
            pose_rotations[bone.name] = copy.deepcopy(bone.rotation_euler)
            bone.rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode="OBJECT")
    return pose_rotations


def _remove_object_transform_curves(armature):
    action = armature.animation_data.action if armature.animation_data else None
    if not action:
        return
    curves = [curve for curve in get_fcurves(action)
              if curve.data_path in {"location", "rotation_euler", "rotation_quaternion", "scale"}]
    if hasattr(action, "fcurves"):
        for curve in curves:
            action.fcurves.remove(curve)
        return
    from bpy_extras import anim_utils
    for slot in action.slots:
        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        if not channelbag:
            continue
        for curve in curves:
            try:
                channelbag.fcurves.remove(curve)
            except RuntimeError:
                pass


def _scale_source_like_rokoko(source, target, retarget_items, root_bones):
    source_min = None
    source_min_root = None
    target_min = None
    target_min_root = None

    for item in retarget_items:
        bone_source = source.pose.bones.get(item.source_name)
        bone_target = target.pose.bones.get(item.target_name)
        if not bone_source or not bone_target:
            continue
        bone_source_z = (source.matrix_world @ bone_source.head)[2]
        bone_target_z = (target.matrix_world @ bone_target.head)[2]

        if bone_target.name in root_bones:
            if source_min_root is None or source_min_root > bone_source_z:
                source_min_root = bone_source_z
            if target_min_root is None or target_min_root > bone_target_z:
                target_min_root = bone_target_z

        if source_min is None or source_min > bone_source_z:
            source_min = bone_source_z
        if target_min is None or target_min > bone_target_z:
            target_min = bone_target_z

    source_height = source_min_root - source_min if source_min_root is not None and source_min is not None else 0
    target_height = target_min_root - target_min if target_min_root is not None and target_min is not None else 0
    if not source_height or not target_height:
        return
    source.scale *= target_height / source_height


def _copy_rest_pose_like_rokoko(context, source):
    context.scene.tool_settings.use_keyframe_insert_auto = False
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    _set_active(source)
    bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.duplicate_move(
        OBJECT_OT_duplicate={"linked": False, "mode": "TRANSLATION"},
        TRANSFORM_OT_translate={
            "value": (0, 0, 0),
            "constraint_axis": (False, True, False),
            "mirror": False,
            "snap": False,
            "remove_on_cancel": False,
            "release_confirm": False,
        },
    )
    source_copy = context.object
    source_copy.name = source.name + "_MRA_COPY"

    bpy.ops.object.select_all(action="DESELECT")
    _set_active(source_copy)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="POSE")

    action_tmp = source_copy.animation_data.action
    source_copy.animation_data.action = None
    bpy.ops.pose.armature_apply()
    source_copy.animation_data.action = action_tmp

    for bone in source_copy.pose.bones:
        constraint = bone.constraints.new("COPY_TRANSFORMS")
        constraint.name = bone.name
        constraint.target = source
        constraint.subtarget = bone.name

    bpy.ops.object.mode_set(mode="OBJECT")
    return source_copy


def _read_anim_start_end(armature):
    frame_start = None
    frame_end = None
    for curve in get_fcurves(armature.animation_data.action):
        for key in curve.keyframe_points:
            keyframe = key.co.x
            if frame_start is None:
                frame_start = keyframe
            if frame_end is None:
                frame_end = keyframe
            if keyframe < frame_start:
                frame_start = keyframe
            if keyframe > frame_end:
                frame_end = keyframe
    return frame_start, frame_end


def _create_final_action(target, actions_all, root_bones):
    if not actions_all:
        return None

    key_counts = {}
    for action in actions_all:
        for curve in get_fcurves(action):
            if curve.data_path.endswith("scale"):
                continue
            if curve.data_path.endswith("location"):
                bone_name = curve.data_path.split('"')
                if len(bone_name) != 3 or bone_name[1] not in root_bones:
                    continue
            key = curve.data_path + str(curve.array_index)
            key_counts[key] = key_counts.get(key, 0) + len(curve.keyframe_points)

    action_final = bpy.data.actions.new(name="MRA_RETARGETING_FINAL")
    action_final.use_fake_user = True
    target.animation_data_create().action = action_final

    for curve in get_fcurves(actions_all[0]):
        if curve.data_path.endswith("scale"):
            continue
        if curve.data_path.endswith("location"):
            bone_name = curve.data_path.split('"')
            if len(bone_name) != 3 or bone_name[1] not in root_bones:
                continue
        key = curve.data_path + str(curve.array_index)
        if key not in key_counts:
            continue

        group_name = curve.group.name if curve.group else ""
        final_curve = ensure_fcurve(action_final, curve.data_path, curve.array_index, group_name=group_name)
        final_curve.keyframe_points.add(key_counts[key])
        index = 0
        for action in actions_all:
            matches = [candidate for candidate in get_fcurves(action)
                       if candidate.data_path == curve.data_path and candidate.array_index == curve.array_index]
            if not matches:
                continue
            for point in matches[0].keyframe_points:
                final_curve.keyframe_points[index].co.x = point.co.x
                final_curve.keyframe_points[index].co.y = point.co.y
                final_curve.keyframe_points[index].interpolation = "LINEAR"
                index += 1

    for curve in get_fcurves(action_final):
        if len(curve.keyframe_points) <= 2:
            continue
        previous_previous = curve.keyframe_points[0]
        previous = curve.keyframe_points[1]
        to_delete = []
        for point in curve.keyframe_points[2:]:
            if round(previous_previous.co.y, 5) == round(previous.co.y, 5) == round(point.co.y, 5):
                to_delete.append(previous)
            previous_previous = previous
            previous = point
        for point in reversed(to_delete):
            curve.keyframe_points.remove(point)

    for action in actions_all:
        if action.users == 0:
            bpy.data.actions.remove(action)
    if hasattr(target.animation_data, "action_slot"):
        try:
            target.animation_data.action_slot = target.animation_data.action_suitable_slots[0]
        except (IndexError, AttributeError):
            pass
    return action_final


def _bake_animation_like_rokoko(source, target, root_bones):
    frame_split = 25
    frame_start, frame_end = _read_anim_start_end(source)
    if frame_start is None or frame_end is None:
        return None
    frame_start, frame_end = int(frame_start), int(frame_end)
    _set_active(target)
    actions_all = []

    bpy.ops.object.mode_set(mode="POSE")
    for frame in range(frame_start, frame_end + 2, frame_split):
        start = frame
        end = frame + frame_split - 1
        if end > frame_end:
            end = frame_end
        if start > end:
            continue
        bpy.ops.nla.bake(
            frame_start=start,
            frame_end=end,
            visual_keying=True,
            only_selected=True,
            use_current_action=False,
            bake_types={"POSE"},
        )
        target.animation_data.action.name = "MRA_RETARGETING_" + str(frame)
        actions_all.append(target.animation_data.action)
    bpy.ops.object.mode_set(mode="OBJECT")
    return _create_final_action(target, actions_all, root_bones)


def retarget(scene, source, target, items=None, auto_scale=True, use_pose="REST", **_ignored):
    """Standalone port of Rokoko's RetargetAnimation operator."""
    if not source or not target or source == target:
        raise ValueError("Source and target armatures must be different")
    if not source.animation_data or not source.animation_data.action:
        raise ValueError("Source armature has no Action")

    retarget_items = _valid_retarget_items(scene, source, target)
    if not retarget_items:
        raise ValueError("No valid mapped bones")
    root_bones = _find_root_bones(target, retarget_items)
    if not root_bones:
        raise ValueError("No mapped root bone found")

    source.data.pose_position = "POSE"
    target.data.pose_position = "POSE"
    if use_pose == "REST":
        _reset_pose_rotations(source)
        _reset_pose_rotations(target)

    source_scale = copy.deepcopy(source.scale)
    helper_source = None
    target_rotation_mode = target.rotation_mode
    target.rotation_mode = "QUATERNION"
    target_rotation = copy.deepcopy(target.rotation_quaternion)
    target_location = copy.deepcopy(target.location)

    try:
        if auto_scale:
            _remove_object_transform_curves(source)
            _scale_source_like_rokoko(source, target, retarget_items, root_bones)

        helper_source = _copy_rest_pose_like_rokoko(bpy.context, source)

        bpy.ops.object.select_all(action="DESELECT")
        _set_active(target)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        bone_transforms = {}
        bpy.ops.object.mode_set(mode="EDIT")
        for bone in target.data.edit_bones:
            try:
                bone.select = False
            except AttributeError:
                pass
            bone_transforms[bone.name] = (
                helper_source.matrix_world.inverted() @ bone.head.copy(),
                helper_source.matrix_world.inverted() @ bone.tail.copy(),
                _mat3_to_vec_roll(helper_source.matrix_world.inverted().to_3x3() @ bone.matrix.to_3x3()),
            )
        bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.select_all(action="DESELECT")
        _set_active(helper_source)
        bpy.ops.object.mode_set(mode="EDIT")
        helper_names = {}
        for item in retarget_items:
            source_bone = helper_source.data.edit_bones.get(item.source_name)
            if not source_bone:
                continue
            helper_bone = helper_source.data.edit_bones.new(item.target_name + RETARGET_ID)
            helper_bone.head, helper_bone.tail, helper_bone.roll = bone_transforms[item.target_name]
            helper_bone.parent = source_bone
            helper_names[item.target_name] = helper_bone.name
        bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.select_all(action="DESELECT")
        _set_active(target)
        for item in retarget_items:
            target_bone = target.pose.bones.get(item.target_name)
            helper_name = helper_names.get(item.target_name)
            if not target_bone or not helper_name:
                continue
            rotation = target_bone.constraints.new("COPY_ROTATION")
            rotation.name += RETARGET_ID
            rotation.target = helper_source
            rotation.subtarget = helper_name
            if target_bone.name in root_bones:
                location = target_bone.constraints.new("COPY_LOCATION")
                location.name += RETARGET_ID
                location.target = helper_source
                location.subtarget = item.source_name

            try:
                target.data.bones.get(item.target_name).select = True
            except Exception:
                target.pose.bones.get(item.target_name).select = True

        action_final = _bake_animation_like_rokoko(helper_source, target, root_bones)

        bpy.ops.object.select_all(action="DESELECT")
        _set_active(helper_source)
        if helper_source.animation_data and helper_source.animation_data.action:
            bpy.data.actions.remove(helper_source.animation_data.action)
        bpy.ops.object.delete()
        helper_source = None

        if action_final:
            action_final.name = source.animation_data.action.name + " Retarget"

        for bone in target.pose.bones:
            for constraint in list(bone.constraints):
                if RETARGET_ID in constraint.name:
                    bone.constraints.remove(constraint)

        bpy.ops.object.select_all(action="DESELECT")
        _set_active(target)
        target.rotation_quaternion = target_rotation
        target.location = target_location
        target.rotation_quaternion.w = -target.rotation_quaternion.w
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        target.rotation_quaternion = target_rotation
        target.rotation_mode = target_rotation_mode
        source.scale = source_scale
        bpy.ops.object.select_all(action="DESELECT")
        _set_active(target)
        return target
    finally:
        if helper_source and helper_source.name in bpy.data.objects:
            bpy.data.objects.remove(helper_source, do_unlink=True)
        source.scale = source_scale
