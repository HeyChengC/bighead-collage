# -*- coding: utf-8 -*-
"""临时配音 + 时间线：script.json → voice/<id>.wav + timeline.json（画面全部挂在这份时间线的字上）

配音一律：切首尾静音、原速（不 atempo 加速——用户听 1.1 倍说“窘迫”）。句间停顿只由 gap 决定。
配音从哪来看 config.json 的 voice.provider（python config.py 查看 / 修改）：
  edge      edge-tts 免费在线配音（默认）。
  command   你自己的 TTS（豆包、ElevenLabs、MiniMax、VoxCPM、本地模型……）：voice.command 里写一条命令，
            {text} / {text_file} / {out} 会被替换，每句调用一次，产出 voice/<id>.final.wav。
  recording 你给的是一整条录好的配音：不用这个脚本，用 voice_timeline.py。
任何一句只要有 voice/<id>.final.wav（不管哪来的）就用它，只切首尾静音、不变速，再逐字对齐。

script.json 例：
{
  "voice": "zh-CN-YunxiNeural", "rate": "+0%", "pre": 0.3,
  "title": {"after": "s01", "len": 1.7},
  "lines": [
    {"id": "s01", "text": "今年，光是谷歌、微软、亚马逊、Meta 这四家……", "gap": 0.35},
    {"id": "s10b", "text": "难怪黄仁勋总爱说这句：", "gap": 0.5,
     "bite": {"pre": 0.15, "post": 0.4, "parts": [["footage/jensen.m4a", 101.60, 1.95, "买得越多，省得越多", 2.5]]}}
  ]
}
- say：只给 TTS 读的写法（数字、英文怎么念），不改屏上的 text
- bite：这句之后插一段原声，parts = [源文件, 入点秒, 时长, 中文字幕, 增益dB]；源文件相对 script.json
- pre：开头先空多久再开口（开头快闪垫在下面）；title：哪句后面留片名的时间

  python temp_voice.py film/script.json            # 缺的句子用 edge-tts 补，已有的不重做
  python temp_voice.py film/script.json --redo     # 全部重做临时配音
  python temp_voice.py film/script.json --asr      # 强制重新逐字对齐（换成正式配音后用）
  默认每句都用 faster-whisper 逐字对齐，再把每个字吸附到波形上的音节起音（edge-tts 自报的字时刻整体晚 ~0.2s，画面会全片慢半拍）；--no-snap 关掉吸附
"""
import asyncio, difflib, json, subprocess, sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
from pathlib import Path

SP = Path(sys.argv[1]).resolve(); D = SP.parent
S = json.loads(SP.read_text('utf-8'))
REDO, ASR = '--redo' in sys.argv, '--asr' in sys.argv
NOSNAP = '--no-snap' in sys.argv          # 默认：字时刻先用 ASR 对齐，再吸附到波形上最近的音节起音
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
VC = config.load()['voice']
PROVIDER = VC.get('provider', 'edge')
VOICE, RATE = S.get('voice', VC.get('edge_voice', 'zh-CN-YunxiNeural')), S.get('rate', VC.get('rate', '+0%'))
if PROVIDER == 'recording':
    sys.exit('voice.provider 是 recording（整条录音）：请用 python voice_timeline.py <配音文件>，不用这个脚本。')
(D / 'voice').mkdir(exist_ok=True)
TRIM = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"


def dur(f):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)]))


def lead_silence(f):
    """切掉的开头静音有多长（逐字时间要减掉它）"""
    out = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(f), '-af', 'silencedetect=n=-45dB:d=0.02', '-f', 'null', '-'], capture_output=True, text=True).stderr
    for ln in out.splitlines():
        if 'silence_end' in ln and 'silence_start: 0' in out.split('silence_end')[0][-60:]:
            return max(0.0, float(ln.split('silence_end:')[1].split('|')[0]) - .03)
    return 0.0


async def edge(text, mp3):
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, VOICE, rate=RATE, boundary='WordBoundary')
    with open(mp3, 'wb') as fp:
        async for ch in com.stream():
            if ch['type'] == 'audio': fp.write(ch['data'])
            elif ch['type'] == 'WordBoundary': words.append([ch['text'], ch['offset'] / 1e7, (ch['offset'] + ch['duration']) / 1e7])
    return words


def custom_tts(text, final):
    """voice.provider = command：调用用户配置的 TTS 命令，把结果转成 voice/<id>.final.wav。"""
    import os, shlex
    tpl = VC.get('command') or ''
    if not tpl: sys.exit('voice.provider 是 command，但 voice.command 是空的：python config.py set voice.command "..."')
    q = (lambda x: subprocess.list2cmdline([x])) if os.name == 'nt' else shlex.quote
    tf = final.with_suffix('.txt'); tf.write_text(text, 'utf-8')
    raw = final.with_name(final.stem.replace('.final', '') + '.tts.' + VC.get('out_ext', 'wav').lstrip('.'))
    if raw.exists(): raw.unlink()
    cmd = tpl.replace('{text_file}', q(str(tf))).replace('{out}', q(str(raw))).replace('{text}', q(text))
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if not raw.exists():
        sys.exit('\n'.join([f'TTS 命令没产出 {raw}：', cmd, r.stdout[-800:], r.stderr[-800:]]))
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-ar', '48000', '-ac', '1', str(final)], check=True)


CN_DIGIT = dict(zip('0123456789', '零一二三四五六七八九'))
def char_times(caption, words):
    """把逐词时间对到屏上文字的每个字；对不上的字（标点）按前后插值。
    屏上写阿拉伯数字、配音读中文（text "1928年"、say "一九二八年"）时，数字逐位换成中文再对，年份不会错位。
    读法不是逐位的（"34" 读"三十四"）对不上的，还是插值——这种就在 text 里直接写中文，或者用 beat(id).start 手动取。"""
    seq = []
    for w, s, e in words:
        w = w.strip()
        for i, ch in enumerate(w): seq.append((ch, s + (e - s) * i / max(1, len(w))))
    a, b = [CN_DIGIT.get(c, c) for c in caption], [CN_DIGIT.get(c, c) for c, _ in seq]; tm = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size): tm[blk.a + k] = seq[blk.b + k][1]
    known = [i for i, x in enumerate(tm) if x is not None]
    for i in range(len(tm)):
        if tm[i] is None:
            p = max([k for k in known if k < i], default=None); n = min([k for k in known if k > i], default=None)
            tm[i] = (0 if p is None and n is None else (tm[n] - .12 * (n - i)) if p is None else (tm[p] + .12 * (i - p)) if n is None
                     else tm[p] + (tm[n] - tm[p]) * (i - p) / (n - p))
    for i in range(1, len(tm)): tm[i] = max(tm[i], tm[i - 1])
    return [max(0.0, x) for x in tm]


def snap(wav, rel):
    """把一句里每个字的时刻（相对这句开头）吸附到波形上最近的音节起音（±0.15s 内）。
    edge-tts 报的词边界、甚至 ASR 的词时间都会偏；画面要卡字，得卡在真正发出声音的那一刻。"""
    import numpy as np, librosa
    y, sr = librosa.load(str(wav), sr=16000)
    on = librosa.onset.onset_detect(y=y, sr=sr, units='time', backtrack=True, delta=.04)
    out = []
    for x in rel:
        c = on[np.abs(on - x) < .15]
        out.append(float(c[np.argmin(np.abs(c - x))]) if len(c) else x)
    for i in range(1, len(out)): out[i] = max(out[i], out[i - 1])
    return out


whisper = None
def asr_words(wav):
    global whisper
    if whisper is None:
        from faster_whisper import WhisperModel
        try: whisper = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device='cuda', compute_type='float16')
        except Exception: whisper = WhisperModel(__import__('os').environ.get('WHISPER_MODEL', 'large-v3'), device='cpu', compute_type='int8')
    segs, _ = whisper.transcribe(str(wav), language='zh', word_timestamps=True)
    return [[w.word, float(w.start), float(w.end)] for s in segs for w in s.words]


t = .15 + S.get('pre', 0.0); beats, inserts, title = [], [], None
meta_p = D / 'voice' / 'words.json'; meta = json.loads(meta_p.read_text('utf-8')) if meta_p.exists() else {}
for ln in S['lines']:
    lid, text = ln['id'], ln['text']; wav = D / 'voice' / f'{lid}.wav'; final = D / 'voice' / f'{lid}.final.wav'
    if PROVIDER == 'command' and (REDO or not final.exists()):
        print('TTS', lid, ln.get('say', text)[:30]); custom_tts(ln.get('say', text), final)
    src_key = f"{ln.get('say', text)}|{VOICE}|{RATE}|{final.exists()}"
    if REDO or not wav.exists() or meta.get(lid, {}).get('key') != src_key:
        if final.exists():                       # 正式配音：只切静音，不变速
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(final), '-af', f'{TRIM},areverse,{TRIM},areverse', '-ar', '48000', '-ac', '1', str(wav)], check=True)
            words = asr_words(wav)
        else:                                    # 临时配音：edge-tts
            mp3 = D / 'voice' / f'{lid}.edge.mp3'; words = asyncio.run(edge(ln.get('say', text), mp3))
            lead = lead_silence(mp3)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(mp3), '-af', f'{TRIM},areverse,{TRIM},areverse', '-ar', '48000', '-ac', '1', str(wav)], check=True)
            words = [[w, s - lead, e - lead] for w, s, e in words]
        meta[lid] = {'key': src_key, 'words': words}
    elif ASR:
        meta[lid]['words'] = asr_words(wav)
    if not NOSNAP and not meta[lid].get('asr'):
        meta[lid]['words'] = asr_words(wav); meta[lid]['asr'] = True     # 临时配音也用 ASR 重对一遍（edge-tts 的边界整体偏晚）
    d = dur(wav); tm = char_times(text, meta[lid]['words'])
    if not NOSNAP: tm = snap(wav, tm)
    beats.append({'id': lid, 'text': text, 'start': round(t, 4), 'end': round(t + d, 4), 'wav': f'voice/{lid}.wav',
                  'chars': [[c, round(t + x, 4)] for c, x in zip(text, tm)]})
    t += d + ln.get('gap', .35)
    if 'bite' in ln:                              # 这句后面插原声
        bt = ln['bite']; t += bt.get('pre', .15) - ln.get('gap', .35); t0 = t; parts = []
        for src, a, l, sub, g in bt['parts']:
            parts.append({'src': src, 'in': a, 'dur': l, 'gain_db': g, 'start': round(t, 4), 'end': round(t + l, 4), 'sub': sub}); t += l
        inserts.append({'id': f'bite_{lid}', 'after': lid, 'start': round(t0, 4), 'end': round(t, 4), 'parts': parts}); t += bt.get('post', .4)
    if S.get('title', {}).get('after') == lid:
        title = {'start': round(t, 4), 'end': round(t + S['title']['len'], 4)}; t += S['title']['len']
meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), 'utf-8')
tl = {'fps': 30, 'duration': round(t + S.get('tail', .95), 4), 'aspect': S.get('aspect', '16:9'), 'pre': S.get('pre', 0.0), 'title': title, 'beats': beats, 'inserts': inserts}
(D / 'timeline.json').write_text(json.dumps(tl, ensure_ascii=False, indent=1), 'utf-8')
for b in beats: print(f"{b['id']:6s} {b['start']:7.2f}–{b['end']:6.2f}  {b['text'][:28]}")
for i in inserts: print(f"{i['id']:6s} {i['start']:7.2f}–{i['end']:6.2f}  原声 {len(i['parts'])} 段")
print('总长', tl['duration'], '秒；片名', title)
