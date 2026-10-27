# -*- coding: utf-8 -*-
"""建一个空的大头剪贴风工程（脚手架，不是模板：没有任何画面）。
  python new_film.py <工程目录>
产物：index.html（载入 a/stage.js、a/acts.js、a/look.css）、a/（引擎、字体）、scene.js（空）、script.json（文案占位，竖屏）。
字体：Anton、思源黑（NotoSansSC-VF）、得意黑；找不到的会提示，补到 a/ 里。"""
import sys, shutil
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
if len(sys.argv) < 2: sys.exit(__doc__)
D = Path(sys.argv[1]); A = D / 'a'; A.mkdir(parents=True, exist_ok=True); H = Path(__file__).parent
for f in ('stage.js', 'acts.js', 'look.css'): shutil.copy2(H / f, A / f)
FONTS = {'Anton-Regular.ttf': [H / 'fonts' / 'Anton-Regular.ttf'],
         'NotoSansSC-VF.ttf': [H / 'fonts' / 'NotoSansSC-VF.ttf'],
         'SmileySans-Oblique.ttf': [H / 'fonts' / 'SmileySans-Oblique.ttf']}
for name, cands in FONTS.items():
    src = next((c for c in cands if c.exists()), None)
    if src: shutil.copy2(src, A / name)
    else: print('缺字体', name, '→ 放进', A)
(D / 'index.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="a/look.css"></head>
<body><script src="a/stage.js"></script><script src="a/acts.js"></script><script src="scene.js"></script></body></html>
''', 'utf-8')
if not (D / 'scene.js').exists():
    (D / 'scene.js').write_text("// 画面：一场一个小舞台。时间一律从 timeline.json 取（STAGE.at / STAGE.beat），不手填秒数。\nconst {scene, word, row, sfx, TX, LOOK, at, beat, W, H, kf, spline, clamp} = STAGE;\nconst {person, actor, drop, rise, slap, dust, shakeOf, ring_, out, plus} = ACTS;   // 动作语法（engine.md）\n", 'utf-8')
if not (D / 'script.json').exists():
    (D / 'script.json').write_text('{\n  "pre": 0.15, "aspect": "9:16",\n  "lines": [\n    {"id": "s01", "text": "第一句。", "gap": 0.15}\n  ]\n}\n', 'utf-8')
for d in ('img', 'sfx', 'gen'): (D / d).mkdir(exist_ok=True)
print('建好', D.resolve(), '→ 下一步：写 script.json → 配音（temp_voice.py / voice_timeline.py）→ 导演表 → gen/ 里生图 → 写 scene.js')
