# -*- coding: utf-8 -*-
"""对临用：把参考片的词级时间（vsr asr 出的 data/<代号>.words.json）变成 timeline.json，配音直接用原片人声。
  python ref_timeline.py <vsr 工作目录>/data/v1.words.json voice/v1_vocals.wav 16.7 > timeline.json
每句按句末标点（. ? ! 。？！）切；每个字的时刻 = 它所在词的开始，at('s01', 'cash') 照常能用。
timeline.json 里写 voice_track，mix.py 就整条用这个人声，不再按句拼。
注意：whisper 的词边界会粘连（v1 的 "in" 被给了 0.86s），画面事件按原片逐帧量到的时刻排，at() 只当参考。"""
import sys, json, re
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
if len(sys.argv) < 4: sys.exit(__doc__)
W = json.load(open(sys.argv[1], encoding='utf-8')); voice, dur = sys.argv[2], float(sys.argv[3])
W = [w if isinstance(w, dict) else {'t': w[0], 'end': w[1], 'w': w[2]} for w in W]
beats, cur = [], []
for w in W:
    cur.append(w)
    if re.search(r'[.?!。？！]$', w['w'].strip()) or w is W[-1]:
        text, chars = '', []
        for k, x in enumerate(cur):
            if k: text += ' '; chars.append([' ', x['t']])
            for c in x['w'].strip(): text += c; chars.append([c, x['t']])
        beats.append({'id': f's{len(beats) + 1:02d}', 'text': text, 'start': cur[0]['t'], 'end': cur[-1]['end'], 'chars': chars}); cur = []
print(json.dumps({'fps': 30, 'duration': dur, 'aspect': '9:16', 'pre': 0, 'voice_track': voice, 'beats': beats}, ensure_ascii=False, indent=1))
