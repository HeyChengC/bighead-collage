// 从画面代码导出音效表：打开页面，读 window.EVENTS（stage.js 在每个跳字、转场、甩镜处登记的音效），
// 合并工程里的 sfx_extra.json（手加的：金币、汽车、灯泡……），写 sfx.json 给 mix.py。
//   node sfxlist.mjs --dir 工程 [--bed bed.wav --bed-gain -17] [--thin 0.12]
// --thin：两个音效挨得比这更近（秒）就只留响的那个，免得糊成一片（默认 0.08；薄完会打印个数，参考片约每秒 2 个）
import fs from 'node:fs/promises'; import path from 'node:path'; import http from 'node:http';
import {createRequire} from 'node:module'; import fsSync from 'node:fs'; import {fileURLToPath} from 'node:url';
const arg = (k, d) => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : d; };
const here = path.resolve(arg('--dir', '.')); const me = path.dirname(fileURLToPath(import.meta.url));
let local = {}; try { local = JSON.parse(fsSync.readFileSync(path.join(me, 'local.json'), 'utf8')); } catch {}
let pw; for (const t of [process.env.PLAYWRIGHT_FROM, local.playwright_from, path.join(me, '..', 'package.json'), path.join(process.cwd(), 'package.json')].filter(Boolean)) { try { pw = createRequire(t)('playwright'); break; } catch {} }
if (!pw) throw new Error('找不到 playwright：在 skill 根目录 npm install && npx playwright install chromium');
const mime = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.ttf': 'font/ttf', '.webp': 'image/webp'};
const srv = http.createServer(async (q, r) => { try { const p = path.join(here, decodeURIComponent(new URL(q.url, 'http://x').pathname)); r.writeHead(200, {'Content-Type': mime[path.extname(p)] ?? 'application/octet-stream'}).end(await fs.readFile(p)); } catch { r.writeHead(404).end(); } });
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const b = await pw.chromium.launch(); const p = await b.newPage({viewport: {width: 540, height: 960}});
await p.goto(`http://127.0.0.1:${srv.address().port}/index.html`); await p.evaluate(() => window.ready);
let ev = await p.evaluate(() => window.EVENTS || []); await b.close(); srv.close();
try { ev = ev.concat(JSON.parse(await fs.readFile(path.join(here, 'sfx_extra.json'), 'utf8'))); } catch {}
ev.sort((a, c) => a.t - c.t);
const thin = Number(arg('--thin', 0.08)), keep = [];
for (const e of ev) { const last = keep[keep.length - 1]; if (last && e.t - last.t < thin && !e.force) { if (e.peak > last.peak) keep[keep.length - 1] = e; } else keep.push(e); }
const bed = arg('--bed', 'bed.wav');
const out = {dir: 'sfx', bed: fsSync.existsSync(path.join(here, 'sfx', bed)) ? {file: bed, gain: Number(arg('--bed-gain', -17)), from_pre: false} : undefined, events: keep};
await fs.writeFile(path.join(here, 'sfx.json'), JSON.stringify(out, null, 1));
const T = JSON.parse(fsSync.readFileSync(path.join(here, 'timeline.json'), 'utf8')); console.log('音效', keep.length, '个（原', ev.length, '），每分钟', Math.round(keep.length / T.duration * 60), '个 → sfx.json', out.bed ? '配乐 ' + bed : '无配乐');
