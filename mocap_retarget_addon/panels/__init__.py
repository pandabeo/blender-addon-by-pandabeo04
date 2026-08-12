import bpy


class MRA_UL_mapping(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text=item.key)
        row.label(text=item.source_name or "—")
        row.label(text="→")
        row.label(text=item.target_name or "—")
        if item.confidence < 1.0:
            row.label(text="?", icon="ERROR")


class MRA_PT_main(bpy.types.Panel):
    bl_idname = "MRA_PT_main"
    bl_label = "Mocap Rename Retarget"
    bl_options = {"DEFAULT_CLOSED"}
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    # Keep all current mechanisms together in the first Mocap tab.
    # Future mechanisms can register additional panels with other categories.
    bl_category = "CUSTOM ADD-ON — PANDABEO04"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        header = layout.row()
        header.alignment = "CENTER"
        header.label(text="MOCAP BRIDGE", icon="ARMATURE_DATA")
        layout.label(text="BVH  •  Mixamo Rename  •  Retarget", icon="INFO")

        box = layout.box()
        box.label(text="01  IMPORT SOURCE", icon="IMPORT")
        row = box.row()
        row.scale_y = 1.25
        row.operator("mra.import_bvh", text="Import BioVision BVH", icon="IMPORT")
        box.prop(scene, "mra_bvh_unit_scale", text="Unit Scale")
        box.prop(scene, "mra_source_armature")
        row = box.row(align=True)
        row.operator("mra.rename_mixamo", text="Rename Bones", icon="EDITMODE_HLT")
        row.prop(scene, "mra_prefix_mode", text="")

        box = layout.box()
        box.label(text="02  CLEAN MOTION", icon="MOD_SMOOTH")
        box.label(text="Cleaning is also applied automatically during Retarget", icon="INFO")
        box.prop(scene, "mra_smooth_enabled")
        if scene.mra_smooth_enabled:
            box.prop(scene, "mra_smoothing_strength")
        box.prop(scene, "mra_outlier_enabled")
        if scene.mra_outlier_enabled:
            box.prop(scene, "mra_outlier_angle")
        box.operator("mra.filter_motion", text="Create Cleaned Action", icon="FCURVE")

        box = layout.box()
        box.label(text="03  MAP BONES", icon="CONSTRAINT_BONE")
        box.prop(scene, "mra_target_armature")
        box.prop(scene, "mra_include_fingers")
        row = box.row(align=True)
        row.operator("mra.build_mapping", text="Auto Map Bones", icon="AUTOMERGE_ON")
        row.operator("mra.clear_mapping", text="Clear", icon="X")
        if scene.mra_mapping:
            box.template_list("MRA_UL_mapping", "MRA_MAPPING", scene, "mra_mapping", scene, "mra_mapping_index", rows=8)

        box = layout.box()
        box.label(text="04  RETARGET", icon="ANIM_DATA")
        box.prop(scene, "mra_use_pose")
        box.prop(scene, "mra_auto_clean_on_retarget")
        row = box.row(align=True)
        row.operator("mra.validate", text="Validate", icon="CHECKMARK")
        row.operator("mra.retarget", text="Retarget Animation", icon="ANIM_DATA")
        row = box.row()
        row.scale_y = 1.4
        row.label(text="Tip: Hover over a control for details", icon="QUESTION")

        layout.separator()
        status = layout.box()
        status.label(text="STATUS", icon="INFO")
        status.label(text=scene.mra_status)

class MRA_PT_game_axis(bpy.types.Panel):
    bl_idname = "MRA_PT_game_axis"
    bl_label = "Game Engine Axis Converter"
    bl_options = {"DEFAULT_CLOSED"}
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CUSTOM ADD-ON — PANDABEO04"

    def draw(self, context):
        layout = self.layout
        obj = context.view_layer.objects.active

        layout.label(text="Blender Z-Up  →  Game Y-Up", icon="INFO")
        box = layout.box()
        box.label(text="ACTIVE OBJECT", icon="OBJECT_DATA")
        if obj:
            box.label(text=obj.name, icon="OBJECT_DATA")
            if obj.parent:
                box.label(text="Parent hierarchy follows this object", icon="CONSTRAINT")
            if obj.get("MRA_GAME_Y_UP_CONVERTED", False):
                box.label(text="Already marked as Game Y-Up", icon="CHECKMARK")
        else:
            box.label(text="Create or select an active object", icon="ERROR")

        box = layout.box()
        box.label(text="CONVERT ORIENTATION", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        row = box.row()
        row.scale_y = 1.3
        row.operator("mra.convert_active_game_y_up", text="Convert to Game Y-Up", icon="EXPORT")
        box.operator("mra.restore_active_blender_z_up", text="Restore Blender Z-Up", icon="LOOP_BACK")
        box.label(text="Changes rotation only; world location is preserved.", icon="INFO")
        box.label(text="Select the parent to convert a full hierarchy.", icon="QUESTION")

        box = layout.box()
        box.label(text="APPLY TRANSFORMS", icon="OBJECT_DATA")
        row = box.row(align=True)
        row.operator("mra.apply_all_transform", text="All", icon="CHECKMARK")
        row.operator("mra.apply_rotation_scale", text="Rotation + Scale", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        box.label(text="Applies to the active object only.", icon="INFO")


CLASSES = (MRA_UL_mapping, MRA_PT_main, MRA_PT_game_axis)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
