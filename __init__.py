import typing as t
import pathlib
import logging

import numpy as np
from openctm.openctm import *
import bpy
import bpy.utils.previews

from .rsi_lib import RSIApiWrapper, RSIException

log = logging.getLogger(__name__)
thumbs = bpy.utils.previews.new()
rsi = RSIApiWrapper()
search_results = []

def _get_thumbnail_icon(sid: str, url: str) -> int:
    if sid not in thumbs:
        if not bpy.app.online_access:
            # this function _should_ never be called without online access,
            # but just in case, let's make extra sure we never make network
            # calls without it.
            raise RSIException("Can't load thumbnail without internet access")
        filename = rsi.get_thumbnail(sid, url)
        ip = thumbs.load(sid, filename, "IMAGE")

        # it appears that images don't always fully load when thumbs.load()
        # is called, but accessing the image_size property forces the image
        # to load fully???
        _wat = ip.image_size[0] + ip.image_size[1]

    return thumbs[sid].icon_id

# https://docs.blender.org/manual/en/dev/advanced/extensions/python_wheels.html
prefs = None
def _init(self, context):
    """
    Configure global things - gets called once on startup and then again
    whenever the preferences are changed.
    """
    global rsi, prefs
    prefs = bpy.context.preferences.addons[__package__].preferences
    addon_dir = pathlib.Path(bpy.utils.extension_path_user(__package__))

    rsi = RSIApiWrapper()
    rsi.cache_dir = addon_dir / "cache"

    logging.basicConfig(
        level=logging.DEBUG if prefs.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info("Initialized RSI Browser")

class RSIClearCacheOperator(bpy.types.Operator):
    """
    Clear RSI Browser Cache
    """

    bl_idname = "rsi.clear_cache"
    bl_label = "Clear Cache"
    bl_description = ("Clears the cache, the cache is used to speed up repeated look up times"
                      "when this is cleared, initial loading will be slow and second slow will"
                      "noticeable quicker")

    @classmethod
    def poll(self, context):
        # Deactivate when cache is empty
        return os.path.exists(rsi.cache_dir)

    def execute(self, context) -> t.Set[str]:
        self.report({"INFO"}, f"Cleared cache folder: {rsi.cache_dir}")
        rsi.clear_cache()
        return {'FINISHED'}

class RSIBrowserPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    debug: bpy.props.BoolProperty(name="Debug",
                                  default=False,
                                  update=_init)  # type: ignore
    cleanup_recalculate: bpy.props.BoolProperty(name="Recalculate normals",
                                                default=True,
                                                update=_init)  # type: ignore
    cleanup_close: bpy.props.BoolProperty(name="Remove Close vertices",
                                          default=False,
                                          update=_init)  # type: ignore
    cleanup_isolated: bpy.props.BoolProperty(name="Remove Isolated vertices",
                                             default=False,
                                             update=_init)  # type: ignore
    cleanup_non_manifold: bpy.props.BoolProperty(name="Remove Non-manifold edges",
                                                 default=False,
                                                 update=_init)  # type: ignore
    auto_scale: bpy.props.BoolProperty(name="Automatically scale model to view",
                                       default=True,
                                       update=_init)  # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "debug")
        layout.prop(self, "cleanup_recalculate")
        layout.prop(self, "cleanup_close")
        layout.prop(self, "cleanup_isolated")
        layout.prop(self, "cleanup_non_manifold")
        layout.prop(self, "auto_scale")

        layout.operator(RSIClearCacheOperator.bl_idname, icon="CONSOLE")

class RSIImportOperator(bpy.types.Operator):
    """
    Fetch a 3D model from RSI and import it into the scene.
    """

    bl_idname = "rsi.import"
    bl_label = "Import a ship"

    sid: bpy.props.StringProperty()  # type: ignore

    def execute(self, context) -> t.Set[str]:
        if not bpy.app.online_access:
            self.report({"ERROR"}, "RSI Browser requires online access")
            return {"CANCELLED"}

        try:
                si = rsi.get_ship_info(self.sid)
                if si['hologram_3d']:
                    self.report({"INFO"}, f"Importing Model for {si['name']}")
                    ctm = import_mesh(rsi.get_model(self.sid, si['hologram_3d']))

                    mesh = bpy.data.meshes.new(name=si["name"])
                    mesh.from_pydata(ctm[0], [], ctm[1])
                    mesh.update()

                    obj = bpy.data.objects.new(name=si["name"], object_data=mesh)

                    scene = bpy.context.scene
                    scene.collection.objects.link(obj)

                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    clean_mesh(
                        remove_non_manifold=prefs.cleanup_non_manifold,
                        remove_isolated=prefs.cleanup_isolated,
                        merge_close_vertices=prefs.cleanup_close,
                        recalculate_normals=prefs.cleanup_recalculate,
                        threshold=0.0001
                    )
                    clean_mesh()
                    if prefs.auto_scale:
                        scale_to_viewport(obj)

                    assert isinstance(obj, bpy.types.Object)
                    obj["rsiId"] = self.sid
                    obj.name = si["name"]
                    if not obj.parent:
                        obj.location = bpy.context.scene.cursor.location

                    self.report({"INFO"}, f"Imported Model successfully")
                else:
                    self.report({"INFO"},f"Model for {si['name']} cannot be found")

        except RSIException as e:
            self.report({"ERROR"}, f"Something went wrong when trying to import model file {e}")
            return {"CANCELLED"}
        return {"FINISHED"}


class RSIBrowserPanel(bpy.types.Panel):
    """
    Browse RSI products.

    For each product, add a button for the RSIImportOperator.
    """

    bl_label = "RSI Browser"
    bl_idname = "OBJECT_PT_rsi_browser"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RSI"

    def draw(self, context) -> None:
        if not bpy.app.online_access:
            self.layout.label(text="Blender is set to offline mode")
            self.layout.label(text="To use RSI Browser, enable online access:")
            self.layout.operator("screen.userpref_show", text="Open Preferences").section = "SYSTEM"
            return

        layout = self.layout
        layout.prop(context.window_manager, "rsi_search", text="", icon="VIEWZOOM")

        grid = layout.grid_flow(even_columns=True)
        for result in search_results:
            box = grid.box()
            box.label(text=result["name"])
            icon = _get_thumbnail_icon(str(result["id"]), result["thumbnail"])
            box.template_icon(icon_value=icon, scale=10)
            btn = box.operator(RSIImportOperator.bl_idname, text="Import")
            btn.sid = f"{result['id']}"

_last_id = None
_last_si = None


class RSIProductPanel(bpy.types.Panel):
    """
    If the currently selected object has an "name" property, display
    some details about the product and a button to open the RSI website.
    """

    bl_label = "RSI Ship"
    bl_idname = "OBJECT_PT_rsi_product"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RSI"

    @classmethod
    def poll(self, context):
        return context.object and context.object.get("rsiId")

    def draw(self, context) -> None:
        global _last_si, _last_id

        layout = self.layout
        sid = context.object.get("rsiId")

        if sid == _last_id:
            si = _last_si
        else:
            if not bpy.app.online_access:
                layout.label(text="Enable online access to see more details")
                return

            si = rsi.get_ship_info(sid)
            _last_id = sid
            _last_si = si

        row = layout.row()
        row.label(text="Name")
        row.label(text=si['name'])

        icon = _get_thumbnail_icon(str(si['id']), si["media"][0]["images"]['subscribers_vault_thumbnail'])
        layout.template_icon(icon_value=icon, scale=10)

        grid = layout.grid_flow(row_major=True, even_rows=False, columns=2)
        grid.label(text="Manufacturer")
        grid.label(text=si["manufacturer"]["name"])
        grid.label(text="Type")
        grid.label(text=si["type"])
        grid.label(text="Focus")
        grid.label(text=si["focus"])
        grid.label(text="Crew")
        grid.label(text=f'{si["min_crew"]} - {si["max_crew"]}')

        layout.operator("wm.url_open", text="Open Website").url = "https://robertsspaceindustries.com" + si["url"]


def _update_search(self, context) -> None:
    global search_results
    if bpy.app.online_access:
        search_results = rsi.search(self.rsi_search)
    else:
        search_results = []


def register() -> None:
    bpy.types.WindowManager.rsi_search = bpy.props.StringProperty(
        name="Search", default="", update=_update_search, options={"SKIP_SAVE"}
    )
    bpy.utils.register_class(RSIClearCacheOperator)
    bpy.utils.register_class(RSIBrowserPreferences)
    bpy.utils.register_class(RSIBrowserPanel)
    bpy.utils.register_class(RSIProductPanel)
    bpy.utils.register_class(RSIImportOperator)

    _init(None, None)


def unregister() -> None:
    del bpy.types.WindowManager.rsi_search
    bpy.utils.unregister_class(RSIImportOperator)
    bpy.utils.unregister_class(RSIProductPanel)
    bpy.utils.unregister_class(RSIBrowserPanel)
    bpy.utils.unregister_class(RSIBrowserPreferences)
    bpy.utils.unregister_class(RSIClearCacheOperator)

def flip_vertices(vertices):
    # Flip Y and Z axes to convert from Three.js to Blender
    vertices_np = np.array(vertices, dtype=np.float32)
    flipped_vertices = vertices_np.copy()
    flipped_vertices[:, [1, 2]] = vertices_np[:, [2, 1]] * np.array([-1, 1])
    return flipped_vertices

def import_mesh(_filename) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    ctm_context = ctmNewContext(CTM_IMPORT)
    vertices_ = []
    faces_ = []
    try:
        ctmLoad(ctm_context, _filename.encode("utf-8"))
        err = ctmGetError(ctm_context)
        if err != CTM_NONE:
            raise IOError("Error loading file: %s" % str(ctmErrorString(err)))

        # Read vertices
        vertex_count = ctmGetInteger(ctm_context, CTM_VERTEX_COUNT)
        vertex_ctm = ctmGetFloatArray(ctm_context, CTM_VERTICES)
        for i in range(vertex_count):
            vertices_.append((float(vertex_ctm[i * 3]), float(vertex_ctm[i * 3 + 1]), float(vertex_ctm[i * 3 + 2])))

        # Flip vertices
        vertices_ = flip_vertices(vertices_).tolist()

        # Read faces
        face_count = ctmGetInteger(ctm_context, CTM_TRIANGLE_COUNT)
        face_ctm = ctmGetIntegerArray(ctm_context, CTM_INDICES)
        for i in range(face_count):
            faces_.append((int(face_ctm[i * 3]), int(face_ctm[i * 3 + 1]), int(face_ctm[i * 3 + 2])))

    except RSIException as e:
        log.exception(f"Something went wrong when trying to import model file {e}")
    finally:
        ctmFreeContext(ctm_context)

    return vertices_, faces_

def clean_mesh(remove_non_manifold=True, remove_isolated=True, merge_close_vertices=True, recalculate_normals=True, threshold=0.0001):
    # Ensure we are in edit mode
    bpy.ops.object.mode_set(mode='EDIT')

    # Remove non-manifold edges
    if remove_non_manifold:
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold()
        bpy.ops.mesh.delete(type='EDGE_FACE')

    # Remove isolated vertices
    if remove_isolated:
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_loose()
        bpy.ops.mesh.delete(type='VERT')

    # Merge close vertices
    if merge_close_vertices:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=threshold)

    # Recalculate normals
    if recalculate_normals:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)

    # Return to object mode
    bpy.ops.object.mode_set(mode='OBJECT')


def scale_to_viewport(obj):
    # Switch to Object Mode
    bpy.ops.object.mode_set(mode='OBJECT')

    # Get the bounding box dimensions
    bounding_box = obj.bound_box
    dimensions = [abs(bounding_box[i][j] - bounding_box[i - 4][j]) for i in range(4, 8) for j in range(3)]
    max_dimension = max(dimensions)

    # Calculate the scaling factor
    scale_factor = 1.0 / max_dimension
    obj.scale = (scale_factor, scale_factor, scale_factor)

    # Apply the scaling
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Center the object to the origin
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

    # Update the viewport to center the object
    bpy.ops.view3d.view_all(center=True)
