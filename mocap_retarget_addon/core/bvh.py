import json
import math
import re
from dataclasses import dataclass, field

import bpy
from mathutils import Euler, Matrix, Vector

from .action_utils import bind_action_to_object, ensure_fcurve


@dataclass(eq=False)
class BVHNode:
    name: str
    parent: object = None
    offset: Vector = field(default_factory=Vector)
    channels: list = field(default_factory=list)
    children: list = field(default_factory=list)
    end_offset: Vector = None


def _clean_line(lines, index):
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        raise ValueError("Unexpected end of BVH file")
    return lines[index].strip(), index + 1


def _parse_node(lines, index, parent=None):
    header, index = _clean_line(lines, index)
    parts = header.split()
    if len(parts) != 2 or parts[0] not in {"ROOT", "JOINT"}:
        raise ValueError("Expected ROOT or JOINT, got: " + header)
    node = BVHNode(parts[1], parent=parent)
    brace, index = _clean_line(lines, index)
    if brace != "{":
        raise ValueError("Expected '{' after " + node.name)

    while True:
        line, index = _clean_line(lines, index)
        parts = line.split()
        if parts[0] == "}":
            return node, index
        if parts[0] == "OFFSET" and len(parts) >= 4:
            node.offset = Vector((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "CHANNELS" and len(parts) >= 2:
            count = int(parts[1])
            node.channels = parts[2:2 + count]
            if len(node.channels) != count:
                raise ValueError("Invalid CHANNELS declaration for " + node.name)
        elif parts[0] == "JOINT":
            # Rewind one line because _parse_node expects the JOINT header.
            child, index = _parse_node(lines, index - 1, parent=node)
            node.children.append(child)
        elif parts[0] == "End" and len(parts) >= 2 and parts[1] == "Site":
            brace, index = _clean_line(lines, index)
            if brace != "{":
                raise ValueError("Expected '{' after End Site")
            offset_line, index = _clean_line(lines, index)
            offset_parts = offset_line.split()
            if offset_parts[0] != "OFFSET" or len(offset_parts) < 4:
                raise ValueError("Invalid End Site offset for " + node.name)
            node.end_offset = Vector((float(offset_parts[1]), float(offset_parts[2]), float(offset_parts[3])))
            closing, index = _clean_line(lines, index)
            if closing != "}":
                raise ValueError("Expected End Site closing brace")
        else:
            raise ValueError("Unsupported BVH hierarchy line: " + line)


def parse_bvh(filepath):
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as handle:
        lines = handle.read().splitlines()
    if not lines or lines[0].strip().upper() != "HIERARCHY":
        raise ValueError("This file is not a BVH hierarchy")

    root, index = _parse_node(lines, 1)
    while index < len(lines) and lines[index].strip().upper() != "MOTION":
        index += 1
    if index >= len(lines):
        raise ValueError("BVH MOTION section is missing")
    index += 1

    frame_line, index = _clean_line(lines, index)
    frame_match = re.match(r"Frames\s*:\s*(\d+)", frame_line, re.IGNORECASE)
    if not frame_match:
        raise ValueError("Invalid BVH Frames line")
    frame_count = int(frame_match.group(1))

    time_line, index = _clean_line(lines, index)
    time_match = re.match(r"Frame\s+Time\s*:\s*([0-9eE+_.-]+)", time_line, re.IGNORECASE)
    if not time_match:
        raise ValueError("Invalid BVH Frame Time line")
    frame_time = float(time_match.group(1))

    values = []
    for line in lines[index:]:
        values.extend(float(value) for value in line.split())

    nodes = []
    channels = []

    def flatten(node):
        nodes.append(node)
        channels.extend((node, channel) for channel in node.channels)
        for child in node.children:
            flatten(child)

    flatten(root)
    channel_count = len(channels)
    expected = frame_count * channel_count
    if len(values) < expected:
        raise ValueError(f"BVH motion data is incomplete: expected {expected} values, got {len(values)}")
    frames = [values[start:start + channel_count] for start in range(0, expected, channel_count)]
    return root, nodes, channels, frames, frame_time


def _convert_vector(vector, axis_mode):
    if axis_mode == "Y_UP_TO_Z_UP":
        # Common BVH coordinates are X-right, Y-up, Z-forward.
        # Blender uses X-right, Z-up, Y-depth. Preserve handedness with -Z on Y.
        return Vector((vector.x, -vector.z, vector.y))
    return Vector(vector)


def _convert_rotation(euler, axis_mode):
    quaternion = euler.to_quaternion()
    if axis_mode == "Y_UP_TO_Z_UP":
        basis = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
        matrix = basis @ quaternion.to_matrix() @ basis.inverted()
        return matrix.to_quaternion()
    return quaternion


def _unique_edit_name(armature, name):
    if not armature.edit_bones.get(name):
        return name
    index = 1
    while armature.edit_bones.get(f"{name}.{index:03d}"):
        index += 1
    return f"{name}.{index:03d}"


def _bone_path(name, property_name):
    return f"pose.bones[{json.dumps(name)}].{property_name}"


def import_bvh(filepath, scene, axis_mode="Y_UP_TO_Z_UP", unit_scale=1.0):
    root, nodes, channels, frames, frame_time = parse_bvh(filepath)
    source_name = filepath.rsplit("\\", 1)[-1].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    armature_data = bpy.data.armatures.new(source_name + "_BVH_DATA")
    obj = bpy.data.objects.new(source_name + "_BVH", armature_data)
    scene.collection.objects.link(obj)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = {}

    def create_bones(node, parent_edit=None, parent_head=None):
        name = _unique_edit_name(armature_data, node.name)
        bone = armature_data.edit_bones.new(name)
        bone.parent = parent_edit
        offset = _convert_vector(node.offset, axis_mode) * unit_scale
        bone.head = Vector((0, 0, 0)) if parent_head is None else parent_head + offset
        if node.children:
            tail_offset = _convert_vector(node.children[0].offset, axis_mode) * unit_scale
        elif node.end_offset is not None:
            tail_offset = _convert_vector(node.end_offset, axis_mode) * unit_scale
        else:
            tail_offset = Vector((0, 0.05, 0)) * unit_scale
        if tail_offset.length < 0.0001:
            tail_offset = Vector((0, 0.05, 0)) * unit_scale
        bone.tail = bone.head + tail_offset
        edit_bones[node] = bone.name
        for child in node.children:
            create_bones(child, bone, bone.head)

    create_bones(root)
    bpy.ops.object.mode_set(mode="OBJECT")

    for bone_name in edit_bones.values():
        pose_bone = obj.pose.bones.get(bone_name)
        if pose_bone:
            pose_bone.rotation_mode = "QUATERNION"

    action = bpy.data.actions.new(source_name + "_Raw")

    node_channels = {}
    for node in nodes:
        node_channels[node] = {}
        for index, channel in enumerate(node.channels):
            node_channels[node][channel.lower()] = index

    frame_number = len(frames)
    node_channel_start = {}
    cursor = 0
    for node in nodes:
        node_channel_start[node] = cursor
        cursor += len(node.channels)

    for node in nodes:
        bone_name = edit_bones[node]
        rotation_channels = [channel for channel in node.channels if channel.lower().endswith("rotation")]
        order = "".join(channel[0].upper() for channel in rotation_channels)
        if len(order) != 3 or set(order) != {"X", "Y", "Z"}:
            order = "XYZ"
        curves = [ensure_fcurve(action, _bone_path(bone_name, "rotation_quaternion"), i, group_name=bone_name)
                  for i in range(4)]
        location_curves = None
        if node is root and any(channel.lower().endswith("position") for channel in node.channels):
            location_curves = [ensure_fcurve(action, _bone_path(bone_name, "location"), i, group_name=bone_name)
                               for i in range(3)]

        for frame_index, values in enumerate(frames):
            start = node_channel_start[node]
            local_values = values[start:start + len(node.channels)]
            angles = [0.0, 0.0, 0.0]
            location = [0.0, 0.0, 0.0]
            for channel_index, channel in enumerate(node.channels):
                lower = channel.lower()
                value = local_values[channel_index]
                if lower.endswith("rotation"):
                    axis = lower[0]
                    angles["xyz".index(axis)] = math.radians(value)
                elif lower.endswith("position"):
                    axis = lower[0]
                    location["xyz".index(axis)] = value
            rotation = _convert_rotation(Euler(angles, order), axis_mode)
            frame = frame_index + 1
            for index, curve in enumerate(curves):
                curve.keyframe_points.insert(frame, rotation[index], options={"FAST"})
            if location_curves:
                converted = _convert_vector(Vector(location), axis_mode) * unit_scale
                for index, curve in enumerate(location_curves):
                    curve.keyframe_points.insert(frame, converted[index], options={"FAST"})

    for curve in action_utils_for(action):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
        curve.update()

    # Bind after the slot/channelbag has been populated. This is required by
    # Blender 5 slotted Actions; without it the Action can exist but appear to
    # have no animation on the imported armature.
    bind_action_to_object(obj, action)
    scene.frame_start = 1
    scene.frame_end = max(1, frame_number)
    if frame_time > 0:
        scene.render.fps = max(1, round(1.0 / frame_time))
        scene.render.fps_base = 1.0
    obj["MRA_BVH_FILE"] = filepath
    obj["MRA_BVH_FRAME_TIME"] = frame_time
    scene.frame_set(scene.frame_start)
    return obj


def action_utils_for(action):
    from .action_utils import get_fcurves
    return get_fcurves(action)
