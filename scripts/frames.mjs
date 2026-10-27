// 逐帧渲染：页面暴露 window.ready（Promise）和 window.seek(t)（画出 t 秒那一帧），Playwright 截图，ffmpeg 编码。
// 用法（放在片子目录外层也行，--dir 指向有 index.html + timeline.json 的目录）：
//   node frames.mjs --dir film --stills 0.5,3.2,10        # 看静帧（out/still_*.png）
//   node frames.mjs --dir film --video --h 720            # 预览整片（out/visual_720.mp4，无声）
//   node frames.mjs --dir film --video --h 720 --range 0:18
//   node frames.mjs --dir film --video --h 1080           # 成片画面（竖屏在 timeline.json 写 "aspect":"9:16"，--h 1920）
// 页面要求：seek 是确定的（同一个 t 永远画出同一帧，不依赖播放时间、不用 CSS 动画），并 await 图片和字体。
import fs from 'node:fs/promises'; import path from 'node:path'; import http from 'node:http';
import {spawn} from 'node:child_process'; import {once} from 'node:events';
import {createRequire} from 'node:module'; import fsSync from 'node:fs'; import {fileURLToPath} from 'node:url';

const arg = k => { const i = process.argv.indexOf(k); return i >= 0 ? process.argv[i + 1] : null; };
const has = k => process.argv.includes(k);
function loadPlaywright() {
  const here = path.dirname(fileURLToPath(import.meta.url)); let local = {};
  try { local = JSON.parse(fsSync.readFileSync(path.join(here, 'local.json'), 'utf8')); } catch {}
  for (const t of [process.env.PLAYWRIGHT_FROM, local.playwright_from, path.join(process.cwd(), 'package.json'), fileURLToPath(import.meta.url)].filter(Boolean)) {
    try { return createRequire(t)('playwright'); } catch {}
  }
  throw new Error('找不到 playwright：在 skill 根目录 npm install && npx playwright install chromium（或设环境变量 PLAYWRIGHT_FROM 指向装了它的 package.json）');
}
const {chromium} = loadPlaywright();
const here = path.resolve(arg('--dir') ?? '.');
const T = JSON.parse(await fs.readFile(path.join(here, 'timeline.json'), 'utf8').catch(() => '{"duration":10,"fps":30}'));
// 画幅：timeline.json 里写 "aspect": "9:16"（竖屏）/ "16:9"（默认）/ "3:4" …；--h 是输出的高
const [aw, ah] = String(T.aspect ?? '16:9').split(':').map(Number);
const H = Number(arg('--h') ?? 720), Wd = Math.round(H * aw / ah / 2) * 2, out = path.join(here, 'out');
await fs.mkdir(out, {recursive: true});
const mime = {'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.TTF': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2'};
const worker = arg('--worker');
let server, port = Number(arg('--port'));
if (!worker) {
  server = http.createServer(async (q, r) => {
    try { const p = path.join(here, decodeURIComponent(new URL(q.url, 'http://x').pathname)); const b = await fs.readFile(p); r.writeHead(200, {'Content-Type': mime[path.extname(p)] ?? 'application/octet-stream'}).end(b); }
    catch { r.writeHead(404).end(); }
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r)); port = server.address().port;
}
async function page() {
  const b = await chromium.launch({args: ['--force-color-profile=srgb', '--disable-lcd-text']});
  const p = await b.newPage({viewport: {width: Wd, height: H}}); const errs = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  p.on('requestfailed', q => errs.push('请求失败 ' + q.url())); p.on('response', s => { if (s.status() >= 400) errs.push(s.status() + ' ' + s.url()); });
  await p.goto(`http://127.0.0.1:${port}/index.html`); await p.evaluate(() => window.ready);
  if (!(await p.evaluate(() => typeof window.seek === 'function'))) { console.error('页面没有 window.seek（脚本没加载或报错）：', errs.slice(0, 8)); process.exit(3); }
  return {b, p, errs};
}
if (arg('--stills')) {
  const {b, p, errs} = await page(); const ts = arg('--stills').split(',').map(Number);
  for (const t of ts) { await p.evaluate(t => window.seek(t), t); await p.screenshot({path: path.join(out, `still_${t.toFixed(2)}.png`)}); }
  await b.close(); server.close(); if (errs.length) console.log('页面报错（先修再看帧）：', [...new Set(errs)].slice(0, 8)); console.log('stills', ts.length); process.exit(0);
}
const fps = T.fps ?? 30, N = Math.ceil(T.duration * fps);
if (worker) {
  const [a, z] = worker.split(':').map(Number); const {b, p, errs} = await page();
  const enc = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-framerate', String(fps), '-i', 'pipe:0', '-c:v', 'libx264', '-preset', 'medium',
    '-crf', H >= 1080 ? '14' : '18', '-pix_fmt', 'yuv420p', '-r', String(fps), path.join(out, `seg_${H}_${a}.mp4`)], {stdio: ['pipe', 'ignore', 'inherit']});
  for (let f = a; f < z; f++) { await p.evaluate(t => window.seek(t), f / fps); const buf = await p.screenshot({type: 'jpeg', quality: H >= 1080 ? 96 : 92}); if (!enc.stdin.write(buf)) await once(enc.stdin, 'drain'); }
  enc.stdin.end(); await once(enc, 'exit'); await b.close(); if (errs.length) { console.error([...new Set(errs)].slice(0, 5)); process.exit(2); } process.exit(0);
}
if (!has('--video')) { console.log('用 --stills 或 --video'); server.close(); process.exit(1); }
const RG = arg('--range'), F0 = RG ? Math.round(Number(RG.split(':')[0]) * fps) : 0, F1 = RG ? Math.min(N, Math.round(Number(RG.split(':')[1]) * fps)) : N;
const K = Number(arg('--workers') ?? 6), size = Math.ceil((F1 - F0) / K), starts = []; const t0 = Date.now();
await Promise.all(Array.from({length: K}, (_, i) => { const a = F0 + i * size, z = Math.min(F1, a + size); if (a >= z) return null; starts.push(a);
  return new Promise((res, rej) => { const c = spawn(process.execPath, [fileURLToPath(import.meta.url), '--dir', here, '--worker', `${a}:${z}`, '--port', String(port), '--h', String(H)], {stdio: 'inherit'}); c.on('exit', x => x === 0 ? res() : rej(new Error('worker ' + a))); }); }));
starts.sort((a, b) => a - b);
await fs.writeFile(path.join(out, `list_${H}.txt`), starts.map(s => `file 'seg_${H}_${s}.mp4'`).join('\n'));
const vout = path.join(out, RG ? `visual_${H}_range.mp4` : `visual_${H}.mp4`);
await new Promise((res, rej) => { const c = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(out, `list_${H}.txt`), '-c', 'copy', vout], {stdio: 'inherit'}); c.on('exit', x => x === 0 ? res() : rej()); });
server.close(); console.log('rendered', F1 - F0, 'frames in', ((Date.now() - t0) / 1000).toFixed(1), 's ->', vout);
