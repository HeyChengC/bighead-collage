# -*- coding: utf-8 -*-
"""生图：在输出目录里跑（一般是工程的 gen/），按 config.json 里 image.provider 选生成方式。

  python gen_image.py "名字.png|提示词" ["名字.png|提示词|参考图1,参考图2"] …
  python gen_image.py --jobs jobs.json          # [{"name": "...png", "prompt": "...", "refs": ["ref.jpg"]}, …]
  python gen_image.py --provider codex "…"      # 临时换一种方式

四种方式（python config.py set image.provider <名字>）：
  codex    本机 codex CLI 自带的生图（走 ChatGPT 订阅额度，不单独付费）。要先装好并登录 codex。
  openai   OpenAI 图像接口或任何兼容它的服务（image.openai.base_url 填服务地址，key 放在 image.openai.api_key_env 指的环境变量里）。
           有参考图时走 images.edit（主角大头必须带脸的参考图）。
  command  你自己的命令行：image.command 里的 {prompt} {prompt_file} {out} {refs} 会被替换，跑完 {out} 要存在。
  manual   不调用任何东西：把提示词追加到 PROMPTS.md，你拿去任何生图工具里生成，按文件名放回这个目录，再跑一遍确认。

规则：同名文件已存在就跳过（--force 或 FORCE=1 才重画，旧图挪到 _previous/）；一次最多 image.parallel 张并行。
出图尺寸不一定是提示词里写的，排版前读实际尺寸。"""
import argparse, base64, json, os, shlex, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

def q(x):
    """给 shell 用的引号：Windows 的 cmd 不认单引号。"""
    return subprocess.list2cmdline([x]) if os.name == "nt" else shlex.quote(x)


COMMON = ("Use your built-in image generation tool to create ONE image and save it in the current directory "
          "with the exact filename given. Reply with just the path.")


def jobs_from(a):
    out = []
    if a.jobs:
        for j in json.loads(Path(a.jobs).read_text("utf-8")):
            out.append((j["name"], j["prompt"], list(j.get("refs", []))))
    for spec in a.specs:
        parts = spec.split("|")
        name, prompt = parts[0].strip(), parts[1].strip()
        refs = [r.strip() for r in parts[2].split(",") if r.strip()] if len(parts) > 2 else []
        out.append((name, prompt, refs))
    return out


def run_codex(name, prompt, refs, cfg):
    exe = shutil.which("codex")
    if not exe: raise RuntimeError("找不到 codex 命令：npm i -g @openai/codex，再 codex login")
    args = [exe, "exec", "--skip-git-repo-check", "-s", "workspace-write", "--enable", "image_generation",
            f"{COMMON} Filename: {name}. {prompt}"]
    for r in refs: args += ["-i", r]
    with open(f"log_{name}.txt", "w", encoding="utf-8") as log:
        subprocess.run(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                       timeout=cfg["codex"].get("timeout", 1200))


def run_openai(name, prompt, refs, cfg):
    from openai import OpenAI
    o = cfg["openai"]
    key = os.environ.get(o.get("api_key_env") or "OPENAI_API_KEY") or "none"
    client = OpenAI(api_key=key, base_url=o.get("base_url") or None)
    kw = dict(model=o.get("model", "gpt-image-1"), prompt=prompt, size=o.get("size", "1024x1536"), n=1)
    if o.get("quality"): kw["quality"] = o["quality"]
    if refs:
        files = [open(r, "rb") for r in refs]
        try: res = client.images.edit(image=files if len(files) > 1 else files[0], **kw)
        finally:
            for f in files: f.close()
    else:
        res = client.images.generate(**kw)
    d = res.data[0]
    if getattr(d, "b64_json", None):
        Path(name).write_bytes(base64.b64decode(d.b64_json))
    elif getattr(d, "url", None):
        import urllib.request
        urllib.request.urlretrieve(d.url, name)
    else:
        raise RuntimeError("接口没返回图片")


def run_command(name, prompt, refs, cfg):
    tpl = cfg.get("command") or ""
    if not tpl: raise RuntimeError("image.command 是空的：python config.py set image.command \"...{prompt_file}...{out}...\"")
    pf = Path(f"_prompt_{name}.txt"); pf.write_text(prompt, "utf-8")
    cmd = (tpl.replace("{prompt_file}", q(str(pf))).replace("{out}", q(name))
              .replace("{refs}", " ".join(q(r) for r in refs)).replace("{prompt}", q(prompt)))
    with open(f"log_{name}.txt", "w", encoding="utf-8") as log:
        subprocess.run(cmd, shell=True, stdout=log, stderr=subprocess.STDOUT)


def run_manual(todo):
    p = Path("PROMPTS.md"); old = p.read_text("utf-8") if p.exists() else "# 待生成的图\n\n生成后按文件名放进这个目录（PNG），再跑一遍 gen_image.py 确认。\n"
    for name, prompt, refs in todo:
        if f"## {name}\n" in old: continue
        old += f"\n## {name}\n\n参考图：{', '.join(refs) if refs else '无'}\n\n```\n{prompt}\n```\n"
    p.write_text(old, "utf-8")
    print(f"手动模式：{len(todo)} 张的提示词写进了 {p.resolve()}")
    for name, _, refs in todo: print("  待放入：", name + (f"（生成时上传参考图 {', '.join(refs)}）" if refs else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", nargs="*"); ap.add_argument("--jobs"); ap.add_argument("--provider")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = config.load()["image"]; prov = a.provider or cfg["provider"]
    force = a.force or bool(os.environ.get("FORCE"))
    jobs = jobs_from(a)
    if not jobs: sys.exit(__doc__)
    todo = []
    for name, prompt, refs in jobs:
        miss = [r for r in refs if not Path(r).exists()]
        if miss and prov != "manual": print("缺参考图，跳过", name, miss); continue
        if Path(name).exists() and not force: print("跳过（已存在）：", name); continue
        if Path(name).exists():
            Path("_previous").mkdir(exist_ok=True); Path(name).rename(Path("_previous") / f"{Path(name).stem}.{int(time.time())}.png")
        todo.append((name, prompt, refs))
    if prov == "manual":
        if todo: run_manual(todo); sys.exit(2)
    else:
        fn = {"codex": run_codex, "openai": run_openai, "command": run_command}.get(prov)
        if not fn: sys.exit(f"不认识的 image.provider：{prov}（codex | openai | command | manual）")
        t0 = time.time()

        def one(job):
            name, prompt, refs = job
            try: fn(name, prompt, refs, cfg)
            except Exception as e: return name, f"失败：{e}"
            return name, "好了" if Path(name).exists() else f"失败：没生成出文件（看 log_{name}.txt）"
        with ThreadPoolExecutor(max_workers=max(1, int(cfg.get("parallel", 4)))) as ex:
            for name, st in ex.map(one, todo): print(f"{st:6s} {name}")
        if todo: print(f"{len(todo)} 张，用时 {time.time() - t0:.0f}s，方式 {prov}")
    have = sorted(p.name for p in Path(".").glob("*.png"))
    missing = [n for n, _, _ in jobs if not Path(n).exists()]
    print(f"本目录共 {len(have)} 张 png" + (f"；还缺 {missing}" if missing else ""))
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
