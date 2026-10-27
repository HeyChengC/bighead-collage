# -*- coding: utf-8 -*-
"""用户给的整条正式配音（不切、不变速）→ timeline.json。
  python voice_timeline.py <配音文件(mp3/wav)> [--script script.json]
script.json 的 lines 按句写好文案（屏上的写法，数字逐位读的写阿拉伯数字）。
做法：转成 voice/main.wav（48k 单声道，时间不动）→ faster-whisper 整条识别、逐词时间 → 按顺序把文案的每个字对上 → 吸附到最近的音节起音 → 每句一个 beat。
timeline.json 写 voice_track：mix.py 整条用这条人声；每句另切一段 voice/<id>.wav（从这句起点切到下一句起点，首尾相接），verify.py --sync 拼回来正好是整条。
对不上的字会打印出来（ASR 听成别的字，比如"那儿"听成"哪"），按前后插值，不影响别的字。
音画对齐最后要从成片量（verify.py --sync，或对 final.mp4 的声音再识别一遍），不用这份计划自证。"""
import json, sys, difflib, subprocess
from pathlib import Path
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
a = [x for x in sys.argv[1:] if not x.startswith('--')]
if not a: sys.exit(__doc__)
src = a[0]; sp = sys.argv[sys.argv.index('--script') + 1] if '--script' in sys.argv else 'script.json'
import numpy as np, librosa
S = json.load(open(sp, encoding='utf-8')); Path('voice').mkdir(exist_ok=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-ar', '48000', '-ac', '1', 'voice/main.wav'], check=True)
from faster_whisper import WhisperModel
try: m = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device='cuda', compute_type='float16')
except Exception: m = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device='cpu', compute_type='int8')
segs, _ = m.transcribe('voice/main.wav', language='zh', word_timestamps=True)
W = [[w.word, float(w.start), float(w.end)] for s in segs for w in s.words]
json.dump(W, open('voice/asr_words.json', 'w', encoding='utf-8'), ensure_ascii=False)
CN = dict(zip('0123456789', '零一二三四五六七八九')); PUN = '，。：、“”‘’；！？,.:;!?·" '
seq = []
for w, s, e in W:
    w = w.strip()
    for i, ch in enumerate(w): seq.append((ch, s + (e - s) * i / max(1, len(w)), s + (e - s) * (i + 1) / max(1, len(w))))
full = ''.join(l['text'] for l in S['lines'])
A_ = [CN.get(c, c) for c in full]; B_ = [CN.get(c, c) for c, _, _ in seq]; st = [None] * len(A_); en = [None] * len(A_)
for blk in difflib.SequenceMatcher(None, A_, B_, autojunk=False).get_matching_blocks():
    for k in range(blk.size): st[blk.a + k], en[blk.a + k] = seq[blk.b + k][1], seq[blk.b + k][2]
print('对不上的字：', ''.join(full[i] for i in range(len(A_)) if st[i] is None and full[i] not in PUN) or '无')
known = [i for i, x in enumerate(st) if x is not None]
for i in range(len(st)):
    if st[i] is None:
        p = max([k for k in known if k < i], default=None); n = min([k for k in known if k > i], default=None)
        st[i] = en[p] if p is not None else st[n]; en[i] = st[i]
y, sr = librosa.load('voice/main.wav', sr=16000); dur = len(y) / sr
on = librosa.onset.onset_detect(y=y, sr=sr, units='time', backtrack=True, delta=.04)
def snap(x):
    c = on[np.abs(on - x) < .15]; return float(c[np.argmin(np.abs(c - x))]) if len(c) else x
sn = [snap(x) if full[i] not in PUN else x for i, x in enumerate(st)]
for i in range(1, len(sn)): sn[i] = max(sn[i], sn[i - 1])
beats, k = [], 0
for l in S['lines']:
    n = len(l['text']); idx = [i for i in range(k, k + n) if full[i] not in PUN]
    beats.append({'id': l['id'], 'text': l['text'], 'start': round(sn[idx[0]], 3), 'end': round(max(en[i] for i in idx), 3), 'chars': [[full[i], round(sn[i], 3)] for i in range(k, k + n)]}); k += n
for i, bt in enumerate(beats):
    nxt = beats[i + 1]['start'] if i + 1 < len(beats) else dur
    bt['wav'] = f"voice/{bt['id']}.wav"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'voice/main.wav', '-ss', str(bt['start']), '-to', str(nxt), bt['wav']], check=True)
T = {'fps': 30, 'duration': round(dur + S.get('tail', .6), 3), 'aspect': S.get('aspect', '9:16'), 'pre': 0, 'voice_track': 'voice/main.wav', 'beats': beats}
json.dump(T, open('timeline.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for i, bt in enumerate(beats):
    gap = (beats[i + 1]['start'] - bt['end']) if i + 1 < len(beats) else 0
    print(f"{bt['id']} {bt['start']:6.2f}-{bt['end']:6.2f}  停{gap:4.2f}  {bt['text']}")
