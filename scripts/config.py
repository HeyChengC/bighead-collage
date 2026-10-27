# -*- coding: utf-8 -*-
"""读写这个 skill 的本机设置：配音怎么来、图怎么生成。

设置文件按顺序找：环境变量 BIGHEAD_CONFIG 指向的文件 → <skill>/config.json。
没有就用默认值（配音 edge-tts，生图 manual：只写提示词，你自己生成后放进来）。

  python config.py                         # 看当前设置
  python config.py set voice.provider edge
  python config.py set image.provider openai
  python config.py set image.openai.model gpt-image-1
  python config.py set image.command "python my_gen.py --prompt-file {prompt_file} --out {out} {refs}"
"""
import json, os, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent

DEFAULT = {
    "voice": {
        "provider": "edge",                 # edge | recording | command
        "edge_voice": "zh-CN-YunxiNeural",  # edge-tts 的音色（edge-tts --list-voices 看全部）
        "rate": "+5%",
        "command": "",                      # provider=command：每句调用一次，{text} {text_file} {out} 会被替换
        "out_ext": "wav",                   # 你的 TTS 输出的格式（wav / mp3 …），{out} 会用这个扩展名
    },
    "image": {
        "provider": "manual",               # codex | openai | command | manual
        "parallel": 4,
        "codex": {"timeout": 1200},
        "openai": {"model": "gpt-image-1", "base_url": "", "api_key_env": "OPENAI_API_KEY",
                   "size": "1024x1536", "quality": "high"},
        "command": "",                      # provider=command：{prompt} {prompt_file} {out} {refs} 会被替换
    },
}


def path():
    return Path(os.environ["BIGHEAD_CONFIG"]) if os.environ.get("BIGHEAD_CONFIG") else SKILL / "config.json"


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return out


def load():
    p = path()
    if p.exists():
        return _merge(DEFAULT, json.loads(p.read_text("utf-8")))
    return json.loads(json.dumps(DEFAULT))


def exists():
    return path().exists()


def save(cfg):
    path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")


def set_key(dotted, value):
    cfg = load(); cur = cfg; keys = dotted.split(".")
    for k in keys[:-1]: cur = cur.setdefault(k, {})
    try: value = json.loads(value)
    except Exception: pass
    cur[keys[-1]] = value; save(cfg); return cfg


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "set":
        set_key(sys.argv[2], sys.argv[3])
    print("设置文件：", path(), "（已存在）" if exists() else "（还没有，下面是默认值）")
    print(json.dumps(load(), ensure_ascii=False, indent=2))
