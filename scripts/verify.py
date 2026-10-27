# -*- coding: utf-8 -*-
"""交片前机器检查。不做审美判断，只报"做错了"的硬项；每个 FAIL 都能直接修。

  python verify.py 成片.mp4 [--expect 1920x1080] [--dur 64.6] [--lufs -15,-10]
  python verify.py --lines voice/*.wav          逐句配音：查结尾是不是被截断、开头空白多长
  python verify.py --sync 工程目录 [--from final.mp4]   画面排字用的时刻（timeline.json 每个字）和配音里真正发声的时刻差多少；--from 直接从成片的声音量

成片查：能否解码到结尾 / 时长 / 画幅 / 音轨 / 综合响度 / 真峰值 / 黑帧 / 冻帧
逐句查：最后 40ms 的电平（> -40 dB 多半被截断）/ 开头静音时长
不查：内容对不对、好不好看、声音好不好听——这些只能人判。"""
import glob, json, re, subprocess, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

fails = []; warns = []
def run(cmd): p = subprocess.run(cmd, capture_output=True, text=True, errors="replace"); return p.stdout + p.stderr

def pcm(path, sr=16000):
    import numpy as np
    b = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(b, np.int16).astype(np.float32) / 32768, sr

def check_lines(paths):
    import numpy as np
    db = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    print(f"{'文件':<36}{'时长':>8}{'尾40ms':>10}{'头部静音':>10}")
    for p in paths:
        y, sr = pcm(p)
        if len(y) < sr * .1: fails.append(f"{p} 太短或读不出"); continue
        tail = db(y[-int(sr * .04):]); win = int(sr * .02); head = 0
        while head + win < len(y) and db(y[head:head + win]) < -40: head += win
        print(f"{p[-36:]:<36}{len(y) / sr:>7.2f}s{tail:>9.1f}{head / sr:>9.2f}s")
        if tail > -40: fails.append(f"{p}：结尾 40ms 电平 {tail:.1f} dB，可能被截断（重合成这一句，不要剪音频）")
        if head / sr > .45: warns.append(f"{p}：开头 {head / sr:.2f}s 静音，拼接前切掉（-30 dB rms）")

def check_film(path, a):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], capture_output=True, text=True).stdout or "{}")
    if not j.get("streams"): fails.append("ffprobe 读不出：文件不完整或不是视频"); return
    v = [s for s in j["streams"] if s["codec_type"] == "video"]; au = [s for s in j["streams"] if s["codec_type"] == "audio"]
    if not v: fails.append("没有视频流"); return
    dur = float(j["format"]["duration"]); w, h = v[0]["width"], v[0]["height"]
    num, den = v[0].get("avg_frame_rate", "30/1").split("/"); fps = int(num) / max(1, int(den))
    print(f"{path}\n  {w}×{h}  {fps:.3f}fps  {dur:.2f}s  {int(j['format'].get('bit_rate', 0)) // 1000} kbps  音轨 {'有' if au else '没有'}")
    if subprocess.run(["ffmpeg", "-v", "error", "-ss", str(max(0, dur - .3)), "-i", path, "-frames:v", "1", "-f", "null", "-"], capture_output=True).returncode:
        fails.append("结尾解码失败（文件不完整）")
    want_dur = float(a[a.index("--dur") + 1]) if "--dur" in a else None
    expect = a[a.index("--expect") + 1] if "--expect" in a else None
    if want_dur and abs(dur - want_dur) > .15: fails.append(f"时长 {dur:.2f}s，期望 {want_dur:.2f}s")
    if expect and expect.lower() != f"{w}x{h}": fails.append(f"画幅 {w}×{h}，期望 {expect}")
    bd = run(["ffmpeg", "-v", "info", "-i", path, "-vf", "blackdetect=d=0.2:pix_th=0.02", "-an", "-f", "null", "-"])
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", bd):
        warns.append(f"黑帧 {float(m.group(3)):.2f}s @ {float(m.group(1)):.2f}s（设计内的换场可以忽略）")
    fd = run(["ffmpeg", "-v", "info", "-i", path, "-vf", "freezedetect=n=-50dB:d=2", "-an", "-f", "null", "-"])
    for m in re.finditer(r"freeze_start: ([\d.]+)", fd):
        warns.append(f"画面完全冻住 >2s @ {float(m.group(1)):.2f}s（有意的静止可以忽略）")
    if not au: fails.append("没有音轨"); return
    lo, hi = (float(x) for x in a[a.index("--lufs") + 1].split(",")) if "--lufs" in a else (-15.0, -10.0)
    loud = run(["ffmpeg", "-v", "info", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = loud[loud.rfind("Summary:"):] if "Summary:" in loud else loud
    m = re.search(r"I:\s*(-?[\d.]+) LUFS", summ); pk = re.search(r"True peak:\s*Peak:\s*(-?[\d.]+|-inf) dBFS", summ, re.S)
    lufs = float(m.group(1)) if m else None; peak = float(pk.group(1)) if pk and pk.group(1) != "-inf" else None
    print(f"  综合响度 {lufs} LUFS   真峰值 {peak} dBTP")
    if lufs is None: warns.append("读不到响度")
    elif lufs < -40: fails.append("整条几乎无声")
    elif not (lo <= lufs <= hi): fails.append(f"综合响度 {lufs} LUFS，应在 {lo}~{hi}")
    if peak is not None and peak > -1.0: fails.append(f"真峰值 {peak} dBTP，超过 -1（会削波）")
    y, sr = pcm(path, 8000)
    import numpy as np
    if len(y) > sr:
        head = 20 * np.log10(np.sqrt(np.mean(y[:int(sr * .5)] ** 2)) + 1e-9)
        if head < -45: warns.append(f"前 0.5 秒几乎无声（{head:.0f} dB）：开头要有声音")

def check_sync(d, lang="zh", src=None):
    """画面用的字时刻 vs 配音真正发声的时刻。TTS 自报的词边界常常整体偏晚（edge-tts 实测晚 ~0.23s），
    画面全片慢半拍、处处"不卡点"，看静帧和自己排的时间表都看不出来。这里从配音波形里找每个音节的起音来对。"""
    import numpy as np, librosa, os
    T = json.load(open(os.path.join(d, "timeline.json"), encoding="utf-8"))
    ins, flt = [], []
    for i, b in enumerate(T["beats"]):
        ins += ["-i", os.path.join(d, b["wav"])]; flt.append(f"[{i}]adelay={int(b['start'] * 1000)}:all=1[a{i}]")
    n = len(T["beats"]); flt.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={T['duration']}[o]")
    tmp = os.path.join(d, "_voice_check.wav")
    if src:                                   # 从成片量（推荐交片前用）：直接拿 final.mp4 的声音，音效、配乐一起在里面
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ar", "16000", "-ac", "1", tmp], check=True)
    elif T.get("voice_track"):                # 整条正式配音（voice_timeline.py 出的）：直接用这一条
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, T["voice_track"]), "-ar", "16000", "-ac", "1", tmp], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(flt), "-map", "[o]", "-ar", "16000", "-ac", "1", tmp], check=True)
    # 按顺序对齐：整轨做语音识别（逐字时间），和画面用的字一一对上（difflib），再看差多少。
    # 不用"离最近的起音"：中文音节很密，什么时刻附近都有起音，整体晚 0.2s 也量不出来（试过）。
    import difflib
    from faster_whisper import WhisperModel
    try: wm = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device="cuda", compute_type="float16")
    except Exception: wm = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device="cpu", compute_type="int8")
    segs, _ = wm.transcribe(tmp, language=lang, word_timestamps=True)
    heard = []
    for sg in segs:
        for w in sg.words:
            t = w.word.strip()
            for k, ch in enumerate(t): heard.append((ch, w.start + (w.end - w.start) * k / max(1, len(t))))
    plan = [(c, t) for b in T["beats"] for c, t in b["chars"] if c.strip() and c not in "，。：、“”；,.:;!?！？ "]
    sm = difflib.SequenceMatcher(None, [c for c, _ in plan], [c for c, _ in heard], autojunk=False); dd = []
    for blk in sm.get_matching_blocks():
        for k in range(blk.size): dd.append(plan[blk.a + k][1] - heard[blk.b + k][1])
    dd = np.array(dd); med = float(np.median(dd)) if len(dd) else 0; off = float(np.mean(np.abs(dd) > .15)) if len(dd) else 0
    print(f"{d}: 对上 {len(dd)}/{len(plan)} 个字  画面时刻 − 听出来的时刻：中位 {med * 1000:+.0f}ms，|差|>150ms 的 {off:.0%}")
    if abs(med) > .1: fails.append(f"画面和配音整体错位 {med * 1000:+.0f}ms：字时刻要按真实发音重新对齐（temp_voice 默认会做：ASR 逐字对齐 + 吸附到起音）")
    elif off > .3: warns.append(f"{off:.0%} 的字和发音差 150ms 以上")

def main():
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == "--sync":
        check_sync(a[1], a[a.index("--lang") + 1] if "--lang" in a else "zh", a[a.index("--from") + 1] if "--from" in a else None)
    elif a[0] == "--lines":
        paths = [p for pat in a[1:] for p in (glob.glob(pat) or [pat])]; check_lines(paths)
    else:
        check_film(a[0], a)
    print()
    for f in fails: print("  FAIL", f)
    for w in warns: print("  warn", w)
    if not fails: print("  硬项全部通过（好不好看、好不好听，还得人看人听）")
    print(f"  {len(fails)} 个 FAIL，{len(warns)} 个 warn")
    sys.exit(1 if fails else 0)

main()
