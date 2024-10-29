import numpy as np
from .bindings import *

class CTM:
    """
    Object that encapsulates a CTM file
    """
    def __init__(self, _vertices, _faces):
        self.vertices = _vertices
        self.faces = _faces

    def __eq__(self, other):
        return (self.vertices == other.vertices).all() and (
            self.faces == other.faces).all()

    def flip_vertices_XY(self):
        # Flip Y and Z axes to convert from Three.js to Blender
        vertices_np = np.array(self.vertices, dtype=np.float32)
        self.vertices[:, [1, 2]] = vertices_np[:, [2, 1]] * np.array([-1, 1])


def import_mesh(_filename) -> CTM:
    ctm_context = ctmNewContext(CTM_IMPORT)
    try:
        ctmLoad(ctm_context, _encode(_filename))
        err = ctmGetError(ctm_context)
        if err != CTM_NONE:
            raise IOError("Error loading file: %s" % str(ctmErrorString(err)))

        # read vertices
        vertex_count = ctmGetInteger(ctm_context, CTM_VERTEX_COUNT)
        vertex_ctm = ctmGetFloatArray(ctm_context, CTM_VERTICES)

        vertices = np.fromiter(vertex_ctm,
                               dtype=float,
                               count=vertex_count * 3).reshape((-1, 3))

        # read faces
        face_count = ctmGetInteger(ctm_context, CTM_TRIANGLE_COUNT)
        face_ctm = ctmGetIntegerArray(ctm_context, CTM_INDICES)
        faces = np.fromiter(face_ctm, dtype=int,
                            count=face_count * 3).reshape((-1, 3))

    finally:
        ctmFreeContext(ctm_context)

    return CTM(vertices, faces)

def _encode(_filename):
    try:
        return str(_filename).encode("utf-8")
    except UnicodeEncodeError:
        pass

    try:
        # works fine for pathlib.Path
        return bytes(_filename)
    except TypeError:
        pass

    return str(_filename).encode("utf-8", "surrogateescape")