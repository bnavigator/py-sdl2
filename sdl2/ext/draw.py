"""Drawing routines for software surfaces."""
import ctypes
from .compat import isiterable, UnsupportedError
from .array import to_ctypes
from .color import convert_to_color
from .. import surface, pixels, rect
from .algorithms import clipline
from .sprite import SoftwareSprite

__all__ = ["prepare_color", "fill", "line"]


def _get_target_surface(target):
    """Gets the SDL_surface from the passed target."""
    if isinstance(target, surface.SDL_Surface):
        rtarget = target
    elif isinstance(target, SoftwareSprite):
        rtarget = target.surface
    elif "SDL_Surface" in str(type(target)):
        rtarget = target.contents
    else:
        raise TypeError("unsupported target type")
    return rtarget


def prepare_color(color, target):
    """Prepares the passed color for the passed target."""
    color = convert_to_color(color)
    pformat = None
    # Software surfaces
    if isinstance(target, pixels.SDL_PixelFormat):
        pformat = target
    elif isinstance(target, surface.SDL_Surface):
        pformat = target.format.contents
    elif isinstance(target, SoftwareSprite):
        pformat = target.surface.format.contents
    if pformat is None:
        raise TypeError("unsupported target type")
    if pformat.Amask != 0:
        # Target has an alpha mask
        return pixels.SDL_MapRGBA(pformat, color.r, color.g, color.b, color.a)
    return pixels.SDL_MapRGB(pformat, color.r, color.g, color.b)


def fill(target, color, area=None):
    """Fills a certain rectangular area on the passed target with a color.

    Targets can be :obj:`~sdl2.surface.SDL_Surface` or 
    :obj:`~sdl2.ext.sprite.SoftwareSprite` objects. Fill areas can be specified
    as 4-item (x, y, w, h) tuples, :obj:`~sdl2.rect.SDL_Rect` objects, or a list
    containing multiple areas to fill in either format. If no area is provided,
    the entire target will be filled with the passed color.

    The fill color can be provided in any format supported by
    :func:`~sdl2.ext.color.convert_to_color`.

    Args:
        target: The target surface or sprite to modify.
        color: The color to add to the specified region of the target.
        area (optional): The rectangular region (or regions) of the target to
            fill with the given colour. If no region is specified, the whole
            surface of the target will be filled.

    """
    color = prepare_color(color, target)
    rtarget = _get_target_surface(target)

    err_msg = (
        "Fill areas must be specified as either (x, y, w, h) tuples or "
        "SDL_Rect objects (Got unsupported format '{0}')"
    )

    rects = []
    if area:
        if not isiterable(area) or not isiterable(area[0]):
            area = [area]
        for r in area:
            if isinstance(r, rect.SDL_Rect):
                rects.append(r)
            else:
                try:
                    new_rect = rect.SDL_Rect(
                        int(r[0]), int(r[1]), int(r[2]), int(r[3])
                    )
                    rects.append(new_rect)
                except (TypeError, ValueError, IndexError):
                    raise ValueError(err_msg.format(str(r)))

    if len(rects) > 2:
        rects, count = to_ctypes(rects, rect.SDL_Rect)
        rects = ctypes.cast(rects, ctypes.POINTER(rect.SDL_Rect))
        surface.SDL_FillRects(rtarget, rects, count, color)
    elif len(rects) == 1:
        surface.SDL_FillRect(rtarget, rects[0], color)
    else:
        surface.SDL_FillRect(rtarget, None, color)


def line(target, color, dline, width=1):
    """Draws one or multiple lines on the passed target.

    dline can be a sequence of four integers for a single line in the
    form (x1, y1, x2, y2) or a sequence of a multiple of 4 for drawing
    multiple lines at once, e.g. (x1, y1, x2, y2, x3, y3, x4, y4, ...).
    """
    if width < 1:
        raise ValueError("width must be greater than 0")
    color = prepare_color(color, target)
    rtarget = _get_target_surface(target)

    # line: (x1, y1, x2, y2) OR (x1, y1, x2, y2, ...)
    if (len(dline) % 4) != 0:
        raise ValueError("line does not contain a valid set of points")
    pcount = len(dline)
    SDLRect = rect.SDL_Rect
    fillrect = surface.SDL_FillRect

    pitch = rtarget.pitch
    bpp = rtarget.format.contents.BytesPerPixel
    frac = pitch / bpp
    clip_rect = rtarget.clip_rect
    left, right = clip_rect.x, clip_rect.x + clip_rect.w - 1
    top, bottom = clip_rect.y, clip_rect.y + clip_rect.h - 1

    if bpp == 3:
        raise UnsupportedError(line, "24bpp are currently not supported")
    if bpp == 2:
        pxbuf = ctypes.cast(rtarget.pixels, ctypes.POINTER(ctypes.c_uint16))
    elif bpp == 4:
        pxbuf = ctypes.cast(rtarget.pixels, ctypes.POINTER(ctypes.c_uint32))
    else:
        pxbuf = rtarget.pixels  # byte-wise access.

    for idx in range(0, pcount, 4):
        x1, y1, x2, y2 = dline[idx:idx + 4]
        if x1 == x2:
            # Vertical line
            if y1 < y2:
                varea = SDLRect(x1 - width // 2, y1, width, y2 - y1)
            else:
                varea = SDLRect(x1 - width // 2, y2, width, y1 - y2)
            fillrect(rtarget, varea, color)
            continue
        if y1 == y2:
            # Horizontal line
            if x1 < x2:
                varea = SDLRect(x1, y1 - width // 2, x2 - x1, width)
            else:
                varea = SDLRect(x2, y1 - width // 2, x1 - x2, width)
            fillrect(rtarget, varea, color)
            continue
        if width != 1:
            raise UnsupportedError(line, "width > 1 is not supported")
        if width == 1:
            # Bresenham
            x1, y1, x2, y2 = clipline(left, top, right, bottom, x1, y1, x2, y2)
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            if x1 is None:
                # not to be drawn
                continue
            dx = abs(x2 - x1)
            dy = -abs(y2 - y1)
            err = dx + dy
            sx, sy = 1, 1
            if x1 > x2:
                sx = -sx
            if y1 > y2:
                sy = -sy
            while True:
                pxbuf[int(y1 * frac + x1)] = color
                if x1 == x2 and y1 == y2:
                    break
                e2 = err * 2
                if e2 > dy:
                    err += dy
                    x1 += sx
                if e2 < dx:
                    err += dx
                    y1 += sy
