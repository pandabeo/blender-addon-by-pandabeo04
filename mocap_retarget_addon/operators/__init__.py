import math

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty

from ..core import action_utils, game_axis, mapping, naming, retarget, smoothing


class MRA_OT_import_bvh(bpy.types.Operator, ImportHelper):
    bl_idname = "mra.import_bvh"
    bl_label = "Import BioVision Motion Capture (BVH)"
    bl_description = "Import a BVH using Blender's built-in BioVision Motion Capture importer"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".bvh"
    filter_glob: StringProperty(default="*.bvh", options={"HIDDEN"})

    def execute(self, context):
        before = set(bpy.data.objects)
        try:
            # BioVision BVH is shipped with Blender as io_anim_bvh. It may be
            # disabled in Preferences, so enable it automatically on demand.
            if not hasattr(bpy.ops.import_anim, "bvh"):
                bpy.ops.preferences.addon_enable(module="io_anim_bvh")
            if not hasattr(bpy.ops.import_anim, "bvh"):
                raise RuntimeError("Blender BioVision Motion Capture (BVH) importer is unavailable")
            result = bpy.ops.import_anim.bvh(
                filepath=self.filepath,
                target="ARMATURE",
                global_scale=context.scene.mra_bvh_unit_scale,
                frame_start=1,
                update_scene_fps=True,
                update_scene_duration=True,
            )
            if "FINISHED" not in result:
                raise RuntimeError("Blender BVH importer was cancelled")
            new_armatures = [
                obj for obj in bpy.data.objects
                if obj not in before and obj.type == "ARMATURE"
            ]
            selected_armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
            candidates = new_armatures or selected_armatures
            if not candidates:
                raise RuntimeError("Blender BVH importer did not create an armature")
            obj = candidates[-1]
            obj["MRA_BVH_FILE"] = self.filepath
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            action = obj.animation_data.action if obj.animation_data else None
            if action:
                action_utils.bind_action_to_object(obj, action)
                start, end = action.frame_range
                context.scene.frame_start = max(1, math.floor(start))
                context.scene.frame_end = max(context.scene.frame_start, math.ceil(end))
                context.scene.frame_set(context.scene.frame_start)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, "BVH import failed: " + str(exc))
            return {"CANCELLED"}
        context.scene.mra_source_armature = obj
        context.scene.mra_status = "BVH imported: " + obj.name
        self.report({"INFO"}, "BioVision Motion Capture BVH imported as source armature")
        return {"FINISHED"}


class MRA_OT_rename_mixamo(bpy.types.Operator):
    bl_idname = "mra.rename_mixamo"
    bl_label = "Rename to Mixamo"
    bl_description = "Rename source armature bones to the selected Mixamo naming convention"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = context.scene.mra_source_armature or context.object
        try:
            renamed, skipped = naming.rename_armature(source, context.scene.mra_prefix_mode)
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        message = f"Renamed {renamed} bones"
        if skipped:
            message += f"; skipped {len(skipped)} duplicates"
        context.scene.mra_status = message
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MRA_OT_filter_motion(bpy.types.Operator):
    bl_idname = "mra.filter_motion"
    bl_label = "Create Cleaned Action"
    bl_description = "Create and assign a cleaned copy of the source Action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        source = context.scene.mra_source_armature
        if not source or not source.animation_data or not source.animation_data.action:
            self.report({"ERROR"}, "Source armature has no Action")
            return {"CANCELLED"}
        old_action = source.animation_data.action
        cleaned = smoothing.filter_action(
            old_action,
            context.scene.mra_smoothing_strength if context.scene.mra_smooth_enabled else 0.0,
            context.scene.mra_outlier_angle if context.scene.mra_outlier_enabled else 0.0,
        )
        action_utils.bind_action_to_object(source, cleaned)
        context.scene.mra_status = "Cleaned Action created; raw Action preserved"
        self.report({"INFO"}, "Cleaned Action assigned to source")
        return {"FINISHED"}


class MRA_OT_build_mapping(bpy.types.Operator):
    bl_idname = "mra.build_mapping"
    bl_label = "Auto Map Bones"
    bl_description = "Automatically match source bones to target bones using Mixamo-style names"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        source, target = scene.mra_source_armature, scene.mra_target_armature
        if not source or not target:
            self.report({"ERROR"}, "Select both source and target armatures")
            return {"CANCELLED"}
        scene.mra_mapping.clear()
        for key, source_name, target_name, confidence in mapping.detect_map(source, target, scene.mra_include_fingers):
            item = scene.mra_mapping.add()
            item.key = key
            item.source_name = source_name
            item.target_name = target_name
            item.confidence = confidence
        mapped, missing, duplicates = mapping.mapping_summary(scene.mra_mapping)
        scene.mra_status = f"Mapped {mapped}; missing {missing}; duplicate targets {duplicates}"
        self.report({"INFO"}, scene.mra_status)
        return {"FINISHED"}


class MRA_OT_clear_mapping(bpy.types.Operator):
    bl_idname = "mra.clear_mapping"
    bl_label = "Clear Mapping"
    bl_description = "Remove all current source-to-target bone mappings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.mra_mapping.clear()
        context.scene.mra_status = "Mapping cleared"
        return {"FINISHED"}


class MRA_OT_retarget(bpy.types.Operator):
    bl_idname = "mra.retarget"
    bl_label = "Retarget Animation"
    bl_description = "Bake the source motion onto the target armature using the Rokoko-style retarget pipeline"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        source = scene.mra_source_armature
        target = scene.mra_target_armature
        if not source or not target:
            self.report({"ERROR"}, "Select both source and target armatures")
            return {"CANCELLED"}

        original_action = source.animation_data.action if source.animation_data else None
        working_action = None
        try:
            if scene.mra_auto_clean_on_retarget and (scene.mra_smooth_enabled or scene.mra_outlier_enabled):
                working_action = smoothing.filter_action(
                    original_action,
                    scene.mra_smoothing_strength if scene.mra_smooth_enabled else 0.0,
                    scene.mra_outlier_angle if scene.mra_outlier_enabled else 0.0,
                )
                action_utils.bind_action_to_object(source, working_action)

            output = retarget.retarget(
                scene,
                source,
                target,
                scene.mra_mapping,
                auto_scale=True,
                use_pose=scene.mra_use_pose,
            )
        except (ValueError, RuntimeError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        finally:
            if original_action:
                action_utils.bind_action_to_object(source, original_action)
        scene.mra_status = "Retargeted: " + output.name
        self.report({"INFO"}, "Retargeted animation created on " + output.name)
        return {"FINISHED"}


class MRA_OT_validate(bpy.types.Operator):
    bl_idname = "mra.validate"
    bl_label = "Validate Setup"
    bl_description = "Check that source, target, Action, and mapping are ready for retargeting"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        problems = []
        if not scene.mra_source_armature:
            problems.append("source armature")
        elif not scene.mra_source_armature.animation_data or not scene.mra_source_armature.animation_data.action:
            problems.append("source Action")
        if not scene.mra_target_armature:
            problems.append("target armature")
        mapped, missing, duplicates = mapping.mapping_summary(scene.mra_mapping)
        if not scene.mra_mapping:
            problems.append("bone mapping")
        if missing:
            problems.append(f"{missing} missing bone mappings")
        if duplicates:
            problems.append(f"{duplicates} duplicate target mappings")
        scene.mra_status = "Ready" if not problems else "Missing: " + ", ".join(problems)
        self.report({"INFO" if not problems else "WARNING"}, scene.mra_status)
        return {"FINISHED"}


class MRA_OT_convert_active_game_y_up(bpy.types.Operator):
    bl_idname = "mra.convert_active_game_y_up"
    bl_label = "Convert Active to Game Y-Up"
    bl_description = "Rotate the active object from Blender Z-Up orientation to Game Y-Up orientation; parent children follow automatically"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = game_axis.convert_active_to_game_y_up(context)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Converted '{obj.name}' to Game Y-Up")
        return {"FINISHED"}


class MRA_OT_restore_active_blender_z_up(bpy.types.Operator):
    bl_idname = "mra.restore_active_blender_z_up"
    bl_label = "Restore Blender Z-Up"
    bl_description = "Undo the Game Y-Up rotation on the active object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = game_axis.restore_active_to_blender_z_up(context)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Restored '{obj.name}' to Blender Z-Up")
        return {"FINISHED"}


class MRA_OT_apply_all_transform(bpy.types.Operator):
    bl_idname = "mra.apply_all_transform"
    bl_label = "Apply All Transforms"
    bl_description = "Apply Location, Rotation and Scale to the active object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = game_axis.apply_active_transform(context, location=True, rotation=True, scale=True)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Applied all transforms to '{obj.name}'")
        return {"FINISHED"}


class MRA_OT_apply_rotation_scale(bpy.types.Operator):
    bl_idname = "mra.apply_rotation_scale"
    bl_label = "Apply Rotation & Scale"
    bl_description = "Apply Rotation and Scale to the active object while keeping Location"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            obj = game_axis.apply_active_transform(context, location=False, rotation=True, scale=True)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Applied rotation and scale to '{obj.name}'")
        return {"FINISHED"}


def _draw_game_axis_object_menu(self, context):
    self.layout.separator()
    self.layout.operator("mra.convert_active_game_y_up", icon="EXPORT")
    self.layout.operator("mra.restore_active_blender_z_up", icon="LOOP_BACK")


if hasattr(bpy.types, "FileHandler"):
    class MRA_FH_bvh(bpy.types.FileHandler):
        bl_idname = "MRA_FH_bvh"
        bl_label = "Mocap Bridge BVH"
        bl_import_operator = "mra.import_bvh"
        bl_file_extensions = ".bvh"

        @classmethod
        def poll_drop(cls, context):
            return bool(context.area and context.area.type in {"VIEW_3D", "PROPERTIES"})
else:
    MRA_FH_bvh = None


CLASSES = (
    MRA_OT_import_bvh,
    MRA_OT_rename_mixamo,
    MRA_OT_filter_motion,
    MRA_OT_build_mapping,
    MRA_OT_clear_mapping,
    MRA_OT_retarget,
    MRA_OT_validate,
    MRA_OT_convert_active_game_y_up,
    MRA_OT_restore_active_blender_z_up,
    MRA_OT_apply_all_transform,
    MRA_OT_apply_rotation_scale,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(_draw_game_axis_object_menu)
    bpy.types.VIEW3D_MT_object_context_menu.append(_draw_game_axis_object_menu)
    if MRA_FH_bvh:
        bpy.utils.register_class(MRA_FH_bvh)


def unregister():
    bpy.types.VIEW3D_MT_object_context_menu.remove(_draw_game_axis_object_menu)
    bpy.types.VIEW3D_MT_object.remove(_draw_game_axis_object_menu)
    if MRA_FH_bvh:
        bpy.utils.unregister_class(MRA_FH_bvh)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
