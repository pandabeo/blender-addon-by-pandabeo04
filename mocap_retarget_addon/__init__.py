bl_info = {
    "name": "Blender Add-On by Pandabeo04",
    "author": "Pandabeo04",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > CUSTOM ADD-ON — PANDABEO04",
    "description": "Import BVH motion capture, clean and retarget animation, and convert objects to Game Y-Up orientation.",
    "category": "Animation",
}

import bpy

from . import properties
from . import operators
from . import panels


def register():
    properties.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
