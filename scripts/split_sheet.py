# 一张白底图里摆了几件道具 → 抠图 → 按连通区域切成单件（从左到右、从上到下编号）
#   python tools/split_sheet.py gen/sheet.png img/a.png img/b.png img/c.png [--white]
import sys, numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
args = [a for a in sys.argv[1:] if not a.startswith('--')]; src, outs = args[0], args[1:]
im = Image.open(src).convert('RGB')
if '--white' in sys.argv: m = (255 * 3 - np.array(im).astype(int).sum(2)) > 45
else:
    from rembg import remove, new_session
    m = np.array(remove(im, session=new_session('isnet-general-use')))[..., 3] > 40
m = ndimage.binary_fill_holes(ndimage.binary_opening(m, iterations=2))
lab, k = ndimage.label(ndimage.binary_dilation(m, iterations=12)); sizes = ndimage.sum(m, lab, range(1, k + 1))
keep = [i + 1 for i in np.argsort(-sizes)[:len(outs)]]
boxes = [(ndimage.find_objects((lab == i).astype(int))[0], i) for i in keep]
boxes.sort(key=lambda b: (round(b[0][0].start / (im.height / 3)), b[0][1].start))
for (sl, i), out in zip(boxes, outs):
    mm = ndimage.binary_erosion(m & (lab == i), iterations=1)
    rgba = im.convert('RGBA'); rgba.putalpha(Image.fromarray((mm * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1)))
    c = rgba.crop(rgba.getbbox()); c.save(out); print(out, c.size)
