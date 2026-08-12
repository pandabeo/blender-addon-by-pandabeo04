import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Object, PropertyGroup, Scene

from .core import retarget


class BoneMappingItem(PropertyGroup):
    key: StringProperty(name="Key")
    source_name: StringProperty(name="Source")
    target_name: StringProperty(name="Target")
    enabled: BoolProperty(name="Use", default=True)
    confidence: FloatProperty(name="Confidence", default=0.0, min=0.0, max=1.0)


def _armature_poll(_, obj):
    return obj.type == "ARMATURE"


def register():
    bpy.utils.register_class(BoneMappingItem)
    Scene.mra_source_armature = PointerProperty(name="Source Armature", description="Armature containing the imported motion capture Action", type=Object, poll=_armature_poll)
    Scene.mra_target_armature = PointerProperty(name="Target Armature", description="Armature that will receive the retargeted animation", type=Object, poll=_armature_poll)
    Scene.mra_mapping = CollectionProperty(type=BoneMappingItem)
    Scene.mra_mapping_index = IntProperty(default=0)
    Scene.mra_prefix_mode = EnumProperty(
        name="Mixamo Names",
        description="Choose whether renamed bones use the mixamorig: prefix",
        items=[
            ("NONE", "No Prefix", "Hips, Spine, LeftArm"),
            ("MIXAMO_PREFIX", "mixamorig: Prefix", "mixamorig:Hips, mixamorig:Spine"),
        ],
        default="NONE",
    )
    Scene.mra_bvh_unit_scale = FloatProperty(
        name="BVH Unit Scale",
        description="Scale applied by Blender's BioVision BVH importer",
        default=1.0,
        min=0.0001,
        max=1000.0,
        precision=4,
    )
    Scene.mra_use_pose = EnumProperty(
        name="Use Pose",
        description="Choose whether retargeting starts from the armatures' rest pose or current pose",
        items=[
            ("REST", "Rest Pose", "Reset source and target rotations before retargeting"),
            ("CURRENT", "Current Pose", "Use the current source and target pose"),
        ],
        default="REST",
    )
    Scene.mra_auto_clean_on_retarget = BoolProperty(
        name="Auto Clean Before Retarget",
        description="Smooth motion and remove rotation spikes automatically for this retarget operation",
        default=True,
    )
    Scene.mra_include_fingers = BoolProperty(name="Include Fingers", description="Include finger bones in automatic mapping", default=True)
    Scene.mra_smooth_enabled = BoolProperty(name="Smooth Motion", description="Reduce high-frequency motion changes in the Action", default=True)
    Scene.mra_smoothing_strength = FloatProperty(name="Smooth Strength", description="Amount of temporal smoothing; higher values produce softer motion", default=0.35, min=0.0, max=0.95)
    Scene.mra_outlier_enabled = BoolProperty(name="Remove Rotation Spikes", description="Suppress sudden abnormal rotation jumps", default=True)
    Scene.mra_outlier_angle = FloatProperty(name="Spike Angle", description="Rotation difference treated as a spike", default=45.0, min=1.0, max=180.0)
    Scene.mra_status = StringProperty(name="Status", default="Ready")


def unregister():
    for name in (
        "mra_source_armature", "mra_target_armature", "mra_mapping", "mra_mapping_index",
        "mra_prefix_mode", "mra_bvh_unit_scale", "mra_use_pose", "mra_auto_clean_on_retarget", "mra_include_fingers", "mra_smooth_enabled", "mra_smoothing_strength",
        "mra_outlier_enabled", "mra_outlier_angle", "mra_status",
    ):
        if hasattr(Scene, name):
            delattr(Scene, name)
    bpy.utils.unregister_class(BoneMappingItem)
