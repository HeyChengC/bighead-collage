#!/usr/bin/env python3
"""OpenAI（或兼容接口）语音合成示例。key 放在环境变量 OPENAI_API_KEY；兼容服务把地址放进 OPENAI_BASE_URL。
接入本 skill：
  python config.py set voice.provider command
  python config.py set voice.out_ext mp3
  python config.py set voice.command "python <skill>/scripts/tts_examples/openai_tts.py {text_file} {out}"
可选：TTS_MODEL（默认 gpt-4o-mini-tts）、TTS_VOICE（默认 alloy）、TTS_INSTRUCTIONS（语气要求）。"""
import os, sys
from openai import OpenAI
src, out = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read().strip() if os.path.isfile(src) else src
c = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None)
kw = dict(model=os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"), voice=os.environ.get("TTS_VOICE", "alloy"), input=text)
if os.environ.get("TTS_INSTRUCTIONS"): kw["instructions"] = os.environ["TTS_INSTRUCTIONS"]
with c.audio.speech.with_streaming_response.create(**kw) as r: r.stream_to_file(out)
print(out)
