from bpy_extras import anim_utils


def get_fcurves(action, slot_identifier=0):
    if not action:
        return []
    if hasattr(action, "fcurves"):
        return action.fcurves
    if not action.slots:
        return []
    try:
        slot = action.slots[slot_identifier]
    except IndexError:
        return []
    channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
    return channelbag.fcurves if channelbag else []


def ensure_fcurve(action, data_path, index=0, slot_identifier=0, group_name=""):
    if hasattr(action, "fcurves"):
        return action.fcurves.new(data_path=data_path, index=index, action_group=group_name)
    if not action.slots:
        action.slots.new(name="Slot_0", id_type="OBJECT")
    try:
        slot = action.slots[slot_identifier]
    except IndexError:
        slot = action.slots.new(name=f"Slot_{slot_identifier}", id_type="OBJECT")
    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    return channelbag.fcurves.ensure(data_path, index=index, group_name=group_name)


def bind_action_to_object(obj, action, slot_identifier=0):
    """Assign an Action and its slot to an ID object across Blender versions."""
    if obj is None or action is None:
        return False
    obj.animation_data_create()
    obj.animation_data.action = action

    # Blender 5.0+ uses slotted Actions. Assigning only ``action`` is not
    # sufficient when the Action was built through the low-level API.
    if hasattr(obj.animation_data, "action_slot"):
        suitable = getattr(obj.animation_data, "action_suitable_slots", None)
        if suitable:
            try:
                obj.animation_data.action_slot = suitable[slot_identifier]
            except IndexError:
                obj.animation_data.action_slot = suitable[0]
        elif getattr(action, "slots", None):
            try:
                obj.animation_data.action_slot = action.slots[slot_identifier]
            except IndexError:
                obj.animation_data.action_slot = action.slots[0]
    return True
