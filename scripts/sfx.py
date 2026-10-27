# -*- coding: utf-8 -*-
"""合成音效 + 80 年代合成器配乐（全部代码生成，没有版权问题）。临时用：好不好听要人听。

  python sfx.py kit <目录>                 # 生成一套音效到 <目录>（flick pop click key whoosh whip swish thud ding shutter pencil coin car）
  python sfx.py bed <输出.wav> <秒数> [--bpm 104] [--seed 1]   # 一段合成器垫乐（小调四和弦、八分音符贝斯、鼓机）

音效和画面事件的对应（参考片工程里的音轨名 → 这里的名字）：
  逐词跳字 / 牌子翻上来（扑克-洗牌-牌面）→ flick；贴条拍上去（UI 点击）→ click；数字/字砸下（碰撞）→ thud
  打字、黑板敲字（电子-打字）→ key（每个字一声）；换场、圆圈（转场-呼）→ whoosh；甩镜 → whip；钞票/物件扫过 → swish
  灯泡、想法（科技-通知）→ ding；闪一下（胶片、闪光）→ shutter；画圈（铅笔）→ pencil；金币 → coin；车开过（汽车）→ car
"""
import sys, wave, argparse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from pathlib import Path
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
def save(path, x, sr=SR):
    x = np.asarray(x, np.float32); pk = np.abs(x).max() or 1; x = x / pk * .89
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes())
def t_(d): return np.arange(int(d * SR)) / SR
def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
R = np.random.default_rng(7)
def noise(d): return R.standard_normal(int(d * SR))
def env(n, a, d):                     # 起 a 秒、指数衰减常数 d 秒
    t = np.arange(n) / SR; e = np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / d); return e

def kit(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    # flick：纸牌弹出（短促的纸声）
    x = bp(noise(.09), 1800, 7000) * env(int(.09 * SR), .002, .018); x += .4 * bp(noise(.09), 400, 1200) * env(int(.09 * SR), .001, .01); save(out / 'flick.wav', x)
    # pop：轻的"啵"
    t = t_(.08); f = 900 * np.exp(-t * 30) + 250; x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .002, .025); save(out / 'pop.wav', x)
    # click：UI 点击
    x = hp(noise(.025), 3000) * env(int(.025 * SR), .0005, .004) + .5 * np.sin(2 * np.pi * 2400 * t_(.025)) * env(int(.025 * SR), .0005, .006); save(out / 'click.wav', x)
    # key：键盘/粉笔敲一下
    x = bp(noise(.04), 1500, 5000) * env(int(.04 * SR), .0008, .008) + .3 * lp(noise(.04), 300) * env(int(.04 * SR), .0005, .01); save(out / 'key.wav', x)
    # whoosh：换场"呼"
    d = .42; n = int(d * SR); t = t_(d); x = noise(d); y = np.zeros(n)
    for k in range(0, n, 480):         # 分段扫频：低 → 高 → 低
        c = 500 + 2500 * np.sin(np.pi * k / n); seg = slice(k, min(n, k + 960)); y[seg] += bp(x[seg], c * .6, c * 1.6)[:len(range(*seg.indices(n)))] * np.hanning(len(range(*seg.indices(n))))
    y *= np.sin(np.pi * t / d) ** 2; save(out / 'whoosh.wav', y)
    # whip：甩镜（更短更尖）
    d = .2; t = t_(d); y = bp(noise(d), 1200, 6000) * np.sin(np.pi * t / d) ** 3; save(out / 'whip.wav', y)
    # swish：一叠纸/钞票扫过（带纸张抖动）
    d = .55; t = t_(d); y = bp(noise(d), 900, 6000) * np.sin(np.pi * t / d) ** 2 * (.6 + .4 * np.sin(2 * np.pi * 32 * t)); save(out / 'swish.wav', y)
    # thud：重物落下 / 大字砸下
    d = .45; t = t_(d); f = 95 * np.exp(-t * 6) + 45; y = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .003, .12) + .35 * lp(noise(d), 900) * env(len(t), .001, .02); save(out / 'thud.wav', y)
    # ding：想法 / 提示
    d = 1.0; t = t_(d); y = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / dd) for f, a, dd in ((1568, 1, .35), (2352, .5, .22), (3136, .25, .15), (784, .3, .5))) * np.minimum(1, t / .002); save(out / 'ding.wav', y)
    # shutter：快门 / 闪光
    y = np.zeros(int(.12 * SR)); c = hp(noise(.02), 2000) * env(int(.02 * SR), .0005, .004); y[:len(c)] += c; y[int(.055 * SR):int(.055 * SR) + len(c)] += .8 * c; save(out / 'shutter.wav', y)
    # pencil：画圈
    d = .55; t = t_(d); y = bp(noise(d), 2500, 8000) * (.5 + .5 * np.abs(np.sin(2 * np.pi * 7 * t))) * np.sin(np.pi * t / d) ** .5; save(out / 'pencil.wav', y)
    # coin：金币
    d = .6; t = t_(d); y = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / dd) for f, a, dd in ((3300, 1, .12), (4950, .6, .08), (2200, .4, .18))) * np.minimum(1, t / .001); save(out / 'coin.wav', y)
    # car：老式汽车开过（突突声 + 由近到远）
    d = 1.4; t = t_(d); pul = (np.sin(2 * np.pi * 22 * t) > .3).astype(float); y = lp(noise(d), 500) * pul * 1.2 + .4 * lp(noise(d), 180)
    y *= np.exp(-((t - .6) / .45) ** 2); save(out / 'car.wav', y)
    print('音效 →', out, sorted(p.name for p in out.glob('*.wav')))

def bed(path, secs, bpm=104, seed=1):
    """小调四和弦（Am F C G）、八分音符贝斯、柔和锯齿铺底、鼓机。返回立体声 wav。"""
    beat = 60 / bpm; n = int(secs * SR); L = np.zeros(n)
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]   # Am F C G
    def saw(f, d):
        t = t_(d); ph = (f * t) % 1; return 2 * ph - 1
    bar = 4 * beat; nb = int(np.ceil(secs / bar)) + 1
    for b in range(nb):
        root, notes = chords[b % 4]; t0 = b * bar
        # 铺底：三个音的锯齿，低通，慢起
        pad = sum(saw(midi(m), bar) + .5 * saw(midi(m) * 1.003, bar) for m in notes); pad = lp(pad, 1400) * np.minimum(1, t_(bar) / .25) * np.minimum(1, (bar - t_(bar)) / .1) * .10
        i0 = int(t0 * SR); seg = L[i0:i0 + len(pad)]; seg += pad[:len(seg)]
        for k in range(8):               # 八分音符贝斯
            d = beat / 2; f = midi(root - 12) * (2 if k % 4 == 3 else 1); x = lp(saw(f, d), 700) * env(int(d * SR), .005, .12) * .32
            i = int((t0 + k * d) * SR); s = L[i:i + len(x)]; s += x[:len(s)]
        for k in range(4):               # 鼓：1、3 底鼓，2、4 军鼓，十六分音符踩镲
            i = int((t0 + k * beat) * SR)
            if k % 2 == 0: x = np.sin(2 * np.pi * np.cumsum(60 + 90 * np.exp(-t_(.3) * 25)) / SR) * env(int(.3 * SR), .001, .09) * .55
            else: x = bp(noise(.22), 900, 5000) * env(int(.22 * SR), .001, .06) * .28 + np.sin(2 * np.pi * 190 * t_(.22)) * env(int(.22 * SR), .001, .04) * .2
            s = L[i:i + len(x)]; s += x[:len(s)]
            for h in range(4):
                j = int((t0 + k * beat + h * beat / 4) * SR); x = hp(noise(.04), 7000) * env(int(.04 * SR), .0005, .012) * (.07 if h % 2 else .1)
                s = L[j:j + len(x)]; s += x[:len(s)]
    L = L[:n]; fade = np.minimum(1, np.minimum(np.arange(n) / (.3 * SR), (n - np.arange(n)) / (.8 * SR)))
    L *= fade; st = np.stack([L, np.roll(L, 240) * .96], 1)
    pk = np.abs(st).max() or 1; y = (st / pk * .7 * 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())
    print('配乐 →', path, f'{secs:.1f}s @ {bpm} BPM')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd'); ap.add_argument('out'); ap.add_argument('secs', nargs='?', type=float, default=30)
    ap.add_argument('--bpm', type=float, default=104); ap.add_argument('--seed', type=int, default=1); a = ap.parse_args()
    if a.cmd == 'kit': kit(a.out)
    elif a.cmd == 'bed': bed(a.out, a.secs, a.bpm, a.seed)
    else: sys.exit(__doc__)
