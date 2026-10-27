# 制作：素材、配音、音效、渲染、交片

所有命令在工程目录里跑；`S=` 指这个 skill 的 `scripts/`。开工前先 `python $S/doctor.py`，配音和生图方式见 SKILL.md「开工前」（`python $S/config.py` 查看）。

## 0 建工程

```bash
python $S/new_film.py film        # index.html、a/（引擎、样式、字体）、scene.js、script.json、img/、sfx/
```

## 1 文案和配音

`script.json`：`"aspect": "9:16"`；每句一个 id；`say` 是只给 TTS 读的写法（年份读成"一九二八年"），屏上用 `text`。句间 `gap` 0.2s，**段落之间 0.35–0.55s**（参考片句间只停 0.1–0.2s，但那是英文母语观众；中文观众要时间看完上一件事）。

配音从哪来看 `voice.provider`：

| provider | 做法 |
|---|---|
| `edge`（默认） | `temp_voice.py` 用 edge-tts 逐句配音。音色、语速在 `voice.edge_voice` / `voice.rate`（script.json 里写 `voice` / `rate` 优先）。常用：`zh-CN-YunxiNeural`（男，讲故事）、`zh-CN-YunyangNeural`（男，播音）、`zh-CN-XiaoxiaoNeural`（女）；`edge-tts --list-voices` 看全部 |
| `command` | `temp_voice.py` 每句调一次 `voice.command`（`{text_file}` `{out}` 会被替换），产出 `voice/<id>.final.wav` 再逐字对齐。示例：`scripts/tts_examples/doubao.py`、`openai_tts.py` |
| `recording` | 用户给的整条录音：`voice_timeline.py`（见下） |

任何一句手动放进 `voice/<id>.final.wav`，都会替代那句的 TTS。

```bash
python $S/temp_voice.py script.json     # 逐句配音 + 逐字时间 → timeline.json、voice/*.wav
                                        # 默认每句用 ASR 逐字对齐再吸附到起音：edge-tts 自报的字时刻整体晚 ~0.23s，不对齐画面会全片慢半拍
```

中文 4.5–5 字/秒：30 秒 ≈ 130 字（留出段落停顿）。不要加速（atempo）。

- 屏上写阿拉伯数字、配音读中文时：逐位读的（1928 → 一九二八）`at()` 能对上；不是逐位读的（34 → 三十四），屏上就直接写中文，或者用 `beat(id).start` 手动取。
- **用户给了一整条正式配音**（mp3/wav，不切不变速）：`script.json` 按句写好文案，`python $S/voice_timeline.py 配音.mp3` → `voice/main.wav` + `timeline.json`（整条 ASR 逐字对齐 + 吸附起音，`voice_track` 指向整条，mix.py 整条用）。会打印对不上的字（ASR 把"那儿"听成"哪"之类），按前后插值。
- **配音和时间线是别人给的**（考卷、正式配音）：把对方的 `timeline.json` 和 `voice/` 拷进工程，在 timeline.json 里补 `"aspect": "9:16"`（frames.mjs 读的是 timeline.json，不是 script.json），跳过 temp_voice。
- Windows 下 python 打印中文是乱码时，先 `export PYTHONIOENCODING=utf-8`；文件本身没坏。
- 自己用 python 写 timeline.json / script.json 时写明 `encoding='utf-8'`：Windows 默认按 GBK 写，浏览器能读、mix.py 会读崩。

## 2 素材

### 主角（大头）

1. 找一张可授权的真人照片（维基共享资源 CC BY / 公有领域）当脸的参考，记进 `SOURCES.txt`。半身、坐着、背景乱都可以，它只管脸像。
2. **大头直接生图，一张图画出大头小身子的整个人，不拼接**。头和身体本来就是同一张照片，脖子自己长出来，没有接缝（对临 v1 用 bighead.py 拼，用户只挑出这一处："开头巴菲特的头和身体融合的很不好"；改成直出后一次过）：
   ```bash
   cd gen && python $S/gen_image.py "hero_big.png|A photorealistic bobblehead photo caricature of the same man as in image 1 (keep his exact face, glasses, hair, age). Extreme big-head proportions: the head from crown to chin is about 40 percent of the whole figure height, the head is wider than his shoulders, and the body below is short and stocky with short legs, like a bobblehead figurine but photographed as a real person. Head and body are ONE continuous real photograph: the huge head sits directly on the shirt collar, consistent lighting and skin, no seam, no cut-out edge, no thin neck. Body facing the camera, <姿势>, <衣服>, <表情/嘴型>. Natural soft frontal studio light, sharp real-photo detail, not a cartoon, not 3D render. Full figure from top of hair to shoes inside the frame with generous margin. Portrait 1024x1536. Background perfectly flat pure white #FFFFFF, no shadow, no text, no logos.|ref.jpg"
   ```
   比例要写狠：写"头约占 1/3"出来只有 27%，写"40%、比肩宽、身子矮壮"出来 39%。比例不够就把上一张当图 2 再要"更夸张"，一轮出两张挑。生出来先看：脸像不像本人、朝向和嘴型对不对、头占全身 30–40%。
3. 抠图：`python $S/cutout.py hero_big.png img/hero_big.png --anchor`（同名 `.json` 写 feet/size/top，坐标是输出 PNG 自己的像素，`person()` 按它让脚踩在地上）。放在对比色底上看一眼头发边。人物身高占画面高的 45–65%。要黑白版（"处境变坏"那场）就在生图提示词里写 black-and-white photo 再出一张。
4. 要不同姿势（举牌、指、抱臂）就各生成一张。姿势每 10 秒至多一个：30 秒的片 2–3 个。
   **备用**：生图画不像本人（脸走样）时，才退回拼接：先生成全身站立白底照（正脸，侧脸做大头下颌线是猜的），再 `python $S/bighead.py hero_body.png img/hero_big.png --scale 2.6 [--gray]`，按镜头推得最近时的大小看下巴和领口的接缝。
5. 照片生成的相像在交片说明里写"AI 生成"。

### 舞台和道具

- **底**：有触感的平面（皱纸、灰泥墙、切割垫、方格纸、云天）。直接生成 9:16 整图。
- **小世界**（浮空小镇、平板屏幕、桌面）：生成"微缩模型 / 移轴摄影"质感，纯白底，抠出来。
- **道具**（钞票、黑板、手、邮筒、目录卡、金币）：写实单品，纯白底，抠出来。手要单独生成（从画面边伸进来的那种角度）。
- 提示词公式：`<物件>, photorealistic product photo, <角度：top-down / 3/4 view / front>, soft studio light, isolated on perfectly flat pure white #FFFFFF background, no shadow, no text, no logos.`
- **一张图里放几件道具**：同一场的小道具（钞票、硬币、眼镜、徽章……）可以几件摆在一张白底图里一起生成（提示词写明 "N separate objects, well spaced apart, not touching"），再 `python $S/split_sheet.py gen/sheet.png img/a.png img/b.png img/c.png [--white]` 按连通区域切开（从左到右、从上到下编号）。切开以后逐件看：哪件糊了、被裁了、和别的粘在一起，那件单独重画。人物、底图、要占大画面的道具还是单张生成。
- 抠图：`python $S/cutout.py gen/x.png img/x.png --w 1200`（rembg 出轮廓 → 填洞 → 颜色取回原图）。直接用 rembg 的结果，钞票、白纸、键盘这类浅色物件会半透明，透出底下的东西；黑板、深色物件 rembg 常把物件本身当背景抠掉，加 `--white` 按"不是白的就是物件"抠。抠完放在对比色底上看一眼（对临 v1 时钞票透出洋红、黑板透出蓝墙，都是这样发现的）。
- 云：生成在纯黑底上，用亮度当透明度（不要用 rembg 抠云）。
- 生图一律在 `gen/` 里跑 `python $S/gen_image.py "名字.png|提示词|参考图1,参考图2" …`（或 `--jobs jobs.json` 一次给一批），按 `image.provider` 选方式：
  | provider | 说明 |
  |---|---|
  | `codex` | 本机 codex CLI 自带生图，走 ChatGPT 订阅额度；每张 1–3 分钟，`image.parallel` 张并行（默认 4） |
  | `openai` | OpenAI 图像接口或兼容服务：`image.openai.model`（默认 gpt-image-1）、`base_url`、`api_key_env`；有参考图走 images.edit |
  | `command` | `image.command` 里的 `{prompt}` `{prompt_file}` `{out}` `{refs}` 被替换后执行，跑完 `{out}` 要存在 |
  | `manual` | 只把提示词写进 `gen/PROMPTS.md`，告诉用户按文件名生成好放进 `gen/`，放好后再跑一遍同一条命令确认（缺图时退出码 2） |
  一条 30 秒的片 10–14 张生图：一场一个底 + 一两件道具。
  - 要后台跑，就交给你的工具的"后台运行"，**不要自己在命令后面加 `&`**，跑完 `ls` 一下再用。
  - 同名文件已存在会跳过（`FORCE=1` 才重画），所以重发不会覆盖。生图预算按"入片的张数"算，重画的不算，但要在交片说明里写。
  - 出图尺寸不一定是提示词里写的，排版前读实际尺寸（PIL 的 `Image.open(f).size`）。
- 画面里不能有网址、品牌 logo（生图常会画上去，看到就重画或遮掉）。

## 3 画面

先静帧，后整片：

```bash
node $S/frames.mjs --dir . --stills 0.5,2,4.5 --h 960     # out/still_*.png
node $S/frames.mjs --dir . --video --h 1280               # 预览（720×1280）
node $S/frames.mjs --dir . --video --h 1920               # 成片画面（1080×1920，无声）
```

量数在第 6 节"样片前自查"里一起做。

### 9:16 平台安全区（发抖音的竖屏片）

发布后界面会盖住画面的几块（1080×1920，抖音的近似值；别的平台改 `ui_check.py` 里的 `ZONES`）：

| 区域 | 范围 | 放什么 |
|---|---|---|
| 顶部标签栏 | y < 160 | 不放字 |
| 右侧按钮列（头像、点赞、评论、分享） | x > 940，y 820–1560 | 不放数字、关键词、主角的脸；装饰、人群边缘可以 |
| 底部账号、标题、音乐 | y > 1560（左侧 0–900） | 不放字幕和关键信息；脚、地面可以 |

- 字幕 y≈1400（`captions()` 默认）；关键词、数字、牌、清单都在字幕之上、按钮列之左。
- 整场构图偏低时不逐个挪东西，**整场相机往上抬**（例：图鉴 01 牌桌 `cam.y + 200`；推到脸、推向某张牌那几下抬回 0，保证对准）。
- 前景字（depth > 1）有视差：相机抬 100，它抬得比人多。原话、大字放在顶部时要单独看一眼有没有进标签栏。
- 两个人站一排（结尾对话）时，算好右边那个不进按钮列；宁可少推一点。

```bash
python $S/ui_check.py final.mp4 ui_check.jpg --every 2     # 每 2 秒一帧，红框 = 界面会盖住的地方
```

## 4 声音

```bash
python $S/sfx.py kit sfx                       # 合成一套音效（flick pop click key whoosh whip swish thud ding shutter pencil coin car）
python $S/sfx.py bed sfx/bed.wav <总长秒数> --bpm 76     # 慢的合成器垫乐（参考片约 76 BPM，只铺底；快了会和说话抢节奏）
node $S/sfxlist.mjs --dir . --bed bed.wav --bed-gain -17    # 从画面导出音效表 → sfx.json（可再加 sfx_extra.json）；会打印每分钟几个，参考片约 120
python $S/mix.py . --check                     # → mix_master.wav（-14 LUFS），人声压着配乐
```

- 音效峰值：跳字 -24、贴条 -22、圆圈/换场 -22、甩镜 -20、重物 -18；人声永远比音效高 7 dB 以上。
- 合成的音效和配乐是临时的，好不好听要人听。

## 5 合成

```bash
ffmpeg -i out/visual_1920.mp4 -i mix_master.wav -map 0:v -map 1:a -c:v libx264 -crf 21 -pix_fmt yuv420p   -af "loudnorm=I=-13.5:TP=-1.5:LRA=11" -ar 48000 -c:a aac -b:a 192k -shortest final.mp4
# mix.py 出来真峰值可能到 -0.9，直接合会被 verify 判不过；这一道 loudnorm 同时把响度和峰值都放进范围。
# 颗粒让画面很难压，crf 21 时 25 秒约 60MB；-c:v copy 会到 150MB 以上。
```

## 6 样片前自查（给用户看之前，十项都过）

用户在《芒格的一生》上一轮一轮替我们发现了这些，每一项都值一轮返工。
**这张表就是这个风格的回归测试**：每条真片都跑，打回重做的下一版也跑；用户再指出新问题，就在表里加一行（查什么、怎么查、过关）。不另外重做旧片或考卷来验证改动。`vsr.py` 也在 `$S` 里（量换场、运镜曲线、平涂占比、帧条）。

```bash
python $S/verify.py final.mp4 --expect 1080x1920 --dur <秒>      # 工艺硬项：时长、响度、真峰值、黑帧、冻帧
python $S/verify.py --sync . --from final.mp4                    # 音画对齐：从成片的声音量，画面排字的时刻 − 听出来的时刻，中位 ±100ms 内
python $S/vsr.py ingest final.mp4 mine && python $S/vsr.py scenes mine && python $S/vsr.py flow mine && python $S/vsr.py camcurve mine && python $S/vsr.py texture mine
```

| # | 查什么 | 怎么查 | 过关 |
|---|---|---|---|
| 1 | 看得懂 | 关掉声音，对着导演表逐个换场说"上一镜的什么带到了下一镜、为什么换" | 每个换场都说得出；说不出的改成带过或删掉 |
| 2 | 段落停顿 | 看 `timeline.json` 段落之间的空白 | 0.35–0.55s |
| 3 | 运镜形状 | 打开 `sheets/mine_camcurve.png`；讲事的段落对着 `timeline.json` 看关键词出现后镜头停没停 | 大起伏、平滑过零、中间有停；平线加转场处的尖刺 = PPT。推拉幅度 55–80%/s 是全片的数，主要由开头和转场撑起来；讲事的段落里关键词出现后至少 0.6 秒镜头几乎不动，没有 1.0→1.1→1.02 式的小抽动（图鉴 01 v4.1：65%/s、几乎不动 37%） |
| 4 | 卡点 | 每个换场的时刻对 `timeline.json`：落在新画面要演的那个词上 | 不在两句之间的停顿里 |
| 5 | 音画对齐 | `verify.py --sync` | 中位 ±100ms |
| 6 | 层级和穿帮 | 每个转场 0.1s 一帧看（`vsr.py strip mine <起> <止> 10`） | 主角不消失、没有整屏空底色、元素没被压到下面 |
| 7 | 大头 | 找镜头离主角最近的那一帧，截原尺寸看下巴和领口；量头占全身多少 | 头和身体是同一张照片（直接生图），看不到切边、细脖子、蛋形下巴；头占全身 30–40% |
| 8 | 物件和人物的动作 | 每个事件前后 0.4s 按 0.05s 一帧排成帧条看，再放一遍视频（静帧拼图只能查构图，看不出动作） | 没有"从零放大弹出来"、直线滑到位就不动、凭空消失；每次进场有方向、加减速和到位后的余震；主角每 2–3 秒有一次表演变化；文案里提到的人都上场了 |
| 9 | 阅读面 | 每一拍暂停一帧，说出"现在该看哪"；数一下画面里还留着几样上一件事的东西，各自说得出为什么还在。讲事的段落每 0.5 秒一帧，说出眼睛落在哪 | 每一拍只有一个焦点；留下的东西要么在账本位（会积累的那一排），要么是主角；说不出理由的，回导演表改调度（不是直接删）。眼睛落在"一个动作"（飞的纸、震的屏、甩的镜头）而不是"这句话讲的事"＝特效盖住了内容：去掉不讲内容的装饰和镜头小抽动，压暗繁忙的底，放大人和数字；开头钩子不按这条减 |
| 10 | 平台遮挡 | `python $S/ui_check.py final.mp4 ui_check.jpg --every 2`（9:16 发抖音的片） | 字幕、关键词、数字、清单、主角的脸都不在红框里（第 3 节"9:16 平台安全区"）；字幕每条不超过 14 字，字号 62 在手机上看得清 |

另外：平涂占比 ≤ 0.42（高了说明画面太平、像矢量）；停住 >2s 为 0。

## 7 交片

预览和成片放 `看这里/`（中文编号），**用播放器直接打开给用户**；说明里写成片在哪、做了什么、哪条没做到、哪些我没法验证（声音、大头会不会冒犯）。素材来源写进 `SOURCES.txt`。

## 8 对临：照着参考片整条复刻

用户说"复刻一下参考片，看像不像"时用。比的只有画面和音效，其余照原片（对临 v1 这样做：换场 9 处 7 处差 ≤0.1s，整体互相关偏移 0 帧）。

1. **配音用原片人声**：`python $S/vsr.py sep <代号>` 分出人声，拷进 `voice/`；`python $S/vsr.py asr <代号>` 出词级时间，再
   `python $S/ref_timeline.py <vsr 工作目录>/data/<代号>.words.json voice/<代号>_vocals.wav <秒数> > timeline.json`。
   timeline.json 里写了 `voice_track`，mix.py 整条用这个人声，不再按句拼。
2. **时刻按原片逐帧量**：`vsr.py strip` 0.1s 一格，换场附近 0.05s 一格，量到的时刻写成 scene.js 顶上的一张表。whisper 的词边界会粘连（v1 的 "in" 被给了 0.86s），`at()` 只当参考。
3. **版面按原片的一帧量**：每一场选原片一帧当"版面帧"（相机 z=1），位置、大小按它量（`vsr.py grid` 原尺寸 + 刻度），在场的注释里写明是哪一帧。镜头的 z 用同一个物件在两帧里的大小之比算，不要从 camcurve 读：整屏大物件扫过、暗底低纹理时 camcurve 量不准。
4. **每一轮三样对照再改**：同一时刻对照表（`vsr.py compare`）、换场前后 0.05s"原片在上、复刻在下"的帧条（`vsr.py tstrip`）、整体时间对齐（`vsr.py xcorr`，最佳偏移 0 帧、分段偏移 ≤0.1s 算过）。再并排看 camcurve 的形状。
5. **交片**：成片 + 左右并排视频（原片 | 复刻，两条音轨：复刻的声音 / 原片声音，播放器里可切）+ 同一时刻对照表。并排视频用播放器直接打开。
6. 原片的人物照、道具图、画面不进成片；原片人声只在本机对照用，不发布。素材照片仍按第 2 节自己生成（对临 v1 的巴菲特是照真实照片生成的相像）。
