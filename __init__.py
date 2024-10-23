import typing as t
import pathlib
import logging
import os

from openctm.openctm import *
import bpy
import bmesh
import bpy.utils.previews  # type: ignore

from .rsi_lib import RSIApiWrapper, RSIException

log = logging.getLogger(__name__)
thumbs = bpy.utils.previews.new()
rsi = RSIApiWrapper()
search_results = []

def _get_thumbnail_icon(name: str, url: str) -> int:
    if name not in thumbs:
        log.info(url)
        if url is None or url is "":
            url = "https://t3.ftcdn.net/jpg/03/35/13/14/240_F_335131435_DrHIQjlOKlu3GCXtpFkIG1v0cGgM9vJC.jpg"

        if not bpy.app.online_access:
            # this function _should_ never be called without online access,
            # but just in case, let's make extra sure we never make network
            # calls without it.
            raise RSIException("Can't load thumbnail without internet access")
        filename = rsi.get_thumbnail(name, url)
        ip = thumbs.load(name, filename, "IMAGE")

        # it appears that images don't always fully load when thumbs.load()
        # is called, but accessing the image_size property forces the image
        # to load fully???
        _wat = ip.image_size[0] + ip.image_size[1]

    return thumbs[name].icon_id

# https://docs.blender.org/manual/en/dev/advanced/extensions/python_wheels.html
def _init(self, context):
    """
    Configure global things - gets called once on startup and then again
    whenever the preferences are changed.
    """
    global rsi
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
        rsi.clear_cache()
        return {'FINISHED'}

class RSIBrowserPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    debug: bpy.props.BoolProperty(name="Debug", default=False, update=_init)  # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "debug")
        layout.operator(RSIClearCacheOperator.bl_idname, icon="CONSOLE")

class RSIImportOperator(bpy.types.Operator):
    """
    Fetch a 3D model from RSI and import it into the scene.
    """

    bl_idname = "rsi.import"
    bl_label = "Import a ship"

    name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context) -> t.Set[str]:
        if not bpy.app.online_access:
            self.report({"ERROR"}, "RSI Browser requires online access")
            return {"CANCELLED"}

        try:
                si = rsi.get_si(self.name)
                mesh = bpy.data.meshes.new(self.name)
                bm = bmesh.new()
                rsi.get_model(self.name)
                # ctm = import_mesh()

                # for vertex in ctm['vertices']:
                #     bm.verts.new(vertex)

                # bm.verts.ensure_lookup_table()
                # hashes = []
                # for face in ctm['faces']:
                #     vert_hash = hash(f"{bm.verts[0]} {bm.verts[1]} {bm.verts[2]}")
                #     if vert_hash not in hashes:
                #         bm.faces.new([bm.verts[i] for i in face])
                #         hashes.append(vert_hash)

                bm.from_mesh(mesh)
                bm.free()

                obj = bpy.data.objects.new(self.name, mesh)
                bpy.context.scene.collection.objects.link(obj)

                assert isinstance(obj, bpy.types.Object)
                obj["rsiName"] = self.name
                obj.name = si["name"]
                if not obj.parent:
                    obj.location = bpy.context.scene.cursor.location
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
            icon = _get_thumbnail_icon(result["name"], result["thumbnail"])
            box.template_icon(icon_value=icon, scale=10)
            btn = box.operator(RSIImportOperator.bl_idname, text="Import")
            btn.name = result["name"]


_last_name = None
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
        return context.object and context.object.get("rsiName")

    def draw(self, context) -> None:
        global _last_si, _last_name

        layout = self.layout
        name = context.object.get("rsiName")

        row = layout.row()
        row.label(text="Name")
        row.label(text=name)

        if not bpy.app.online_access:
            layout.label(text="Enable online access to see more details")
            return

        if name == _last_name:
            si = _last_si
        else:
            si = rsi.get_si(name)
            _last_name = name
            _last_si = si

        icon = _get_thumbnail_icon(name, si["media"]["thumbnail"]["storeSmall"])
        layout.template_icon(icon_value=icon, scale=10)

        grid = layout.grid_flow(row_major=True, even_rows=False, columns=2)
        grid.label(text="Manufacturer")
        grid.label(text=si["manufacturer"]["name"])
        grid.label(text="Type")
        grid.label(text=si["type"])
        grid.label(text="Focus")
        grid.label(text=si["focus"])
        grid.label(text="Crew")
        grid.label(text=f'{si["minCrew"]} - {si["maxCrew"]}')

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

def import_mesh(_filename) -> t.Dict[str, t.List]:
    ctm_context = ctmNewContext(CTM_IMPORT)
    vertices_ = []
    faces_ = []
    normals_ = []
    colors_ = []
    texture_ = []

    try:
        ctmLoad(ctm_context, _filename.encode("utf-8"))
        err = ctmGetError(ctm_context)
        if err != CTM_NONE:
            raise IOError("Error loading file: %s" % str(ctmErrorString(err)))

        # read vertices
        vertex_count = ctmGetInteger(ctm_context, CTM_VERTEX_COUNT)
        vertex_ctm = ctmGetFloatArray(ctm_context, CTM_VERTICES)

        for i in range(vertex_count):
            vertices_.append((vertex_ctm[i * 3], vertex_ctm[i * 3 + 1], vertex_ctm[i * 3 + 2]))

        # read faces
        face_count = ctmGetInteger(ctm_context, CTM_TRIANGLE_COUNT)
        face_ctm = ctmGetIntegerArray(ctm_context, CTM_INDICES)

        for i in range(face_count):
            faces_.append((face_ctm[i * 3], face_ctm[i * 3 + 1], face_ctm[i * 3 + 2]))

        if ctmGetInteger(ctm_context, CTM_HAS_NORMALS) == CTM_TRUE:
            normals_ctm = ctmGetFloatArray(ctm_context, CTM_NORMALS)
            for i in range(vertex_count):
                normals_.append((normals_ctm[i * 3], normals_ctm[i * 3 + 1], normals_ctm[i * 3 + 2]))

        tex_count = ctmGetInteger(ctm_context,  CTM_UV_MAP_COUNT)
        if tex_count > 0:
            texture_ = ctmGetFloatArray(ctm_context, CTM_UV_MAP_1)


        color_map = ctmGetNamedAttribMap(ctm_context, 'Color'.encode("utf-8"))
        if color_map != 0:
            colors_ = ctmGetFloatArray(ctm_context, color_map)

    except Exception as e:
        log.exception(f"Something went wrong when trying to import model file {e}")
    finally:
        ctmFreeContext(ctm_context)

    return { "vertices": vertices_, "faces": faces_, "normals": normals_, "colors": colors_, "uv": texture_ }