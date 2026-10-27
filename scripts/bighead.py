# -*- coding: utf-8 -*-
"""大头照片剪纸：全身照（白底）→ 抠图 → 找脸 → 头按下巴放大 → 透明 PNG + 锚点 json。

  python bighead.py 全身照.png 输出.png [--scale 1.8] [--model isnet-general-use] [--gray]

锚点 json（同名 .json）：feet（双脚中点）、head（脸中心）、chin（下巴），都是输出图的像素坐标，排版时按它对齐。
做法：rembg 抠出人；YuNet 找脸；下巴以上整块头放大 scale 倍（两侧留人形自己的轮廓，下巴底边是一条 U 形弧），下巴压过领口一点，盖住原来的脖子，衣领上加一层淡淡的接触阴影。
正脸最好：侧脸时下颌线是猜的。做完放在对比色底上，按镜头推得最近时的大小看接缝。
要 tools/face_yunet.onnx（opencv_zoo 的 face_detection_yunet_2023mar.onnx）。
"""
import sys, json, argparse
from pathlib import Path
import numpy as np, cv2
from PIL import Image, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('out')
ap.add_argument('--scale', type=float, default=2.2)
ap.add_argument('--model', default='isnet-general-use')
ap.add_argument('--gray', action='store_true', help='同时出一张黑白版 <名>_gray.png')
a = ap.parse_args()

from rembg import new_session, remove
im = Image.open(a.src).convert('RGB')
cut = remove(im, session=new_session(a.model))           # RGBA
arr = np.array(cut); alpha = arr[..., 3]
ys, xs = np.where(alpha > 128)
top, bot, left, right = ys.min(), ys.max(), xs.min(), xs.max()

# 找脸（YuNet，模型和本脚本放一起）；下巴 = 脸框下沿；领口 = 下巴往下、人形宽到 1.6 倍脸宽的那一行
fd = cv2.FaceDetectorYN.create(str(Path(__file__).with_name('face_yunet.onnx')), '', im.size, .6)
_, F = fd.detect(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
if F is None: sys.exit('没找到脸：换一张正面、脸露全的全身照')
fx, fy, fw, fh = [float(v) for v in max(F, key=lambda f: f[2] * f[3])[:4]]
cx = fx + fw / 2; chin = fy + fh * 1.06
collar = int(chin)
while collar < bot and (alpha[collar] > 128).sum() < fw * 1.6: collar += 1
# 头的左右范围按眼睛那一行的人形轮廓量（侧脸时后脑勺、耳朵在脸框外面，按脸框居中会被横着切掉）
row = alpha[int(fy + fh * .45)] > 128; hl = hr = int(cx)
while hl > 0 and row[hl - 1]: hl -= 1
while hr < len(row) - 1 and row[hr + 1]: hr += 1
x0 = int(max(0, min(cx - fw * 1.35, hl - 12))); x1 = int(min(arr.shape[1], max(cx + fw * 1.35, hr + 12)))
y0 = int(top); y1 = int(chin + fh * .04)
head = cut.crop((x0, y0, x1, y1))
# 下巴的底边：两侧保留人形自己的轮廓（腮帮、耳朵、后脑），只在脖子那一段用一条 U 形弧切出下巴。
# 以前整个下半张脸用椭圆修形：腮帮变成光滑的蛋形，侧脸时还对不上，放大后像"气球插在杆上"（对临 v1 用户："头和身体融合的很不好"）
m = np.array(head.split()[3]).astype(np.float32)
yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]].astype(np.float32)
# 两侧：按眼睛那一行量到的头宽，用一个偏方的超椭圆（p=3）往下收——比椭圆饱满，腮帮不会变成蛋形，又能把领子、肩膀挡在外面
ex, ey0 = (hl + hr) / 2 - x0, fy + fh * .45 - y0; rx, ry = (hr - hl) / 2 * 1.05, (chin - y0) - ey0 + fh * .04
side = np.clip(np.abs((xx - ex) / rx) ** 3 + np.clip((yy - ey0) / ry, 0, None) ** 3, 0, None)
m = m * np.clip((1.0 - side) / .06, 0, 1)
# 下巴附近那一条带里只留肤色：下颌线贴着衬衫、西装领，那条边本来就是"肤色 / 不是肤色"的分界。黑白照片（脸没有颜色）跳过
lab = cv2.cvtColor(np.array(head.convert('RGB')), cv2.COLOR_RGB2LAB).astype(np.float32)
fr = lab[int(fy + fh * .55 - y0):int(fy + fh * .8 - y0), int(fx + fw * .25 - x0):int(fx + fw * .75 - x0)].reshape(-1, 3)
a0, b0 = np.median(fr[:, 1]), np.median(fr[:, 2])
if abs(a0 - 128) + abs(b0 - 128) > 10:
    d = np.hypot(lab[..., 1] - a0, lab[..., 2] - b0)
    skin = cv2.GaussianBlur(cv2.morphologyEx((d < 14).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 1.2)
    band = np.clip((yy - ((chin - y0) - fh * .38)) / (fh * .06), 0, 1)   # 从下巴往上 0.38 个脸高开始生效
    m = m * (1 - band + band * np.clip(skin * 1.6, 0, 1))
# 底边：脖子那一段用 U 形弧切出下巴（弧心在下巴尖，两端抬到下颌角）
ux, uw = cx - x0, max(fw * .55, (hr - hl) * .3)
cut_y = (chin - y0) - fh * .22 * np.clip(((xx - ux) / uw) ** 2, 0, 1)
m = m * np.clip((cut_y - yy) / (fh * .015) + .5, 0, 1)     # 弧边轻羽化（放大后仍要像剪刀剪的边）
head.putalpha(Image.fromarray(m.astype(np.uint8)))
s = a.scale
hw, hh = head.size; big = head.resize((int(hw * s), int(hh * s)), Image.LANCZOS)
# 画布要能装下放大的头
pad_top = max(10, int(hh * s)); pad_x = int(hw * (s - 1) / 2) + 10
W = arr.shape[1] + 2 * pad_x; H = arr.shape[0] + pad_top
canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
canvas.alpha_composite(cut, (pad_x, pad_top))
land = collar + fh * .1                                    # 放大后的下巴压过领口一点，原来那截脖子被盖住，不露出"杆"
bx = int(pad_x + cx - big.size[0] * (cx - x0) / hw); by = int(pad_top + land - (chin - y0) * s)
# 接触阴影：头在衣领上投一层很淡的影子（只落在身体上），头和身体才像贴在一起
sh = Image.new('L', (W, H), 0); sh.paste(big.split()[3], (bx, by + int(fh * .05 * s)))
sh = sh.filter(ImageFilter.GaussianBlur(fh * .07 * s))
body_a = Image.new('L', (W, H), 0); body_a.paste(cut.split()[3], (pad_x, pad_top))
sh = Image.fromarray((np.array(sh).astype(np.float32) * np.array(body_a).astype(np.float32) / 255 * .38).astype(np.uint8))
canvas.alpha_composite(Image.merge('RGBA', (Image.new('L', (W, H), 0),) * 3 + (sh,)))
canvas.alpha_composite(big, (bx, by))
bb = canvas.getbbox(); canvas = canvas.crop(bb)
ox, oy = bb[0], bb[1]
feet_y = bot + pad_top - oy
fx_feet = float(np.where(alpha[bot - 5] > 128)[0].mean()) + pad_x - ox
anch = {'feet': [round(fx_feet), int(feet_y)], 'head': [round(pad_x + cx - ox), round(by + (fy + fh * .45 - y0) * s - oy)],
        'chin': [round(pad_x + cx - ox), int(pad_top + land - oy)], 'size': list(canvas.size), 'scale': s}
canvas.save(a.out)
Path(a.out).with_suffix('.json').write_text(json.dumps(anch), 'utf-8')
if a.gray:
    r, g2, b, al = canvas.split(); gr = Image.merge('RGB', (r, g2, b)).convert('L')
    gr = Image.merge('RGBA', (gr, gr, gr, al)); gr.save(str(Path(a.out).with_name(Path(a.out).stem + '_gray.png')))
print(a.out, canvas.size, '脸', (int(fx), int(fy), int(fw), int(fh)), '锚点', anch)
