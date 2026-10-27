#!/usr/bin/env python3
"""豆包语音合成（火山引擎 V3 HTTP 单向流）示例。key 放在环境变量 VOLC_TTS_KEY。
接入本 skill：
  python config.py set voice.provider command
  python config.py set voice.out_ext mp3
  python config.py set voice.command "python <skill>/scripts/tts_examples/doubao.py {text_file} {out}"
单独用：python doubao.py "文本或文本文件" out.mp3 [--speaker zh_male_dayi_uranus_bigtts] [--speed 0]"""
import argparse, base64, json, os, sys, urllib.request
p = argparse.ArgumentParser()
p.add_argument("text"); p.add_argument("out")
p.add_argument("--speaker", default="zh_male_dayi_uranus_bigtts")
p.add_argument("--speed", type=int, default=0, help="speech_rate -50..100，0 是正常语速")
p.add_argument("--resource", default="seed-tts-2.0")
a = p.parse_args()
text = open(a.text, encoding="utf-8").read().strip() if os.path.isfile(a.text) else a.text
key = os.environ.get("VOLC_TTS_KEY") or sys.exit("没有环境变量 VOLC_TTS_KEY")
body = {"user": {"uid": "bighead-collage"}, "req_params": {"text": text, "speaker": a.speaker,
        "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": a.speed}}}
req = urllib.request.Request("https://openspeech.bytedance.com/api/v3/tts/unidirectional", data=json.dumps(body).encode(),
                             headers={"x-api-key": key, "X-Api-Resource-Id": a.resource, "Content-Type": "application/json"})
audio = bytearray()
with urllib.request.urlopen(req, timeout=300) as r:
    for line in r:
        line = line.strip()
        if not line: continue
        j = json.loads(line)
        if j.get("data"): audio += base64.b64decode(j["data"])
        elif j.get("code") not in (0, 20000000): sys.exit(f"TTS 出错：{j}")
if not audio: sys.exit("没有返回音频")
open(a.out, "wb").write(audio); print(a.out, len(audio), "bytes")
