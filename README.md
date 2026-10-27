# 大头拼贴（bighead-collage）

给 AI Agent（Claude Code、Codex 等）用的 Skill：**你给选题和文案，它做出一条 9:16 竖屏的大头拼贴人物故事短片。**

主角是放大了头的真人照片剪纸，站在代表他处境的小舞台上；数字是他举着的牌子、黑板上敲出来的字，关键词是贴条；每 0.4–0.6 秒一个画面事件，卡在配音的字上；镜头大起大落，换场时总有一样东西跟着过去；几乎每个动作配一个短音效。适合讲「一个大人物的一件反常事」或「一个人的一生」，15–60 秒。

![用这个 skill 做出来的画面](anchors/own_taste_board.jpg)

同一个题目、同一段配音，不用 skill（左）和用 skill（右）：

![不用 skill vs 用 skill](anchors/own_gap_pairs.jpg)

---

## 它会替你做什么

| 步骤 | 内容 |
|---|---|
| 配音 | 逐句配音（默认 edge-tts，免费），语音识别逐字对齐，画面卡在每个字真正发声的那一刻 |
| 导演表 | 每一镜屏上是什么、观众多懂了什么、凭什么接上一镜；每个动作从哪进、怎么走、怎么离场 |
| 素材 | 照着主角的照片直接生成大头全身像，场景和道具也生成，自动抠图 |
| 画面 | 网页引擎逐帧渲染：小舞台、曲线运镜、贴条字、字幕轨、9:16 平台安全区 |
| 声音 | 从画面自动导出音效表，合成音效和垫乐，混音到 -14 LUFS |
| 自查 | 出片前十项自查：看不看得懂、卡没卡字、音画对齐、大头接缝、平台界面遮挡…… |

你要做的：**给选题（或文案）、确认文案、看样片提意见。**

---

## 安装

需要：Python 3.10+、Node.js 18+、ffmpeg。

```bash
# 1. 放进 Agent 的 skills 目录（Claude Code 是 ~/.claude/skills/）
git clone https://github.com/HeyChengC/bighead-collage ~/.claude/skills/bighead-collage
cd ~/.claude/skills/bighead-collage

# 2. 依赖
pip install -r requirements.txt
npm install
npx playwright install chromium

# 3. 自检：缺什么会告诉你怎么装
python scripts/doctor.py
```

或者把这句话发给你的 Agent，让它帮你装：

```text
请帮我安装这个 skill：https://github.com/HeyChengC/bighead-collage，克隆到我的 skills 目录，按 README 装好 Python 和 Node 依赖，最后运行 scripts/doctor.py 确认全部通过。
```

> 没有 NVIDIA 显卡也能用，语音识别会走 CPU，慢一些。可以设环境变量 `WHISPER_MODEL=small` 换小模型（默认 large-v3，第一次运行会下载约 3GB）。

---

## 使用

在 Agent 里直接说：

```text
用大头拼贴风做一个《芒格的一生》，竖屏 40 秒左右
```

```text
大头剪贴风：讲讲西尔斯是怎么在亚马逊之前一百年就做了网购的
```

第一次用时它会问你两件事，答完会记住，以后不再问：

**配音怎么来**

| 选项 | 说明 |
|---|---|
| edge-tts（默认） | 免费、不用注册，音色可换（`zh-CN-YunxiNeural` 等） |
| 自己的整条录音 | 给它一个 mp3/wav，它自己切句、逐字对齐 |
| 接你自己的 TTS | 豆包、ElevenLabs、MiniMax、本地模型都行，给一条命令即可，示例见 `scripts/tts_examples/` |

**图怎么生成**

| 选项 | 说明 |
|---|---|
| codex | 本机 codex CLI 自带的生图，走 ChatGPT 订阅额度 |
| OpenAI 图像接口 | 官方或任何兼容服务（填 `base_url`），需要 key |
| 你自己的命令 | 任何能「输入提示词、输出图片」的命令行 |
| 手动 | 它只给你提示词清单（`gen/PROMPTS.md`），你用任何工具生成，按文件名放回来 |

以后想换，跟 Agent 说一声，或者自己改：

```bash
python scripts/config.py                              # 查看
python scripts/config.py set image.provider codex
python scripts/config.py set voice.edge_voice zh-CN-YunyangNeural
```

---

## 目录

```
SKILL.md              Agent 读的说明：开工前、流程、每一镜问自己的八句、度、拒绝
style-card.md         风格判断 15 节，每条带参考片时间点
references/
  mapping.md          每类话怎么变成实物在动
  engine.md           渲染引擎 stage.js：场、相机、字、转场、字幕
  production.md       素材、配音、音效、渲染、样片前自查、交片
  taste.md            作者看样片时定下的口味规则
examples/
  munger-life/        《芒格的一生》：导演表、近失对、运镜曲线
  hardcases-01/       《商业狠人图鉴 01》：动作分镜、舞台调度、注意力层级
anchors/              好在哪 / 坏成什么样 的对照图
scripts/              引擎、配音、生图、抠图、音效、混音、渲染、自查工具
```

---

## 常见问题

- **Windows 下中文打印成乱码**：先设 `PYTHONIOENCODING=utf-8`，文件本身没坏。
- **生图画得不像本人**：大头要用一张清楚的正脸照片做参考；还不行时，`production.md` 里有拼接的备用方案。
- **生成的图里有网址、logo**：重画或遮掉，成片里不能出现。
- **真人肖像**：片子里的人物形象是 AI 照着照片生成的，发布时请注明「AI 生成」，并遵守平台对真人内容的规定。

---

## 引用说明

- 这个风格学自 Instagram / TikTok 账号 **earn.edits**（[earnedits.com](https://earnedits.com)）的两条短片：《巴菲特囤现金》和《西尔斯邮购目录》。`anchors/taste_board.jpg`、`anchors/gap_pairs.jpg`、`anchors/detail.jpg` 里有这两条片的截帧，`style-card.md` 里引用了它们的时间点，仅用于说明风格、学习研究。版权归原作者所有。**如有侵权，请在 [Issues](https://github.com/HeyChengC/bighead-collage/issues) 联系，我们会立即删除。**
- 示例片子里芒格、巴菲特的脸参考了维基共享资源的照片（CC BY 2.0 / CC BY-SA 2.0），人物形象由 AI 生成。
- 字体：Anton、思源黑体（Noto Sans SC）、得意黑（Smiley Sans），均为 SIL Open Font License 1.1，协议见 `scripts/fonts/`。
- 人脸检测模型 `scripts/face_yunet.onnx` 来自 [OpenCV Zoo](https://github.com/opencv/opencv_zoo)（YuNet，MIT）。

## 协议

代码和文档：MIT（见 `LICENSE`）。字体、第三方截帧和模型按上面各自的协议。
