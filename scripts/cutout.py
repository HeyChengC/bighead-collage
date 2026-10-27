# -*- coding: utf-8 -*-
"""白底生图 → 实心透明 PNG（道具、手、钞票、黑板）。
  python cutout.py 输入.png 输出.png [--w 最大宽] [--white] [--anchor]
默认：rembg 出轮廓 → 填洞 → 颜色取回原图（rembg 会把浅色纸面当成半透明、把透明处颜色清零，
      钞票、白纸、白键盘直接用会透出底下的东西，填洞后又会是黑块）。
--white：不用 rembg，按"不是白的就是物件"抠（黑板、深色物件 rembg 常把物件本身当背景）。
--anchor：抠的是站着的人（直接生成的大头全身像）时用，同时写同名 .json：feet（两只鞋最低处的中点）、size、top，scene.js 的 person() 按它让脚踩地。"""
import argparse
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('out'); ap.add_argument('--w', type=int, default=0); ap.add_argument('--white', action='store_true'); ap.add_argument('--anchor', action='store_true')
a = ap.parse_args()
src = Image.open(a.src).convert('RGB')
if a.white:
    m = (255 * 3 - np.array(src).astype(int).sum(2)) > 45
    m = ndimage.binary_opening(m, iterations=2); lab, k = ndimage.label(m); sizes = ndimage.sum(m, lab, range(1, k + 1))
    m = np.isin(lab, 1 + np.where(sizes > sizes.max() * .02)[0])
else:
    from rembg import remove, new_session
    m = np.array(remove(src, session=new_session('isnet-general-use')))[..., 3] > 40
m = ndimage.binary_erosion(ndimage.binary_fill_holes(m), iterations=1)
im = src.convert('RGBA'); im.putalpha(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1)))
im = im.crop(im.getbbox())
if a.w and im.width > a.w: im = im.resize((a.w, round(im.height * a.w / im.width)), Image.LANCZOS)
im.save(a.out); print(a.out, im.size)
if a.anchor:
    import json
    from pathlib import Path
    al = np.array(im)[..., 3] > 128; ys, xs = np.where(al); top, bot = int(ys.min()), int(ys.max())
    band = np.where(al[bot - int((bot - top) * .03): bot + 1].any(0))[0]          # 最下面 3% 高度里的鞋
    anch = {'feet': [int((band.min() + band.max()) / 2), bot], 'size': list(im.size), 'top': top}
    Path(a.out).with_suffix('.json').write_text(json.dumps(anch), 'utf-8'); print(anch)
