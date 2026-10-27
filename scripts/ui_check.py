# 平台界面遮挡自查：在成片（或静帧）上画出发布后会被界面盖住的区域，拼成一张接触表。
# 关键内容（字幕、关键词、数字、主角的脸、清单）不能落在红框里。
#   python ui_check.py final.mp4 ui_check.jpg                 # 每 4 秒一帧
#   python ui_check.py final.mp4 ui_check.jpg --every 2
#   python ui_check.py final.mp4 ui_check.jpg --at 1,9.8,16.5,47
#   python ui_check.py out/ ui_check.jpg                      # 用 out/still_*.png
# 区域按抖音 9:16（1080×1920）给的近似值，别的平台或尺寸改 ZONES；画面尺寸不同会按比例换算。
import glob, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw

ZONES = {                       # (x0, y0, x1, y1)，1080×1920 坐标
    "顶部标签栏": (0, 0, 1080, 160),
    "右侧按钮列": (940, 820, 1080, 1560),
    "底部账号/标题/音乐": (0, 1560, 900, 1800),
    "底部导航": (0, 1800, 1080, 1920),
}

def arg(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

def grab(src):
    if os.path.isdir(src):
        fs = glob.glob(os.path.join(src, "still_*.png"))
        return sorted(((float(re.findall(r"still_([\d.]+)\.png", f)[0]), f) for f in fs))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    ts = [float(x) for x in arg("--at").split(",")] if arg("--at") else [round(t * float(arg("--every", 4)) + .5, 2) for t in range(int(dur // float(arg("--every", 4))) + 1)]
    tmp = tempfile.mkdtemp(); out = []
    for t in ts:
        if t >= dur: continue
        f = os.path.join(tmp, f"{t:.2f}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", src, "-frames:v", "1", f], check=True); out.append((t, f))
    return out

def main():
    src, dst = sys.argv[1], sys.argv[2]
    frames = grab(src); tw, th, cols = 270, 480, 7
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), "black")
    for i, (t, f) in enumerate(frames):
        im = Image.open(f).convert("RGBA"); kx, ky = tw / 1080, th / 1920
        im = im.resize((tw, th)); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for x0, y0, x1, y1 in ZONES.values():
            d.rectangle([x0 * kx, y0 * ky, x1 * kx, y1 * ky], fill=(255, 0, 0, 55), outline=(255, 0, 0, 220))
        im = Image.alpha_composite(im, ov); ImageDraw.Draw(im).text((4, 4), f"{t:.1f}s", fill="yellow")
        sheet.paste(im.convert("RGB"), ((i % cols) * tw, (i // cols) * th))
    sheet.save(dst, quality=88); print(dst, len(frames), "帧；红框里不能有字幕、关键词、数字、主角的脸")

if __name__ == "__main__":
    main()
