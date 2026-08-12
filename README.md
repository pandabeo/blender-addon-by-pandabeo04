# Blender Add-On by Pandabeo04

Standalone Blender add-on with two tools:

1. **Mocap Rename Retarget** — import BVH, rename bones to Mixamo names, clean motion, map bones and bake a retargeted Action.
2. **Game Engine Axis Converter** — convert an active object from Blender Z-Up to Game Y-Up and apply transforms.

The retarget engine is standalone and does not require Rokoko Studio Live. Its helper-bone workflow follows the Rokoko-style retarget sequence while remaining independent of the Rokoko add-on.

## Install

Install the `mocap_retarget_addon` folder or a ZIP containing that folder from Blender's `Edit > Preferences > Add-ons > Install`.
Enable **Blender Add-On by Pandabeo04**, then open the 3D View sidebar with `N` and select the `CUSTOM ADD-ON — PANDABEO04` tab.

## Workflow

1. Open **Mocap Rename Retarget**.
2. Click **Import BioVision BVH**. The add-on automatically enables Blender's built-in BVH importer when needed.
3. Select the imported armature as Source.
4. Click **Rename Bones**.
5. Configure smoothing and rotation-spike removal if needed.
6. Select the Mixamo character as Target.
7. Click **Auto Map Bones** and inspect the table.
8. Click **Validate**.
9. Click **Retarget Animation**.

You can also drag a `.bvh` file from Windows Explorer directly into Blender's 3D View. The add-on registers a Blender File Handler and imports the file through the BioVision importer.

The default behavior preserves the original source Action and creates a new retargeted Action on the target.

For game-axis conversion, open **Game Engine Axis Converter**, select an active object or parent, and use **Convert to Game Y-Up**. The panel also includes **Apply All Transforms** and **Apply Rotation & Scale**.

## Notes

- The first release targets body animation and optional fingers.
- The current release targets body animation and optional fingers.
- Smoothing and rotation-spike removal can run automatically during the first retarget operation.
- The retargeting algorithm is independent of the Rokoko add-on and does not require Rokoko Studio or a login.
