# -*- coding: utf-8 -*-
"""vsr —— 拆参考视频用的取证工具（video-style-learn）。在一个空的工作目录里运行；
所有产物落在 src/ frames/ audio/ data/ sheets/。

  python vsr.py ingest <视频文件> <代号>            入库：体检 + 每秒一帧 + 抽音轨 + 全片概览
  python vsr.py sheet  <代号> <起> <止> <步长秒>     某一段的拼图
  python vsr.py grid   <代号> <名字> t1 t2 …         指定时刻的原尺寸拼图；--crop x0,y0,x1,y1
  python vsr.py strip  <代号> <起> <止> <张数>        连续帧条（原尺寸裁切），每格标秒数
  python vsr.py motion <代号>                       硬切、闪、抖动、暗场、静止占比
  python vsr.py scenes <代号>                       换场（不管硬切还是动画转场）：场数、一场多长
  python vsr.py texture <代号>                      平涂占比：扁平矢量/纯色 vs 照片/纸纹（量材质，不量节奏）
  python vsr.py camcurve <代号>                     镜头速度曲线：一场里停几次、换场时镜头还动不动（先跑 flow、scenes）
  python vsr.py flow   <代号>                       镜头运动：静止、运动、前后层、推拉比、一镜时长
  python vsr.py audio  <代号>                       响度、速度、起音、静音段 + 频谱图
  python vsr.py sep    <代号>                       分出人声 / 鼓 / 贝斯 / 其他（demucs）→ sep/
  python vsr.py asr    <代号>                       语音识别 → data/<代号>.asr.txt + 词级时间 words.json（跑过 sep 就用干净人声）
  python vsr.py sync   <代号> [--events …]          画面事件卡的是字还是拍子：离词头、离八分音符各差多少
  python vsr.py ocr    <代号>                       每秒一帧 OCR → data/<代号>.ocr.jsonl（慢）
  python vsr.py subs   <代号>                       从 OCR 重建字幕轨 + 节奏统计
  python vsr.py labels <代号>                       字幕以外的屏上文字，按时间窗
  python vsr.py palette <代号>                      底色随时间的变化 + 亮色聚类
  python vsr.py color  <代号> <时刻> x0,y0,x1,y1 [bright|sat|dark|median]
  python vsr.py compare <代号> <复刻.mp4 或 静帧目录> <输出.png> t1 t2 …  同一时刻并排
  python vsr.py pair   <代号> <起> <止> <我们.mp4|id:代号> <起> <止> <名字> "<差在哪>"   近失对 → pairs/<名字>.jpg
  python vsr.py tstrip <代号> <复刻.mp4> <输出.jpg> 起-止[,起-止…] [--step .05]   对临：换场前后逐帧，参考在上、复刻在下
  python vsr.py xcorr  <代号> <复刻.mp4> [--win 3]    对临：逐帧画面变化做互相关 → 整体偏移 + 每段偏移（时间对没对齐）
  python vsr.py blind  <片段目录> <输出.mp4>          打乱顺序、去标识、统一编码，做盲看
  python vsr.py ranges <代号…> --metrics flow,subs,audio,motion   几条片的同一指标区间
  python vsr.py dossier <代号…>                     一页数字：每个代号的规格与全部指标

依赖：ffmpeg / ffprobe；pip install numpy opencv-python pillow；
     audio 要 librosa；asr 要 faster-whisper；ocr 要 rapidocr-onnxruntime。
坐标一律用视频自己的像素；换算到制作尺寸时乘比例（ingest 会给出提示）。
"""
import argparse, io, json, math, os, re, shutil, subprocess, sys
from pathlib import Path

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def src(vid): return f"src/{vid}.mp4"
def meta(vid): return json.load(open(f"data/{vid}.meta.json", encoding="utf-8"))
def grab(path, t):
    from PIL import Image
    o = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", path, "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not o: raise SystemExit(f"取帧失败：{path} @ {t}")
    return Image.open(io.BytesIO(o)).convert("RGB")
def font(size):
    from PIL import ImageFont
    for p in ("C:/Windows/Fonts/consolab.ttf", "/System/Library/Fonts/Menlo.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return ImageFont.load_default()
def tile_sheet(items, cols, tw, out, labels):
    from PIL import Image, ImageDraw
    w, h = items[0].size; th = round(tw * h / w); rows = math.ceil(len(items) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20)); d = ImageDraw.Draw(sheet); f = font(max(13, tw // 28))
    for i, (im, lab) in enumerate(zip(items, labels)):
        x, y = (i % cols) * tw, (i // cols) * th; sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        bb = d.textbbox((0, 0), lab, font=f); d.rectangle([x, y, x + bb[2] + 10, y + bb[3] + 8], fill=(0, 0, 0))
        d.text((x + 5, y + 2), lab, font=f, fill=(255, 230, 0)); d.rectangle([x, y, x + tw - 1, y + th - 1], outline=(60, 60, 60))
    Path(out).parent.mkdir(parents=True, exist_ok=True); sheet.save(out, quality=88); print(out, sheet.size, len(items))
def mmss(t): return f"{int(t) // 60}:{int(t) % 60:02d}"

# ---------------------------------------------------------------- ingest
def cmd_ingest(a):
    vid = a.id
    if Path("frames").exists():                           # Windows 不分大小写：a 和 A 是同一个目录，会互相覆盖
        clash = [d.name for d in Path("frames").iterdir() if d.name.lower() == vid.lower() and d.name != vid]
        if clash: raise SystemExit(f"代号 {vid} 和已有的 {clash[0]} 只差大小写，在 Windows 上会写进同一个目录。换一个代号（v1、v2…）")
    for d in ("src", f"frames/{vid}", "data", "sheets", "audio"): Path(d).mkdir(parents=True, exist_ok=True)
    if not Path(src(vid)).exists(): shutil.copy2(a.video, src(vid))
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", src(vid)],
                                  capture_output=True, text=True).stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video"); au = [s for s in j["streams"] if s["codec_type"] == "audio"]
    num, den = v["avg_frame_rate"].split("/"); fps = round(int(num) / int(den), 3)
    m = dict(id=vid, file=str(a.video), width=v["width"], height=v["height"], fps=fps,
             duration=round(float(j["format"]["duration"]), 3), frames=int(v.get("nb_frames", 0)),
             bitrate=int(j["format"].get("bit_rate", 0)), vcodec=v["codec_name"],
             audio=(dict(codec=au[0]["codec_name"], rate=int(au[0]["sample_rate"]), channels=au[0]["channels"]) if au else None))
    json.dump(m, open(f"data/{vid}.meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{vid}: {m['width']}×{m['height']}  {fps}fps  {m['duration']}s  {m['frames']} 帧  {m['bitrate'] // 1000} kbps  音轨 {m['audio']}")
    kbps_px = m["bitrate"] / (m["width"] * m["height"])
    if m["width"] < 1280 or kbps_px < 0.6:
        print("  注意：这是压过的下载版，细线和小字会糊；量颜色取核心像素，量尺寸按比例换算到制作尺寸")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src(vid), "-vf", "fps=1", "-q:v", "3", f"frames/{vid}/s%04d.jpg"], check=True)
    if au:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src(vid), "-vn", "-ac", "1", "-ar", "16000", f"audio/{vid}.wav"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src(vid), "-vn", "-ac", "2", "-ar", "44100", f"audio/{vid}_st.wav"], check=True)
    # 全片概览控制在 12 张以内；短片（< 40s）一秒一格太粗，改半秒一格
    step = 0.5 if m["duration"] < 40 else max(1, math.ceil(m["duration"] / (12 * 16)))
    n = 0; t = 0; last = max(0, m["duration"] - min(1, step))
    while t <= last:
        _sheet(vid, t, min(t + step * 15, last), step, 4, 480, f"sheets/{vid}_overview_{n:02d}.jpg"); t += step * 16; n += 1
    print(f"概览 {n} 张（步长 {step}s）。下一步：看概览 → 记下分段 → motion / flow / audio / asr → ocr（后台）")

# ---------------------------------------------------------------- sheets
def _sheet(vid, a0, b0, step, cols, tw, out):
    from PIL import Image
    ts = []; t = a0
    while t <= b0 + 1e-6: ts.append(round(t, 3)); t += step
    ims = []
    for t in ts:
        p = f"frames/{vid}/s{int(round(t)) + 1:04d}.jpg"
        ims.append(Image.open(p).convert("RGB") if step >= 1 and abs(t - round(t)) < 1e-6 and os.path.exists(p) else grab(src(vid), t))
    tile_sheet(ims, cols, tw, out, [mmss(t) if step >= 1 else f"{t:.2f}" for t in ts])
def cmd_sheet(a): _sheet(a.id, a.start, a.end, a.step, a.cols, a.tile, f"sheets/{a.id}_{a.start:g}-{a.end:g}_s{a.step:g}.jpg")
def cmd_grid(a):
    ims = [grab(src(a.id), t) for t in a.times]
    if a.crop: x0, y0, x1, y1 = [int(v) for v in a.crop.split(",")]; ims = [im.crop((x0, y0, x1, y1)) for im in ims]
    tile_sheet(ims, a.cols, a.tile, f"sheets/{a.id}_{a.name}.png", [f"{t:.2f}" for t in a.times])
def cmd_strip(a):
    """连续帧：起止之间取 n 张，保持原尺寸比例（可裁切），每格标秒数。"""
    import cv2, numpy as np
    cap = cv2.VideoCapture(src(a.id)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    ts = np.linspace(a.start, a.end, a.n); tiles = []
    crop = tuple(int(x) for x in a.crop.split(",")) if a.crop else None
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps))); ok, fr = cap.read()
        if not ok: fr = np.zeros((int(a.tile * 9 / 16), a.tile, 3), np.uint8)
        elif crop: x0, y0, x1, y1 = crop; fr = fr[y0:y1, x0:x1]
        fr = cv2.resize(fr, (a.tile, int(fr.shape[0] * a.tile / fr.shape[1])), interpolation=cv2.INTER_AREA)
        cv2.rectangle(fr, (0, 0), (92, 22), (0, 0, 0), -1)
        cv2.putText(fr, f"{t:.2f}", (4, 17), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA); tiles.append(fr)
    while len(tiles) % a.cols: tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + a.cols]) for i in range(0, len(tiles), a.cols)]
    out = f"sheets/{a.id}_strip_{a.start:g}-{a.end:g}.jpg"; cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90]); print(out)

# ---------------------------------------------------------------- motion
def cmd_motion(a):
    import cv2, numpy as np
    vid = a.id; cap = cv2.VideoCapture(src(vid)); fps = cap.get(cv2.CAP_PROP_FPS) or 30; prev = None; rows = []; thumbs = []; i = 0
    while True:
        ok, fr = cap.read()
        if not ok: break
        g = cv2.cvtColor(cv2.resize(fr, (256, 144), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = np.zeros_like(g) if prev is None else np.abs(g - prev)
        rows.append((i, i / fps, float(d.mean()), float(d[:26].mean()), float(d[26:112].mean()), float(d[112:].mean()), float(g.mean()), float((d > 24).mean()))); prev = g; i += 1
        thumbs.append(cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA))
    m = np.array(rows, dtype=np.float32)
    np.savetxt(f"data/{vid}.motion.csv", m, fmt="%.4f", delimiter=",", header="f,t,diff,diff_top,diff_mid,diff_bottom,luma,frac_changed", comments="")
    t, d, luma = m[:, 1], m[:, 2], m[:, 6]
    cuts = [k for k in range(3, len(d) - 4) if d[k] > 6 and d[k] > 3.5 * max(d[k - 1], d[k + 1], .3)]
    T = lambda k: round(float(t[k]), 2)
    is_flash = lambda k: luma[k] - luma[k - 2] > 12 and luma[min(len(luma) - 1, k + int(fps * .6))] < luma[k] - 8
    persists = lambda k: float(np.abs(thumbs[k + 3] - thumbs[k - 2]).mean()) > 3
    flashes = [T(k) for k in cuts if is_flash(k)]; hard = [T(k) for k in cuts if not is_flash(k) and persists(k)]
    jitter = [T(k) for k in cuts if not is_flash(k) and not persists(k)]
    thr = max(float(np.percentile(luma, 3)), 4.0); dips = []; st = None
    for k in range(len(luma)):
        if luma[k] < thr and st is None: st = t[k]
        if st is not None and (luma[k] >= thr or k == len(luma) - 1):
            if t[k] - st > .2: dips.append((round(float(st), 1), round(float(t[k]), 1)))
            st = None
    out = dict(fps=round(float(fps), 2), frames=len(d), still_pct=round(float(np.mean(d < .15)) * 100, 1),
               busy_pct=round(float(np.mean(d > 2)) * 100, 1), mean_diff=round(float(d.mean()), 2),
               hard_cuts=hard, flashes=flashes, jitter=jitter, dips=dips, cuts_per_min=round(len(hard) / (t[-1] / 60), 1) if len(t) else 0)
    json.dump(out, open(f"data/{vid}.motion.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print(f"{vid}: {len(d)} 帧 @ {fps:.2f}fps")
    print(f"  静止帧（差分<0.15）{out['still_pct']}%   忙帧（差分>2）{out['busy_pct']}%   平均差分 {out['mean_diff']}")
    print(f"  硬切 {len(hard)} 处（{out['cuts_per_min']}/分钟）：{hard[:60]}")
    print(f"  闪 {len(flashes)} 处：{flashes}")
    print(f"  抖动 / 闪烁（一两帧的跳变）{len(jitter)} 处：{jitter[:40]}")
    print(f"  暗场 {len(dips)} 处：{dips[:60]}")
    if hard: gaps = np.diff([0] + hard + [float(t[-1])]); print(f"  镜头长度 中位 {np.median(gaps):.1f}s  最短 {gaps.min():.1f}s  最长 {gaps.max():.1f}s")
    else: print("  没有硬切：镜头靠溶解 / 变形 / 推移来接，分段看暗场和概览图")
    print("  → data/{}.motion.json".format(vid))

# ---------------------------------------------------------------- scenes（换场，不管用什么转场）
def cmd_scenes(a):
    """按画面"是不是还在同一个地方"分段：比颜色分布，不比相邻两帧。
    硬切检测只认一帧之内的跳变；靠推进、遮罩、物件扫过来换场的片子，motion/flow 会数出很少的切点（实际换得很勤）。
    这里每秒取 10 帧，和"本场的参考色"比，连续 0.3 秒都不像了 = 换场；参考色随镜头慢慢漂（推拉、揭开不会被误切）。"""
    import cv2, numpy as np
    vid = a.id; step = 1 / a.fps
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src(vid), "-vf", f"fps={a.fps},scale=96:96,format=bgr24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    H = []
    while True:
        b = p.stdout.read(96 * 96 * 3)
        if len(b) < 96 * 96 * 3: break
        hsv = cv2.cvtColor(np.frombuffer(b, np.uint8).reshape(96, 96, 3), cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 6], [0, 180, 0, 256, 0, 256]).ravel(); H.append(h / max(h.sum(), 1))
    H = np.array(H, np.float32); n = len(H)
    dist = lambda x, y: float(cv2.compareHist(x, y, cv2.HISTCMP_BHATTACHARYYA))
    ref = H[0].copy(); over = 0; bounds = [0]; d = []
    for i in range(n):
        di = dist(H[i], ref); d.append(di)
        if di > a.thr: over += 1
        else: over = 0; ref = ref * (1 - a.drift) + H[i] * a.drift
        if over >= a.hold:
            s = i - a.hold + 1; bounds.append(s); over = 0
            ref = H[min(n - 1, i + 2)].copy()
    t = [round(b * step, 2) for b in bounds]; lens = np.diff(t + [round(n * step, 2)])
    out = dict(starts=t, lengths=[round(float(x), 2) for x in lens], n=len(t), median=round(float(np.median(lens)), 2),
               per_min=round(len(t) / (n * step / 60), 1), dist=[round(x, 3) for x in d])
    json.dump(out, open(f"data/{vid}.scenes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{vid}: {out['n']} 场（{out['per_min']}/分钟）  一场中位 {out['median']}s  最短 {lens.min():.2f}s  最长 {lens.max():.2f}s")
    print("  起点：", t)
    print("  读法：和 motion 的硬切数差很多 = 这个风格靠动画转场换场；对着概览图核一遍（同一底色的两场会被并成一场）")

# ---------------------------------------------------------------- texture（平涂 vs 有质感）
def cmd_texture(a):
    """平涂占比：每秒一帧，7×7 邻域里几乎没有明暗变化的像素占多少（先轻糊一下，单像素颗粒不算质感）。
    扁平矢量、纯色底、放射光底 → 高；照片、纸纹、灰泥墙、写实道具 → 低。
    用途：节奏指标（scenes/flow）量不出"画的是什么材质"；主导写的是"照片剪纸 / 实物"一类时，用它区分 X 和 Y。"""
    import cv2, numpy as np, glob
    fr = sorted(glob.glob(f"frames/{a.id}/s*.jpg"))
    if not fr: raise SystemExit("先 ingest")
    vals = []
    for f in fr:
        g = cv2.cvtColor(cv2.resize(cv2.imread(f), (270, 480) if meta(a.id)["height"] > meta(a.id)["width"] else (480, 270), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        g = cv2.GaussianBlur(g, (3, 3), 0); m = cv2.blur(g, (7, 7)); sd = np.sqrt(np.maximum(cv2.blur(g * g, (7, 7)) - m * m, 0))
        vals.append(float((sd < 2.0).mean()))
    v = np.array(vals); out = dict(flat=round(float(v.mean()), 3), flat_p90=round(float(np.percentile(v, 90)), 3), per_sec=[round(x, 3) for x in vals])
    json.dump(out, open(f"data/{a.id}.texture.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{a.id}: 平涂占比 平均 {out['flat']}  90 分位 {out['flat_p90']}（照片/纸纹类约 0.25–0.4；扁平矢量、纯色底 0.5 以上）")

# ---------------------------------------------------------------- camcurve（镜头速度曲线）
def cmd_camcurve(a):
    """镜头速度随时间的曲线：推拉（%/秒，推为正）和摇移（画面宽的 %/秒）。先跑 flow（和 scenes）。
    flow 的平均数（镜头在动占比、慢漂速度）看不出"动一下停一下"：每段动作都从零加速、到关键帧又减到零，平均数照样好看，看起来却像 PPT。
    中位数和"在动的占比"看不出形状：场内每秒推 5% 的微漂和每秒 40% 的大起伏，平均数可能差不多，看起来一个像 PPT、一个像运镜。
    这里量：推拉幅度（|推拉速度| 的 90 分位）、摇移幅度、推拉来回（方向反转、两边都超过 8%/s，次/分）、几乎不动的时间占比、换场前后 0.1s 的镜头速度。
    一定要看图：曲线是大起伏、平滑过零（运镜），还是平线加转场处的尖刺（PPT）。"""
    import cv2, numpy as np
    f = _load(a.id, "flow")
    if not f or "series" not in f: raise SystemExit("先跑 flow（新版会存逐帧序列）")
    S = f["series"]; fps = S["fps"]; z = np.array(S["zoom"]) * fps * 100; tx = np.array(S["tx"]); ty = np.array(S["ty"]); cut = np.array(S["cut"], bool)
    W = meta(a.id)["width"]; pan = np.hypot(tx, ty) / 6 * (320 / 320) * fps / 320 * 100   # 画面宽的 %/秒（flow 在 320 宽上算，tx 已乘 6）
    k = max(3, int(round(fps * .1)) | 1)
    med = lambda x: np.array([np.median(x[max(0, i - k // 2): i + k // 2 + 1]) for i in range(len(x))])
    z, pan = med(z), med(pan); z[cut] = 0; pan[cut] = 0
    sp = np.hypot(z, pan); n = len(sp); t = np.arange(n) / fps
    sc = _load(a.id, "scenes"); starts = (sc or {}).get("starts", [0.0]) + [n / fps]
    # 幅度：推拉速度的 90 分位（%/秒）；起伏：推拉方向反转、两边都超过 8%/s 的次数（次/分）——曲线运镜 = 幅度大、来回起伏
    big = np.where(np.abs(z) > 8, np.sign(z), 0); flips = 0; last = 0
    for v in big:
        if v and last and v != last: flips += 1
        if v: last = v
    mid = float(np.median(sp[sp > 0])) if (sp > 0).any() else 1
    bnd = [float(np.mean(sp[max(0, int(b * fps) - int(fps * .1)): int(b * fps) + int(fps * .1)])) for b in starts[1:-1]]
    still = float(np.mean(sp < 3))
    out = dict(zoom_p90=round(float(np.percentile(np.abs(z), 90)), 1), pan_p90=round(float(np.percentile(pan, 90)), 1),
               flips_per_min=round(flips / (n / fps / 60), 1), near_still=round(still, 2),
               speed_at_change=round(float(np.median(bnd)), 1) if bnd else None)
    f.update(camcurve=out); json.dump(f, open(f"data/{a.id}.flow.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    # 画图：上 推拉、下 摇移；竖线 = 换场
    Wd, Hh = 1600, 520; img = np.full((Hh, Wd, 3), 250, np.uint8); X = lambda tt: int(40 + (Wd - 60) * tt / max(t[-1], 1e-6))
    def plot(y, y0, h, lim, col, lab):
        cv2.line(img, (40, y0), (Wd - 20, y0), (180, 180, 180), 1)
        pts = [(X(tt), int(y0 - h / 2 * np.clip(v / lim, -1, 1))) for tt, v in zip(t, y)]
        cv2.polylines(img, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
        cv2.putText(img, lab, (44, y0 - h // 2 + 16), cv2.FONT_HERSHEY_SIMPLEX, .5, (60, 60, 60), 1, cv2.LINE_AA)
    plot(z, 140, 240, a.zlim, (40, 90, 200), f"zoom %/s (+push)  lim {a.zlim}")
    plot(pan, 470, 240, a.plim, (40, 150, 60), f"pan %W/s  lim {a.plim}")
    for b in starts[1:-1]: cv2.line(img, (X(b), 10), (X(b), Hh - 10), (60, 60, 230), 1)
    for s_ in range(int(t[-1]) + 1): cv2.putText(img, str(s_), (X(s_) - 4, Hh - 4), cv2.FONT_HERSHEY_SIMPLEX, .4, (90, 90, 90), 1)
    cv2.putText(img, f"{a.id}  zoom p90 {out['zoom_p90']}%/s  flips/min {out['flips_per_min']}  near-still {out['near_still']}", (420, 22), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(f"sheets/{a.id}_camcurve.png", img)
    print(f"{a.id}: 推拉幅度（90 分位）{out['zoom_p90']}%/s  摇移幅度 {out['pan_p90']}%W/s  推拉来回 {out['flips_per_min']} 次/分  几乎不动的时间 {out['near_still']:.0%}  换场时速度 {out['speed_at_change']}")
    print(f"  sheets/{a.id}_camcurve.png（蓝 = 推拉，绿 = 摇移，红竖线 = 换场）")

# ---------------------------------------------------------------- flow（镜头运动）
def cmd_flow(a):
    """逐帧光流：画面死不死、平不平、有没有前后层。避开字幕区（默认只看上面 80%）。
    指标：still 完全不动 / cam 镜头在动 / layer 有前后层 / nonuni 镜头动时各处不一样 / pushpull 推:拉 / zoom 慢漂速度 / p75 一镜 75 分位 / cutmin 切点密度"""
    import cv2, numpy as np
    vid = a.id; m = meta(vid); W, H = 320, 180; h = int(H * a.top)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(a.start), "-i", src(vid)] + (["-t", str(a.end - a.start)] if a.end < 1e8 else []) +
                         ["-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    fps = float(m.get("fps") or 30)
    ys, xs = np.mgrid[6:h - 6:8, 6:W - 6:8]; X = (xs - W / 2).ravel().astype(np.float32); Y = (ys - h / 2).ravel().astype(np.float32)
    A = np.zeros((2 * len(X), 4), np.float32); A[0::2, 0] = X; A[0::2, 1] = -Y; A[0::2, 2] = 1; A[1::2, 0] = Y; A[1::2, 1] = X; A[1::2, 3] = 1
    rows = []; prev = None
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H: break
        g = np.frombuffer(b, np.uint8).reshape(H, W)[:h]
        if prev is not None:
            diff = float(np.abs(g.astype(np.int16) - prev).mean())
            fl = cv2.calcOpticalFlowFarneback(prev, g, None, .5, 3, 15, 3, 5, 1.2, 0)
            u = fl[ys, xs, 0].ravel(); v = fl[ys, xs, 1].ravel()
            tex = np.hypot(cv2.Sobel(prev, cv2.CV_32F, 1, 0), cv2.Sobel(prev, cv2.CV_32F, 0, 1))[ys, xs].ravel() > 20
            mag = float(np.hypot(u, v)[tex].mean()) if tex.sum() > 20 else 0.
            if tex.sum() > 30:
                idx = np.where(tex)[0]; Ai = A.reshape(-1, 2, 4)[idx].reshape(-1, 4); bi = np.stack([u[idx], v[idx]], 1).ravel()
                Af, bf = Ai, bi; sol = np.zeros(4, np.float32)
                for _ in range(3):
                    sol, *_ = np.linalg.lstsq(Ai, bi, rcond=None); rn = np.hypot(*(Ai @ sol - bi).reshape(-1, 2).T)
                    keep = rn < max(.3, np.percentile(rn, 70) * 2)
                    if keep.all(): break
                    Ai = Ai.reshape(-1, 2, 4)[keep].reshape(-1, 4); bi = bi.reshape(-1, 2)[keep].ravel()
                rn = np.hypot(*(Af @ sol - bf).reshape(-1, 2).T); res = float(rn.mean()); fit = float((rn < .5).mean()); z, _, tx, ty = sol
            else: z = tx = ty = res = 0.; fit = 1.
            rows.append((diff, z, np.hypot(tx, ty) * 6, mag, res, fit, tx * 6, ty * 6))
        prev = g.copy()
    r = np.array(rows); n = len(r)
    if n < 5: raise SystemExit("帧数不够，检查 --start/--end")
    diff, zoom, tr, mag, res, fit, txs, tys = r.T
    cut = np.zeros(n, bool); last = -9
    for i in range(n):
        nb = np.median(np.r_[diff[max(0, i - 6):i], diff[i + 1:i + 7]])
        if diff[i] > 6 and diff[i] > 3 * nb + 2 and fit[i] < .7 and i - last > 4: cut[i] = True; last = i
    cam = (fit > .5) & ~cut & ((np.abs(zoom) > .0007) | (tr > 1.2)); still = (mag < .04) & ~cut
    def runs(mask):
        o = []; s = None
        for i, x in enumerate(np.r_[mask, False]):
            if x and s is None: s = i
            if not x and s is not None: o.append((i - s) / fps); s = None
        return np.array(o)
    b = np.r_[0, np.where(cut)[0], n]; seg = np.diff(b) / fps; seg = seg[seg > .1]
    holds = runs(still); mins = n / fps / 60
    zin, zout = ((zoom > .0007) & cam).sum(), ((zoom < -.0007) & cam).sum()
    out = dict(fps=round(float(fps), 2), seconds=round(n / fps, 1), still=round(float(still.mean()), 3),
               hold2_per_min=round((holds > 2).sum() / mins, 2), cam=round(float(cam.mean()), 3),
               layer=round(float((cam & (res > .25)).mean()), 3),
               nonuni=round(float(np.median(res[cam] / np.maximum(mag[cam], 1e-3))) if cam.any() else 0, 3),
               pushpull=round(zin / max(1, zout), 2),
               zoom_pct_s=round(float(np.median(np.abs(zoom[cam]))) * fps * 100 if cam.any() else 0, 2),
               shot_p50=round(float(np.median(seg)) if len(seg) else 0, 2),
               shot_p75=round(float(np.percentile(seg, 75)) if len(seg) else 0, 2),
               cut_per_min=round(cut.sum() / mins, 1),
               holds_over_2s=[round(float(x), 1) for x in holds if x > 2][:40],
               cuts=[round(float(i / fps), 2) for i in np.where(cut)[0]][:200],
               series=dict(fps=fps, zoom=[round(float(x), 5) for x in zoom], tx=[round(float(x), 3) for x in txs], ty=[round(float(x), 3) for x in tys],
                           fit=[round(float(x), 3) for x in fit], cut=[int(x) for x in cut]))
    json.dump(out, open(f"data/{vid}.flow.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print(f"{vid}: {out['seconds']}s @ {fps:.2f}fps（只看上面 {a.top:.0%}，避开字幕）")
    for k, lab in (("still", "完全不动"), ("cam", "镜头在动"), ("layer", "有前后层"), ("nonuni", "运动时各处不一样"),
                   ("pushpull", "推 : 拉"), ("zoom_pct_s", "慢漂速度 %/s"), ("shot_p50", "一镜中位 s"), ("shot_p75", "一镜 75 分位 s"),
                   ("cut_per_min", "切点 / 分钟"), ("hold2_per_min", "停住>2s 次/分")):
        print(f"  {lab:<16} {out[k]}")
    print(f"  → data/{vid}.flow.json")

# ---------------------------------------------------------------- audio
def cmd_audio(a):
    import numpy as np, librosa, cv2
    vid = a.id; y, sr = librosa.load(f"audio/{vid}_st.wav", sr=22050, mono=True); dur = len(y) / sr; hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]; t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=hop)
    on = librosa.onset.onset_detect(onset_envelope=oenv, sr=sr, hop_length=hop, backtrack=False, delta=.25); ot = librosa.frames_to_time(on, sr=sr, hop_length=hop)
    order = np.argsort(-oenv[on])[:70]; strong = sorted((round(float(ot[i]), 2), round(float(oenv[on][i]), 1)) for i in order)
    db = 20 * np.log10(np.maximum(rms, 1e-6)); per10 = [round(float(db[(t >= s) & (t < s + 10)].mean()), 1) for s in range(0, int(dur), 10)]
    quiet = []; st = None
    for k in range(len(db)):
        if db[k] < -50 and st is None: st = t[k]
        if st is not None and (db[k] >= -50 or k == len(db) - 1):
            if t[k] - st >= .5 and st > .5 and t[k] < dur - .5: quiet.append((round(float(st), 1), round(float(t[k]), 1)))
            st = None
    info = dict(duration=round(dur, 2), tempo=round(float(np.atleast_1d(tempo)[0]), 2), mean_dbfs=round(float(db.mean()), 1),
                peak_dbfs=round(float(20 * np.log10(np.abs(y).max() + 1e-9)), 1), onsets=int(len(on)),
                onsets_per_min=round(len(on) / dur * 60, 1), loud_per10s=per10, silent_spans=quiet, strong_onsets=strong)
    json.dump(info, open(f"data/{vid}.audio.json", "w"), indent=1)
    print(f"{vid}: 平均 {info['mean_dbfs']} dBFS  峰值 {info['peak_dbfs']}  估计速度 {info['tempo']} BPM  起音 {info['onsets']}（{info['onsets_per_min']}/分钟）")
    print("  读法：平均 -12 dBFS 以上、起音密、速度稳 = 现成配乐（母带压满）；-18 以下、起音稀 = 合成音 / 环境音。")
    print("  片中彻底静音：", quiet or "无"); print("  每 10 秒响度：", per10); print("  最强起音（时刻, 强度）：", strong)
    S = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=sr, n_fft=2048, hop_length=hop, n_mels=128, fmax=10000), ref=np.max)
    W = 2000; pps = W / dur; spec = cv2.applyColorMap(cv2.resize((np.clip((S + 70) / 70, 0, 1)[::-1] * 255).astype(np.uint8), (W, 384), interpolation=cv2.INTER_AREA), cv2.COLORMAP_MAGMA)
    def curve(v, lo, hi, col):
        im = np.full((220, W, 3), 18, np.uint8); xs = (t[:len(v)] * pps).astype(np.int32); ys = (219 - np.clip((v - lo) / (hi - lo), 0, 1) * 219).astype(np.int32)
        cv2.polylines(im, [np.stack([xs, ys], 1)], False, col, 1, cv2.LINE_AA); return im
    img = np.vstack([spec, curve(db, -60, 0, (255, 220, 120)), curve(oenv, 0, float(np.percentile(oenv, 99.9)), (160, 220, 255))])
    for s in range(0, int(dur) + 1, 10):
        x = int(s * pps); cv2.line(img, (x, 0), (x, img.shape[0]), (90, 90, 90), 1)
        cv2.putText(img, str(s), (x + 3, 14), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(f"sheets/{vid}_audio.png", img); print(f"  sheets/{vid}_audio.png（上：频谱；中：响度；下：起音强度）")

def cmd_asr(a):
    from faster_whisper import WhisperModel
    try: model = WhisperModel(a.model, device="cuda", compute_type="float16")
    except Exception: model = WhisperModel(a.model, device="cpu", compute_type="int8")
    wav = f"sep/{a.id}_vocals.wav" if os.path.exists(f"sep/{a.id}_vocals.wav") else f"audio/{a.id}.wav"   # 跑过 sep 就用干净的人声
    segs, _ = model.transcribe(wav, language=a.lang, word_timestamps=True, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=300))
    segs = list(segs)
    out = [dict(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in segs]
    words = [dict(t=round(w.start, 3), end=round(w.end, 3), w=w.word.strip()) for s in segs for w in (s.words or [])]
    json.dump(words, open(f"data/{a.id}.words.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    with open(f"data/{a.id}.asr.txt", "w", encoding="utf-8") as f:
        for s in out: f.write(f"[{s['start']:7.2f} - {s['end']:7.2f}] {s['text']}\n")
    print(f"{a.id}: {len(out)} 段" + ("。没有人声：旁白在画面上的字里，去跑 ocr + subs" if not out else f" → data/{a.id}.asr.txt"))

# ---------------------------------------------------------------- sep / sync（卡点：画面卡的是拍子、字，还是音效）
def cmd_sep(a):
    """把音轨分成 人声 / 鼓 / 贝斯 / 其他（demucs htdemucs，CPU 上 20 秒的片约半分钟）→ sep/<代号>_*.wav。
    没装 demucs：pip install --target <某目录> --no-deps demucs julius einops openunmix dora-search lameenc treetable retrying submitit omegaconf antlr4-python3-runtime，
    再把那个目录写进环境变量 DEMUCS_PATH。要 torch（CPU 版就行）和 soundfile。"""
    Path("sep").mkdir(exist_ok=True)
    env = dict(os.environ); here = Path(__file__).parent
    if env.get("DEMUCS_PATH"): env["PYTHONPATH"] = env["DEMUCS_PATH"] + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, str(here / "sep_demucs.py"), f"audio/{a.id}_st.wav", f"sep/{a.id}"], env=env, capture_output=True, text=True)
    if r.returncode: raise SystemExit("分离失败：" + r.stderr[-800:])
    print(f"{a.id}: sep/{a.id}_vocals.wav / _drums / _bass / _other")

def cmd_sync(a):
    """画面事件卡的是什么：每个事件离最近的词头、最近的配乐拍子各差多少。
    事件：--events "0.1,0.35,1.22" 或一个文本文件（每行一个秒数）；不给就用 scenes 的换场点。
    词：data/<代号>.words.json（vsr asr 生成）；拍子：sep/<代号>_drums+bass 做节拍追踪（先 vsr sep）。
    读法：落在词头 ±0.1s 的比例远高于落在拍上 ±0.06s 的比例 = 卡字（跟着说话走）；反过来 = 卡拍（跟着音乐走）。
    拍上的比例要和随机比：八分音符网格下随机约 0.12 /（半拍长）。"""
    import numpy as np
    if a.events and os.path.exists(a.events): ev = [float(x) for x in open(a.events, encoding="utf-8").read().replace(",", " ").split()]
    elif a.events: ev = [float(x) for x in a.events.split(",")]
    else: ev = (_load(a.id, "scenes") or {}).get("starts", [])[1:]
    ev = np.array(ev)
    if not len(ev): raise SystemExit("没有事件：给 --events，或先跑 scenes")
    wp = f"data/{a.id}.words.json"; words = json.load(open(wp, encoding="utf-8")) if os.path.exists(wp) else []
    ws = np.array([w["t"] for w in words])
    out = dict(n=len(ev))
    if len(ws):
        dw = np.array([x - ws[np.argmin(np.abs(ws - x))] for x in ev])
        out.update(word_within_100ms=round(float(np.mean(np.abs(dw) < .1)), 2), word_abs_p50_ms=int(np.median(np.abs(dw)) * 1000))
    if os.path.exists(f"sep/{a.id}_drums.wav"):
        import librosa, soundfile as sf
        d, sr = sf.read(f"sep/{a.id}_drums.wav"); b, _ = sf.read(f"sep/{a.id}_bass.wav"); m = (d + b).mean(1)
        tempo, beats = librosa.beat.beat_track(y=librosa.resample(m, orig_sr=sr, target_sr=22050), sr=22050, units="time")
        tempo = float(np.atleast_1d(tempo)[0])
        if len(beats) > 2:
            g8 = np.sort(np.concatenate([beats, beats[:-1] + np.diff(beats) / 2]))
            db = np.array([x - g8[np.argmin(np.abs(g8 - x))] for x in ev])
            out.update(bpm=round(tempo, 1), beat8_within_60ms=round(float(np.mean(np.abs(db) < .06)), 2), chance=round(min(1, .12 / (30 / tempo)), 2))
    json.dump(out, open(f"data/{a.id}.sync.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{a.id}: 事件 {out['n']} 个", end="")
    if "word_within_100ms" in out: print(f"  落在词头 ±0.1s：{out['word_within_100ms']:.0%}（|差| 中位 {out['word_abs_p50_ms']}ms）", end="")
    if "bpm" in out: print(f"  配乐 {out['bpm']} BPM，落在八分音符 ±60ms：{out['beat8_within_60ms']:.0%}（随机约 {out['chance']:.0%}）", end="")
    print()

# ---------------------------------------------------------------- ocr / subs / labels
def cmd_ocr(a):
    import cv2
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR(); vid = a.id; files = sorted(os.listdir(f"frames/{vid}")); sc = a.scale or (2 if meta(vid)["width"] < 1500 else 1)
    with open(f"data/{vid}.ocr.jsonl", "w", encoding="utf-8") as f:
        for i, fn in enumerate(files):
            img = cv2.imread(f"frames/{vid}/{fn}")
            if sc != 1: img = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
            res, _ = ocr(img); items = []
            for box, txt, conf in (res or []):
                xs = [p[0] / sc for p in box]; ys = [p[1] / sc for p in box]
                items.append(dict(x0=round(min(xs)), y0=round(min(ys)), x1=round(max(xs)), y1=round(max(ys)), t=txt, c=round(float(conf), 2)))
            f.write(json.dumps(dict(s=i, items=items), ensure_ascii=False) + "\n"); f.flush()
            if i % 50 == 0: print(vid, i, len(files), flush=True)
    print(vid, "ocr done")
def _ocr_rows(vid): return [json.loads(l) for l in open(f"data/{vid}.ocr.jsonl", encoding="utf-8")]
def _is_sub(it, W, H, ymin, xtol): return (it["y0"] + it["y1"]) / 2 >= ymin * H and abs((it["x0"] + it["x1"]) / 2 - W / 2) < xtol * W
def cmd_subs(a):
    import difflib
    vid = a.id; m = meta(vid); W, H = m["width"], m["height"]; cjk = lambda s: sum("\u4e00" <= c <= "\u9fff" for c in s); cur = None; out = []
    for r in _ocr_rows(vid):
        c = [it for it in r["items"] if _is_sub(it, W, H, a.ymin, a.xtol) and it["t"].strip() and it["c"] >= .6]
        main = sorted([x for x in c if cjk(x["t"]) >= 2] or [x for x in c if len(x["t"]) > 6 and not a.cjk_only], key=lambda x: x["y0"])
        second = [x for x in c if x not in main and len(x["t"]) > 6]
        txt = " ".join(x["t"] for x in main[:1]) if main else ""; sub2 = " ".join(x["t"] for x in second)
        if not txt:
            if cur: out.append(cur); cur = None
            continue
        if cur and (txt.startswith(cur["txt"][:max(2, len(cur["txt"]) // 2)]) or cur["txt"].startswith(txt[:max(2, len(txt) // 2)]) or difflib.SequenceMatcher(None, txt, cur["txt"]).ratio() > .6):
            cur["e"] = r["s"]
            if len(txt) >= len(cur["txt"]): cur["txt"] = txt; cur["box"] = main[0]
            if len(sub2) > len(cur["sub2"]): cur["sub2"] = sub2
        else:
            if cur: out.append(cur)
            cur = dict(s=r["s"], e=r["s"], txt=txt, sub2=sub2, box=main[0])
    if cur: out.append(cur)
    with open(f"data/{vid}.subs.txt", "w", encoding="utf-8") as f:
        for o in out:
            b = o["box"]; f.write(f"{o['s']:4d}-{o['e'] + 1:4d}  h={b['y1'] - b['y0']:3d} y={b['y0']}-{b['y1']} x={b['x0']}-{b['x1']}  {o['txt']}" + (f"  | {o['sub2']}" if o["sub2"] else "") + "\n")
    if not out: print("没找到字幕。调 --ymin（字幕区上沿占画面高度）或 --xtol；或这条片没有字幕"); return
    n = [len(re.sub(r"\s", "", o["txt"])) for o in out]; d = [o["e"] + 1 - o["s"] for o in out]
    hs = sorted(o["box"]["y1"] - o["box"]["y0"] for o in out); ws = max(o["box"]["x1"] - o["box"]["x0"] for o in out)
    yc = sum((o["box"]["y0"] + o["box"]["y1"]) / 2 for o in out) / len(out)
    stat = dict(lines=len(out), chars_mean=round(sum(n) / len(n), 2), chars_max=max(n), hold_mean=round(sum(d) / len(d), 2),
                per_min=round(len(out) / m["duration"] * 60, 2), chars_per_min=round(sum(n) / m["duration"] * 60),
                coverage=round(sum(d) / m["duration"] * 100, 1), h_median=hs[len(hs) // 2],
                h_pct=round(hs[len(hs) // 2] / H * 100, 2), yc_pct=round(yc / H * 100, 2), w_max_pct=round(ws / W * 100, 1))
    json.dump(stat, open(f"data/{vid}.subs.json", "w"), indent=1)
    print(f"{vid}: {len(out)} 句 → data/{vid}.subs.txt（时间精度 ±1s）")
    print(f"  每句字数 均 {stat['chars_mean']} / 最长 {stat['chars_max']}   每句停留 均 {stat['hold_mean']}s   每分钟 {stat['per_min']} 句 / {stat['chars_per_min']} 字")
    print(f"  字幕覆盖 {stat['coverage']}% 的时间   字高中位 {stat['h_median']}px（≈ 画面高的 {stat['h_pct']}%）   中线在 {stat['yc_pct']}% 高   最宽占 {stat['w_max_pct']}%")
def cmd_labels(a):
    vid = a.id; m = meta(vid); W, H = m["width"], m["height"]; out = {}
    for r in _ocr_rows(vid):
        for it in r["items"]:
            t = it["t"].strip()
            if not t or it["c"] < .6 or _is_sub(it, W, H, a.ymin, a.xtol): continue
            d = out.setdefault(r["s"] // a.win, {}); e = d.setdefault(t, [it["y1"] - it["y0"], 0, it["x0"], it["y0"]]); e[1] += 1
    for w in sorted(out):
        items = sorted([(k, v) for k, v in out[w].items() if v[1] >= 2 or v[0] >= .05 * H], key=lambda kv: (kv[1][3] // 40, kv[1][2]))
        print(f"{w * a.win:4d}-{w * a.win + a.win:4d}: " + " | ".join(k + (f"«{v[0]}»" if v[0] >= .05 * H else "") for k, v in items)[:a.width])
    print("«N» = 字高 N 像素的大字。每个时间窗都出现的小字 = 常驻元素（水印、章节标、仪表读数）")

# ---------------------------------------------------------------- colour
def cmd_palette(a):
    import cv2, numpy as np
    vid = a.id; files = sorted(os.listdir(f"frames/{vid}")); bg = []; pool = []; hexc = lambda c: "#%02X%02X%02X" % tuple(int(round(v)) for v in c)
    for i, fn in enumerate(files):
        if i % 2: continue
        sm = cv2.resize(cv2.cvtColor(cv2.imread(f"frames/{vid}/{fn}"), cv2.COLOR_BGR2RGB), (160, 90), interpolation=cv2.INTER_AREA).reshape(-1, 3).astype(np.float32)
        lum = sm @ np.array([.299, .587, .114], np.float32); bg.append((i, np.median(sm[np.argsort(lum)[:len(lum) // 2]], 0), np.median(sm, 0)))
        mx, mn = sm.max(1), sm.min(1); sel = sm[(lum > 110) | (((mx - mn) / np.maximum(mx, 1) > .45) & (mx > 90))]
        if len(sel): pool.append(sel[np.random.RandomState(i).choice(len(sel), min(len(sel), 300), replace=False)])
    print(f"{vid} 底色（每帧较暗一半像素的中位色），每 10 秒：\n   " + "  ".join(f"{i}s {hexc(d)}" for i, d, _ in bg if i % 10 == 0))
    pool = np.concatenate(pool); lab = cv2.cvtColor(pool.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    cv2.setRNGSeed(0); _, labels, _ = cv2.kmeans(lab, 10, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .5), 4, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel(); cnt = np.bincount(labels, minlength=10); cols = [(cnt[k] / len(pool), pool[labels == k].mean(0)) for k in np.argsort(-cnt) if cnt[k]]
    print("   亮色 / 彩色聚类（压缩过的片子会偏灰，精确色用 color 命令在字形核心量）：\n   " + "  ".join(f"{hexc(c)} {p * 100:.0f}%" for p, c in cols))
    json.dump(dict(bg=[(i, hexc(d)) for i, d, _ in bg][::5], colors=[(round(p, 3), hexc(c)) for p, c in cols]),
              open(f"data/{vid}.palette.json", "w"), ensure_ascii=False, indent=1)
    sw = np.zeros((120, 1000, 3), np.uint8); x = 0
    for p, c in cols: w = max(20, int(p * 1000)); sw[:, x:x + w] = c[::-1]; x += w
    strip = np.zeros((120, 1000, 3), np.uint8)
    for j, (_, d, md) in enumerate(bg): x0, x1 = int(j / len(bg) * 1000), int((j + 1) / len(bg) * 1000); strip[:60, x0:x1] = d[::-1]; strip[60:, x0:x1] = md[::-1]
    cv2.imwrite(f"sheets/{vid}_palette.png", np.vstack([sw, strip])); print(f"   sheets/{vid}_palette.png（上：亮色；下：底色随时间）")
def cmd_color(a):
    import numpy as np
    x0, y0, x1, y1 = [int(v) for v in a.box.split(",")]; px = np.asarray(grab(src(a.id), a.t)).astype(np.float32)[y0:y1, x0:x1].reshape(-1, 3)
    lum = px @ np.array([.299, .587, .114], np.float32); mx, mn = px.max(1), px.min(1); sat = (mx - mn) / np.maximum(mx, 1) * mx
    sel = {"bright": px[lum >= np.percentile(lum, 97)], "sat": px[sat >= np.percentile(sat, 97)], "dark": px[lum <= np.percentile(lum, 10)], "median": px}[a.mode]
    print("#%02X%02X%02X" % tuple(int(round(v)) for v in np.median(sel, 0)), f"  {a.id}@{a.t} {a.box} {a.mode}（bright = 浅色字核心，sat = 彩色字/图形核心，dark = 底）")

# ---------------------------------------------------------------- compare / blind
def cmd_compare(a):
    from PIL import Image
    m = meta(a.id); tw = a.tile; th = round(tw * m["height"] / m["width"]); pairs = []; labs = []   # 按参考片自己的画幅
    for t in a.times:
        ref = grab(src(a.id), t); tt = t + a.offset
        if os.path.isdir(a.replica):                      # 静帧目录：认 frames.mjs 的 still_<t>.png，也认旧的 s_<t>.png
            p = next((q for q in (os.path.join(a.replica, f"still_{tt:.2f}.png"), os.path.join(a.replica, f"s_{tt:07.2f}.png")) if os.path.exists(q)), None)
            rep = Image.open(p).convert("RGB") if p else Image.new("RGB", ref.size, (60, 0, 0))
        else: rep = grab(a.replica, tt)
        pair = Image.new("RGB", (tw * 2, th)); pair.paste(ref.resize((tw, th), Image.LANCZOS), (0, 0)); pair.paste(rep.resize((tw, th), Image.LANCZOS), (tw, 0))
        pairs.append(pair); labs.append(f"REF {t:.2f} | MINE {tt:.2f}")
    tile_sheet(pairs, a.cols, tw * 2, a.out, labs)

def cmd_blind(a):
    """把目录里的片段打乱、统一编码、拼成一条；答案键单独写 blind_key.txt。"""
    import random, tempfile
    files = sorted(f for f in os.listdir(a.dir) if f.lower().endswith((".mp4", ".mov", ".mkv")))
    if len(files) < 2: raise SystemExit("至少两段")
    random.Random(a.seed).shuffle(files)
    tmp = tempfile.mkdtemp(); lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for i, fn in enumerate(files):
            out = os.path.join(tmp, f"n{i:02d}.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(a.dir, fn), "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
                            "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out], check=True)
            f.write(f"file '{out}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", a.out], check=True)
    with open(os.path.splitext(a.out)[0] + "_key.txt", "w", encoding="utf-8") as f:
        for i, fn in enumerate(files): f.write(f"{i + 1:02d}  {fn}\n")
    print(f"{a.out}（{len(files)} 段，顺序已打乱；键在 {os.path.splitext(a.out)[0]}_key.txt，先盲看再看键）")

def cjk_font(size):
    from PIL import ImageFont
    for p in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"):
        if os.path.exists(p): return ImageFont.truetype(p, size)
    return font(size)
def cmd_pair(a):
    """近失对：参考片的一个手法 vs 我们的同一手法，各取 n 张连续帧上下对齐，底部写一句差在哪 → pairs/<名字>.jpg"""
    from PIL import Image, ImageDraw
    import numpy as np
    ours = src(a.ours[3:]) if a.ours.startswith("id:") else a.ours
    rows = []
    for path, t0, t1, lab in ((src(a.id), a.t0, a.t1, f"参考 {a.id}"), (ours, a.u0, a.u1, "我们")):
        ts = np.linspace(t0, t1, a.n); ims = [grab(path, t) for t in ts]; ims = [im.resize((a.tile, round(a.tile * im.height / im.width)), Image.LANCZOS) for im in ims]   # 按片子自己的画幅
        w, h = ims[0].size; row = Image.new("RGB", (w * a.n, h), (20, 20, 20)); d = ImageDraw.Draw(row); f = cjk_font(max(14, a.tile // 22))
        for i, (im, t) in enumerate(zip(ims, ts)):
            row.paste(im, (i * w, 0)); tag = f"{lab}  {t:.2f}" if i == 0 else f"{t:.2f}"
            bb = d.textbbox((0, 0), tag, font=f); d.rectangle([i * w, 0, i * w + bb[2] + 12, bb[3] + 10], fill=(0, 0, 0)); d.text((i * w + 6, 3), tag, font=f, fill=(255, 230, 0))
        rows.append(row)
    W = rows[0].width; fh = max(28, a.tile // 12); note = Image.new("RGB", (W, fh + 24), (250, 245, 230)); d = ImageDraw.Draw(note)
    d.text((16, 12), f"{a.name}：{a.note}", font=cjk_font(fh), fill=(30, 20, 10))
    sheet = Image.new("RGB", (W, rows[0].height * 2 + note.height), (0, 0, 0)); sheet.paste(rows[0], (0, 0)); sheet.paste(rows[1], (0, rows[0].height)); sheet.paste(note, (0, rows[0].height * 2))
    Path("pairs").mkdir(exist_ok=True); out = f"pairs/{a.name}.jpg"; sheet.save(out, quality=90); print(out, sheet.size)

def cmd_tstrip(a):
    """对临：换场前后逐帧对照。每个时间窗两排：上排参考、下排复刻，同一时刻上下对齐 → 一张图"""
    from PIL import Image, ImageDraw
    m = meta(a.id); tw = a.tile; th = round(tw * m["height"] / m["width"]); f = cjk_font(max(12, tw // 11)); rows = []
    for win in a.windows.split(","):
        t0, t1 = (float(x) for x in win.split("-")); ts = []; t = t0
        while t <= t1 + 1e-6: ts.append(round(t, 3)); t += a.step
        row = Image.new("RGB", (len(ts) * tw + 46, 2 * th + 18), (15, 15, 15)); d = ImageDraw.Draw(row)
        d.text((4, th // 2), "参考", font=f, fill=(255, 255, 255)); d.text((4, th + 18 + th // 2), "复刻", font=f, fill=(255, 230, 0))
        for i, t in enumerate(ts):
            x = 46 + i * tw; row.paste(grab(src(a.id), t).resize((tw, th), Image.LANCZOS), (x, 0))
            row.paste(grab(a.replica, t + a.offset).resize((tw, th), Image.LANCZOS), (x, th + 18)); d.text((x + 3, th + 1), f"{t:.2f}", font=f, fill=(255, 210, 70))
        rows.append(row)
    W = max(r.width for r in rows); sheet = Image.new("RGB", (W, sum(r.height + 8 for r in rows)), (0, 0, 0)); y = 0
    for r in rows: sheet.paste(r, (0, y)); y += r.height + 8
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); sheet.save(a.out, quality=86); print(a.out, sheet.size, len(rows), "个时间窗")

def _change_signal(path, size, fps=None):
    """逐帧画面变化（相邻两帧灰度差的均值）；fps 给了就按这个帧率取（两条帧率不同时对齐时间轴）"""
    import cv2, numpy as np
    c = cv2.VideoCapture(path); vf = c.get(cv2.CAP_PROP_FPS) or 30; prev = None; out = []
    while True:
        ok, fr = c.read()
        if not ok: break
        g = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), size).astype(np.float32)
        out.append(0.0 if prev is None else float(np.abs(g - prev).mean())); prev = g
    s = np.array(out)
    if fps and abs(vf - fps) > .01: s = np.interp(np.arange(0, len(s) / vf, 1 / fps), np.arange(len(s)) / vf, s)
    return s, (fps or vf)

def cmd_xcorr(a):
    """对临：整体时间对齐。两条片逐帧画面变化信号做互相关：最佳偏移（帧、秒）+ 每一段的偏移。
    换场、物件进出、镜头动作都会在信号上起峰，峰对上了 = 画面事件卡在同一时刻；分段偏移说明哪一段早了或晚了"""
    import numpy as np
    m = meta(a.id); size = (72, round(72 * m["height"] / m["width"]))
    r, fps = _change_signal(src(a.id), size); q, _ = _change_signal(a.replica, size, fps); n = min(len(r), len(q)); r, q = r[:n], q[:n]
    z = lambda x: (x - x.mean()) / (x.std() + 1e-9); L = int(round(a.max * fps))
    def corr(x, y, k): return float(np.mean(z(x[max(0, k):len(x) + min(0, k)]) * z(y[max(0, -k):len(y) - max(0, k)])))
    allk = [(k, corr(r, q, k)) for k in range(-L, L + 1)]; k0, c0 = max(allk, key=lambda x: x[1])
    late = -k0                                             # corr(r, q, k) 比的是 r(t+k) 和 q(t)：k>0 是复刻早了 k 帧
    print(f"{a.id} vs {a.replica}：{n} 帧；最佳偏移 {late:+d} 帧（{late / fps:+.3f}s，正 = 复刻晚），相关 {c0:.3f}（偏移 0 时 {dict(allk)[0]:.3f}）")
    w = int(a.win * fps); segs = []
    for s0 in range(0, n - w + 1, max(1, w // 2)):
        best = None
        for k in range(-L, L + 1):
            if s0 - k < 0 or s0 + w - k > n: continue
            x, y = r[s0:s0 + w], q[s0 - k:s0 + w - k]
            if x.std() < 1e-6 or y.std() < 1e-6: continue
            cc = float(np.corrcoef(x, y)[0, 1]); best = max(best or (k, -2), (k, cc), key=lambda v: v[1])
        if best: segs.append({"t0": round(s0 / fps, 2), "t1": round((s0 + w) / fps, 2), "lag_s": round(-best[0] / fps, 3), "r": round(best[1], 2)})
    for sg in segs: print(f"  {sg['t0']:5.1f}–{sg['t1']:5.1f}s  偏移 {sg['lag_s']:+.2f}s  r={sg['r']:.2f}" + ("   ← 这一段对不上" if abs(sg['lag_s']) > .1 or sg['r'] < .4 else ""))
    print("  读法：最佳偏移 0 帧、分段偏移都在 ±0.1s 内 = 时间对齐；某段 r 很低 = 那一段画面事件不一样（不是早晚的问题），去看 tstrip")
    Path("data").mkdir(exist_ok=True); json.dump({"lag_frames": late, "lag_s": round(late / fps, 3), "corr": round(c0, 3), "segments": segs}, open(f"data/{a.id}.xcorr.json", "w", encoding="utf-8"), indent=1)

# ---------------------------------------------------------------- ranges / dossier
METRIC_SRC = {"flow": "flow.json", "subs": "subs.json", "audio": "audio.json", "motion": "motion.json", "scenes": "scenes.json", "texture": "texture.json"}
def _load(vid, kind):
    p = f"data/{vid}.{METRIC_SRC[kind]}"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
def _flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict): out.update(_flatten(v, f"{prefix}{k}."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool): out[f"{prefix}{k}"] = v
    return out
def cmd_ranges(a):
    kinds = [k.strip() for k in a.metrics.split(",") if k.strip()]
    rows = {}
    for vid in a.ids:
        for kind in kinds:
            d = _load(vid, kind)
            if d: rows.setdefault(vid, {}).update({f"{kind}.{k}": v for k, v in _flatten(d).items()})
    keys = sorted({k for v in rows.values() for k in v})
    print(f"{'指标':<34}" + "".join(f"{v:>18}" for v in a.ids) + f"{'区间':>22}")
    for k in keys:
        vals = [rows[v][k] for v in a.ids if k in rows[v]]
        if not vals: continue
        rng = f"{min(vals):g} – {max(vals):g}"
        print(f"{k:<34}" + "".join((f"{rows[v][k]:>18g}" if k in rows[v] else f"{'-':>18}") for v in a.ids) + f"{rng:>22}")
def cmd_dossier(a):
    for vid in a.ids:
        m = meta(vid); print(f"\n=== {vid}  {m['width']}×{m['height']}  {m['fps']}fps  {m['duration']}s ===")
        for kind in ("scenes", "flow", "texture", "subs", "audio", "motion"):
            d = _load(vid, kind)
            if not d: continue
            d = {k: v for k, v in d.items() if not isinstance(v, (list, dict)) or k == 'starts'}
            if 'starts' in d: d['starts'] = len(d['starts'])          # scenes：只报场数
            print(f"  {kind}: " + "  ".join(f"{k}={v}" for k, v in d.items()))

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("ingest"); p.add_argument("video"); p.add_argument("id"); p.set_defaults(fn=cmd_ingest)
    p = sp.add_parser("sheet"); p.add_argument("id"); p.add_argument("start", type=float); p.add_argument("end", type=float); p.add_argument("step", type=float); p.add_argument("--cols", type=int, default=4); p.add_argument("--tile", type=int, default=480); p.set_defaults(fn=cmd_sheet)
    p = sp.add_parser("grid"); p.add_argument("id"); p.add_argument("name"); p.add_argument("times", type=float, nargs="+"); p.add_argument("--cols", type=int, default=4); p.add_argument("--tile", type=int, default=512); p.add_argument("--crop"); p.set_defaults(fn=cmd_grid)
    p = sp.add_parser("strip"); p.add_argument("id"); p.add_argument("start", type=float); p.add_argument("end", type=float); p.add_argument("n", type=int); p.add_argument("--cols", type=int, default=4); p.add_argument("--tile", type=int, default=480); p.add_argument("--crop"); p.set_defaults(fn=cmd_strip)
    p = sp.add_parser("motion"); p.add_argument("id"); p.set_defaults(fn=cmd_motion)
    p = sp.add_parser("scenes"); p.add_argument("id"); p.add_argument("--fps", type=float, default=10); p.add_argument("--thr", type=float, default=.4); p.add_argument("--hold", type=int, default=3); p.add_argument("--drift", type=float, default=.15); p.set_defaults(fn=cmd_scenes)
    p = sp.add_parser("texture"); p.add_argument("id"); p.set_defaults(fn=cmd_texture)
    p = sp.add_parser("camcurve"); p.add_argument("id"); p.add_argument("--zlim", type=float, default=60); p.add_argument("--plim", type=float, default=150); p.set_defaults(fn=cmd_camcurve)
    p = sp.add_parser("flow"); p.add_argument("id"); p.add_argument("--top", type=float, default=.8); p.add_argument("--start", type=float, default=0); p.add_argument("--end", type=float, default=1e9); p.set_defaults(fn=cmd_flow)
    p = sp.add_parser("audio"); p.add_argument("id"); p.set_defaults(fn=cmd_audio)
    p = sp.add_parser("asr"); p.add_argument("id"); p.add_argument("--lang", default="zh"); p.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "large-v3")); p.set_defaults(fn=cmd_asr)
    p = sp.add_parser("sep"); p.add_argument("id"); p.set_defaults(fn=cmd_sep)
    p = sp.add_parser("sync"); p.add_argument("id"); p.add_argument("--events"); p.set_defaults(fn=cmd_sync)
    p = sp.add_parser("ocr"); p.add_argument("id"); p.add_argument("--scale", type=int, default=0); p.set_defaults(fn=cmd_ocr)
    for name, fn in (("subs", cmd_subs), ("labels", cmd_labels)):
        p = sp.add_parser(name); p.add_argument("id"); p.add_argument("--ymin", type=float, default=.8, help="字幕区上沿占画面高度的比例"); p.add_argument("--xtol", type=float, default=.17, help="字幕中心离画面中线的最大偏移（占宽度）")
        p.add_argument("--win", type=int, default=6); p.add_argument("--width", type=int, default=400); p.add_argument("--cjk-only", action="store_true"); p.set_defaults(fn=fn)
    p = sp.add_parser("palette"); p.add_argument("id"); p.set_defaults(fn=cmd_palette)
    p = sp.add_parser("color"); p.add_argument("id"); p.add_argument("t", type=float); p.add_argument("box"); p.add_argument("mode", nargs="?", default="bright", choices=["bright", "sat", "dark", "median"]); p.set_defaults(fn=cmd_color)
    p = sp.add_parser("compare"); p.add_argument("id"); p.add_argument("replica"); p.add_argument("out"); p.add_argument("times", type=float, nargs="+"); p.add_argument("--cols", type=int, default=2); p.add_argument("--tile", type=int, default=512); p.add_argument("--offset", type=float, default=0); p.set_defaults(fn=cmd_compare)
    p = sp.add_parser("pair"); p.add_argument("id"); p.add_argument("t0", type=float); p.add_argument("t1", type=float); p.add_argument("ours", help="我们的 mp4，或 id:<代号>"); p.add_argument("u0", type=float); p.add_argument("u1", type=float)
    p.add_argument("name"); p.add_argument("note", help="一句话：差在哪一层"); p.add_argument("--n", type=int, default=6); p.add_argument("--tile", type=int, default=400); p.set_defaults(fn=cmd_pair)
    p = sp.add_parser("tstrip"); p.add_argument("id"); p.add_argument("replica"); p.add_argument("out"); p.add_argument("windows", help="起-止[,起-止…]，比如 1.0-1.45,5.55-6.0")
    p.add_argument("--step", type=float, default=.05); p.add_argument("--tile", type=int, default=144); p.add_argument("--offset", type=float, default=0); p.set_defaults(fn=cmd_tstrip)
    p = sp.add_parser("xcorr"); p.add_argument("id"); p.add_argument("replica"); p.add_argument("--win", type=float, default=3, help="分段窗长（秒）"); p.add_argument("--max", type=float, default=.5, help="最多找多大的偏移（秒）"); p.set_defaults(fn=cmd_xcorr)
    p = sp.add_parser("blind"); p.add_argument("dir"); p.add_argument("out"); p.add_argument("--seed", type=int, default=0); p.set_defaults(fn=cmd_blind)
    p = sp.add_parser("ranges"); p.add_argument("ids", nargs="+"); p.add_argument("--metrics", default="flow,subs,audio"); p.set_defaults(fn=cmd_ranges)
    p = sp.add_parser("dossier"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_dossier)
    a = ap.parse_args(); a.fn(a)
