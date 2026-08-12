import bpy
from mathutils import Matrix


# Blender: Z-up, Y-forward
# Game Y-up convention: Y-up, Z-forward
# This is a -90 degree rotation around X: (x, y, z) -> (x, z, -y).
BLENDER_TO_GAME_Y_UP = Matrix((
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
))
GAME_Y_UP_TO_BLENDER = BLENDER_TO_GAME_Y_UP.inverted()
CONVERTED_PROPERTY = "MRA_GAME_Y_UP_CONVERTED"


def _active_object(context):
    obj = context.view_layer.objects.active
    if not obj:
        raise ValueError("Create or select an active object first")
    if obj.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before converting orientation")
    return obj


def convert_active_to_game_y_up(context):
    obj = _active_object(context)
    if obj.get(CONVERTED_PROPERTY, False):
        raise ValueError(f"Object '{obj.name}' is already marked as Game Y-Up")

    world_matrix = obj.matrix_world.copy()
    converted = BLENDER_TO_GAME_Y_UP @ world_matrix
    # This tool changes orientation only. Keep the object's world location.
    converted.translation = world_matrix.translation
    obj.matrix_world = converted
    obj[CONVERTED_PROPERTY] = True
    return obj


def restore_active_to_blender_z_up(context):
    obj = _active_object(context)
    if not obj.get(CONVERTED_PROPERTY, False):
        raise ValueError(f"Object '{obj.name}' is not marked as Game Y-Up")

    world_matrix = obj.matrix_world.copy()
    restored = GAME_Y_UP_TO_BLENDER @ world_matrix
    restored.translation = world_matrix.translation
    obj.matrix_world = restored
    obj[CONVERTED_PROPERTY] = False
    return obj


def apply_active_transform(context, location=False, rotation=True, scale=True):
    """Apply transforms to the active object only, preserving selection state."""
    obj = _active_object(context)
    selected = list(context.selected_objects)
    previous_active = context.view_layer.objects.active
    try:
        for selected_obj in selected:
            selected_obj.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(
            location=location,
            rotation=rotation,
            scale=scale,
        )
    except RuntimeError as exc:
        raise ValueError(f"Could not apply transforms to '{obj.name}': {exc}") from exc
    finally:
        obj.select_set(False)
        for selected_obj in selected:
            if selected_obj.name in bpy.data.objects:
                selected_obj.select_set(True)
        if previous_active and previous_active.name in bpy.data.objects:
            context.view_layer.objects.active = previous_active
        else:
            context.view_layer.objects.active = obj
    return obj
