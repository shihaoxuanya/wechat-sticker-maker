"""Color-safe, explicit image finishing. No illustration generation or OCR claims."""
from __future__ import annotations

from collections import deque
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

LANCZOS = Image.Resampling.LANCZOS


def resize_rgba(image, size):
    out = image.convert('RGBa').resize(tuple(size), LANCZOS).convert('RGBA')
    a = np.asarray(out).copy()
    a[a[:, :, 3] < 4] = 0
    return Image.fromarray(a)


def connected_screen(mask):
    """Scanline flood fill from the image border; enclosed colors survive."""
    remaining = np.pad(mask.astype(bool), 1, constant_values=True)
    found = np.zeros_like(remaining)
    todo = [(0, 0)]
    height, width = remaining.shape
    while todo:
        y, x = todo.pop()
        if not remaining[y, x]:
            continue
        stops = np.flatnonzero(~remaining[y, :x])
        left = int(stops[-1]+1) if len(stops) else 0
        stops = np.flatnonzero(~remaining[y, x:])
        right = int(x+stops[0]) if len(stops) else width
        remaining[y, left:right] = False
        found[y, left:right] = True
        for ny in (y-1, y+1):
            if 0 <= ny < height:
                row = remaining[ny, left:right]
                starts = np.flatnonzero(row & ~np.r_[False, row[:-1]])
                todo.extend((ny, left+int(k)) for k in starts)
    return found[1:-1, 1:-1]


def mask_file(path, size):
    with Image.open(path) as im:
        if im.size != size:
            raise ValueError('Protection/removal mask must match source dimensions')
        return np.asarray(im.convert('L')) >= 128


def alpha_cutout(image, background, root):
    image = ImageOps.exif_transpose(image)
    rgba = image.convert('RGBA')
    alpha = np.asarray(rgba)[:, :, 3]
    mode = background.get('mode', 'native')
    if mode == 'native':
        if alpha.min() == 255:
            raise ValueError('alpha_missing: source is opaque; painted checkerboard is not transparency')
        if alpha.max() == 0:
            raise ValueError('empty_image: source has no visible content')
        return rgba, {'alpha_method': 'native', 'edge_review_required': True}
    if mode != 'chroma' or not background.get('screen_confirmed', False):
        raise ValueError('chroma requires explicit screen_confirmed after visual inspection')
    key = np.asarray(background.get('key_rgb', []), dtype=np.float32)
    if key.shape != (3,) or key.min() < 0 or key.max() > 255:
        raise ValueError('key_rgb must contain 3 channel values in 0..255')
    rgb = np.asarray(rgba, dtype=np.float32)[:, :, :3]
    protect = np.zeros(alpha.shape, dtype=bool)
    remove = np.zeros(alpha.shape, dtype=bool)
    for field, target in [('protect_mask', protect), ('remove_mask', remove)]:
        if background.get(field):
            target[:] = mask_file(root/background[field], image.size)
    if (protect & remove).any():
        raise ValueError('Protection and removal masks overlap')
    tolerance = float(background.get('tolerance', 28))
    if not 0 < tolerance <= 65:
        raise ValueError('Chroma tolerance must be in 0..65')
    candidate = (np.max(abs(rgb-key), axis=2) <= tolerance) & ~protect
    screen = connected_screen(candidate) | remove
    if screen.mean() < .005:
        raise ValueError('No connected chroma background found; do not erase arbitrary colors')
    band = np.asarray(Image.fromarray((screen*255).astype('uint8')).filter(ImageFilter.MaxFilter(7))) > 0
    # Estimate chroma mixing only in the narrow screen fringe. Interior colors,
    # including a key-colored eye/book, are never globally desaturated.
    hi = int(np.argmax(key)); lo = int(np.argmin(key))
    strength = float(key[hi]-key[lo])
    if strength < 80:
        raise ValueError('Use a saturated non-conflicting key or native alpha')
    chroma = np.clip((rgb[:, :, hi]-rgb[:, :, lo]-4)/(strength-4), 0, 1)
    a = np.ones(alpha.shape, dtype=np.float32)
    a[band & ~protect] = 1-chroma[band & ~protect]
    a[screen] = 0
    a[protect] = 1
    a *= alpha/255
    a[a < .025] = 0
    fg = np.clip((rgb-(1-a[:, :, None])*key)/np.maximum(a[:, :, None], .025), 0, 255)
    fg[protect] = rgb[protect]
    fg[a == 0] = 0
    out = Image.fromarray(np.dstack((fg, a*255)).astype('uint8'))
    if out.getchannel('A').getbbox() is None:
        raise ValueError('Extraction removed all artwork')
    return out, {'alpha_method': 'connected-chroma-with-edge-band', 'screen_fraction': round(float(screen.mean()), 4), 'enclosed_key_pixels_retained': int((candidate & ~screen).sum()), 'edge_review_required': True}


def fit_transparent(image, size, margin):
    size = tuple(size)
    if margin < 1 or min(size) <= margin*2:
        raise ValueError('Transparent outputs need a positive safe margin')
    box = image.getchannel('A').getbbox()
    if not box:
        raise ValueError('Empty image')
    crop = image.crop(box)
    factor = min((size[0]-2*margin)/crop.width, (size[1]-2*margin)/crop.height)
    dims = tuple(max(1, round(n*factor)) for n in crop.size)
    art = resize_rgba(crop, dims)
    out = Image.new('RGBA', size)
    out.alpha_composite(art, ((size[0]-dims[0])//2, (size[1]-dims[1])//2))
    return out


def png_bytes(image):
    buf = BytesIO(); image.save(buf, 'PNG', optimize=True, compress_level=9)
    return buf.getvalue()


def encode(image, path, fmt, budget=None):
    """Lossless first; highest candidate quality that meets an explicit budget."""
    fmt = fmt.upper(); path.parent.mkdir(parents=True, exist_ok=True)
    changes = []
    if fmt == 'PNG':
        data = png_bytes(image)
        if budget and len(data) > budget:
            for colors in (256, 192, 128, 96, 64):
                reduced = image.convert('RGBA').quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
                data2 = png_bytes(reduced)
                if len(data2) <= budget:
                    data = data2; changes.append(f'palette-{colors}: visual recheck required'); break
    elif fmt in ('JPEG', 'JPG'):
        rgb = image.convert('RGB'); data = None
        for quality in range(100, 59, -1):
            buf = BytesIO(); rgb.save(buf, 'JPEG', quality=quality, subsampling=0, optimize=True)
            data = buf.getvalue()
            if not budget or len(data) <= budget:
                changes.append(f'JPEG-quality-{quality}'); break
    elif fmt == 'GIF':
        rgba = image.convert('RGBA'); rgb = Image.new('RGB', image.size, 'white'); rgb.paste(rgba, mask=rgba.getchannel('A'))
        q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        arr = np.asarray(q).copy(); arr[np.asarray(rgba)[:, :, 3] < 128] = 255
        g = Image.fromarray(arr, 'P'); palette=q.getpalette(); g.putpalette((palette+[255]*768)[:765]+[0,0,0])
        buf=BytesIO();g.save(buf,'GIF',transparency=255,optimize=False,disposal=2)
        data=buf.getvalue();changes.append('single-frame-GIF: binary-alpha and palette need visual recheck')
    else:
        raise ValueError(f'Unsupported export format: {fmt}')
    if budget and len(data) > budget:
        raise ValueError(f'byte_budget: cannot meet {budget} bytes at the configured quality floor; revise art or verified targets')
    path.write_bytes(data)
    return {'encoding': fmt, 'bytes':len(data),'processing_notes':changes}


def metrics(path):
    with Image.open(path) as im:
        im.load(); fmt=im.format;frames=getattr(im,'n_frames',1);mode=im.mode
        a=np.asarray(im.convert('RGBA')); alpha=a[:, :, 3]
        box=im.convert('RGBA').getchannel('A').getbbox()
        return {'format':fmt,'size':list(im.size),'mode':mode,'frames':frames,'bytes':path.stat().st_size,
                'has_transparency':bool((alpha<255).any()),'visible_pixels':int((alpha>0).sum()),
                'bbox':list(box) if box else None,'edge_alpha_max':int(max(alpha[0].max(),alpha[-1].max(),alpha[:,0].max(),alpha[:,-1].max())),
                'content_extent':round(max((box[2]-box[0])/im.width,(box[3]-box[1])/im.height),4) if box else 0}
