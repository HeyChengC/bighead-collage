# -*- coding: utf-8 -*-
"""环境自检：做片之前跑一遍，缺什么、怎么装，逐条列出来。

  python doctor.py            # 按 config.json 里选的配音 / 生图方式检查
  python doctor.py --all      # 所有方式都查
"""
import importlib, json, os, shutil, subprocess, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = Path(__file__).resolve().parent; SKILL = HERE.parent
sys.path.insert(0, str(HERE))
import config

ALL = "--all" in sys.argv
cfg = config.load(); vp, ip = cfg["voice"]["provider"], cfg["image"]["provider"]
bad, warn = [], []


def ok(msg): print("  ✓", msg)
def no(msg, fix): print("  ✗", msg, "\n      →", fix); bad.append(msg)
def maybe(msg, fix): print("  !", msg, "\n      →", fix); warn.append(msg)


def run(args):
    try: return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except Exception: return None


print("设置：", config.path(), "" if config.exists() else "（还没有 config.json，用的是默认值；第一次做片时 skill 会问你）")
print(f"  配音方式 voice.provider = {vp}；生图方式 image.provider = {ip}\n")

print("基础")
if sys.version_info >= (3, 9): ok(f"Python {sys.version.split()[0]}")
else: no(f"Python {sys.version.split()[0]} 太旧", "装 Python 3.10 以上")
for exe in ("ffmpeg", "ffprobe"):
    ok(exe) if shutil.which(exe) else no(f"找不到 {exe}", "装 ffmpeg 并加进 PATH（Windows：winget install ffmpeg；macOS：brew install ffmpeg）")
node = shutil.which("node")
if node:
    r = run([node, "-v"]); ver = (r.stdout.strip() if r else "?")
    ok(f"Node {ver}") if ver.startswith("v") and int(ver[1:].split(".")[0]) >= 18 else no(f"Node {ver} 太旧", "装 Node 18 以上")
    js = ("const {createRequire}=require('module');const fs=require('fs');"
          "for (const t of [process.env.PLAYWRIGHT_FROM, process.argv[1]+'/package.json', process.cwd()+'/package.json'].filter(Boolean)) {"
          "try{const pw=createRequire(t)('playwright');const p=pw.chromium.executablePath();console.log(fs.existsSync(p)?'OK':'NOBROWSER');process.exit(0)}catch(e){}}console.log('NOPW')")
    r = run([node, "-e", js, str(SKILL)]); st = r.stdout.strip() if r else "NOPW"
    if st == "OK": ok("playwright + chromium")
    elif st == "NOBROWSER": no("playwright 装了，浏览器没装", f"cd \"{SKILL}\" && npx playwright install chromium")
    else: no("找不到 playwright（逐帧渲染要用）", f"cd \"{SKILL}\" && npm install && npx playwright install chromium")
else:
    no("找不到 node", "装 Node.js 18 以上（https://nodejs.org）")

print("\nPython 包")
need = [("numpy", "numpy"), ("scipy", "scipy"), ("PIL", "pillow"), ("cv2", "opencv-python"), ("librosa", "librosa"),
        ("soundfile", "soundfile"), ("faster_whisper", "faster-whisper"), ("rembg", "rembg[cpu]"), ("onnxruntime", "onnxruntime")]
if vp == "edge" or ALL: need.append(("edge_tts", "edge-tts"))
if ip == "openai" or ALL: need.append(("openai", "openai"))
miss = []
for mod, pkg in need:
    try: importlib.import_module(mod); ok(pkg)
    except Exception: miss.append(pkg); print("  ✗", pkg)
if miss:
    bad.append("缺 Python 包"); print("      → pip install -r \"" + str(SKILL / "requirements.txt") + "\"")
try:
    import ctranslate2
    n = ctranslate2.get_cuda_device_count()
    ok(f"语音识别用 GPU（{n} 块）") if n else maybe("没有可用的 GPU：语音识别走 CPU，会慢",
        "设环境变量 WHISPER_MODEL=small（或 medium）换小模型；默认 large-v3 第一次会下载约 3GB")
except Exception:
    pass

print("\n配音")
if vp == "edge" or ALL:
    ok("edge-tts：免费，需要能连上微软的语音服务") if shutil.which("edge-tts") or "edge-tts" not in miss else None
if vp == "command" or ALL:
    c = cfg["voice"].get("command")
    ok(f"自定义 TTS 命令：{c}") if c else (no("voice.provider=command 但没写命令", 'python config.py set voice.command "python tts.py {text_file} {out}"') if vp == "command" else None)
if vp == "recording": ok("用整条录音：python voice_timeline.py <配音文件>")

print("\n生图")
if ip == "codex" or ALL:
    cx = shutil.which("codex")
    if cx:
        r = run([cx, "login", "status"]); s = ((r.stdout or "") + (r.stderr or "")).strip() if r else ""
        ok(f"codex（{s.splitlines()[0] if s else '已安装'}）")
    elif ip == "codex": no("找不到 codex", "npm i -g @openai/codex，然后 codex login（用 ChatGPT 账号登录）")
if ip == "openai" or ALL:
    o = cfg["image"]["openai"]; envk = o.get("api_key_env") or "OPENAI_API_KEY"
    if os.environ.get(envk) or o.get("base_url"): ok(f"OpenAI 图像接口：模型 {o.get('model')}，地址 {o.get('base_url') or '官方'}")
    elif ip == "openai": no(f"没有环境变量 {envk}", f"设置 {envk}=你的 key；兼容服务再 python config.py set image.openai.base_url <地址>")
if ip == "command" or ALL:
    c = cfg["image"].get("command")
    ok(f"自定义生图命令：{c}") if c else (no("image.provider=command 但没写命令", 'python config.py set image.command "..."') if ip == "command" else None)
if ip == "manual": ok("手动生图：gen_image.py 会把提示词写进 PROMPTS.md，你生成后按文件名放回来")

fonts = [f for f in ("Anton-Regular.ttf", "NotoSansSC-VF.ttf", "SmileySans-Oblique.ttf") if not (HERE / "fonts" / f).exists()]
print("\n字体"); ok("三款字体都在") if not fonts else no(f"缺字体 {fonts}", "重新下载这个 skill 的 scripts/fonts/")

print("\n" + ("全部通过，可以开工。" if not bad else f"有 {len(bad)} 项要先处理。") + (f"（{len(warn)} 条提醒）" if warn else ""))
sys.exit(1 if bad else 0)
