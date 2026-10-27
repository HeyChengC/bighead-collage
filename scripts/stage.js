// stage.js —— 大头剪贴风的舞台引擎。画面完全由 seek(t) 决定（同一个 t 永远是同一帧）。
// 舞台是 1080×1920 的逻辑坐标，按视口等比缩放。
// 概念：场（scene）= 一个小舞台：底 + 若干层（图、字），一台相机（推拉摇移），进出场用转场。
//      层按 depth 分到不同的"景深面"：相机动时，depth 大的动得多（前景云），小的动得少（远处天空）。
(function () {
  const W = 1080, H = 1920;
  // ---------- 缓动（剪映关键帧曲线的几种常用形状）
  const E = {
    lin: x => x,
    io: x => .5 - .5 * Math.cos(Math.PI * x),                 // 慢推、慢摇
    out: x => 1 - Math.pow(1 - x, 3),                          // 一般进场
    out5: x => 1 - Math.pow(1 - x, 5),                         // 快进慢停（剪映 x 从 2700 甩到 -100 那种）
    in: x => x * x * x,                                        // 转场加速
    back: x => { const c = 1.9; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); },   // 弹一下
    swing: x => 1 - Math.exp(-5 * x) * Math.cos(11 * x),       // 吊牌摆动停住
  };
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  // 关键帧：[[t, v, ease], ...]；ease 写在到达的那一帧上。数字直接当常量。
  function kf(tr, t) {
    if (typeof tr === 'number' || tr == null) return tr;
    if (typeof tr === 'function') return tr(t);
    if (t <= tr[0][0]) return tr[0][1];
    for (let i = 1; i < tr.length; i++) {
      const [t1, v1, e] = tr[i], [t0, v0] = tr[i - 1];
      if (t <= t1) { const u = (E[e || 'io'])(clamp((t - t0) / Math.max(1e-6, t1 - t0))); return v0 + (v1 - v0) * u; }
    }
    return tr[tr.length - 1][1];
  }
  // 曲线运镜：过一串关键帧的平滑曲线（三次 Hermite，切线取前后两点的斜率）。和 kf 的区别：
  //   kf 每一段都自带缓动，经过每个关键帧时速度归零 → "动一下、停一下"，像 PPT；
  //   spline 经过中间的关键帧时速度不归零，推完顺势接着拉，像剪映里贝塞尔曲线拉出来的运镜。
  //   log: true 在对数空间插值（缩放用：1→2 和 2→4 一样快）；ends: 'keep' 两端保持速度（转场长在运动最快处），'rest' 两端停住
  //   关键帧写 [t, v, 'h'] 表示在这里停住；参考片一场 1–2 个大动作，动作之间停一停（全片约 20–35% 的时间镜头几乎不动）
  function spline(pts, o = {}) {
    const lg = !!o.log, P = pts.map(([t, v]) => [t, lg ? Math.log(v) : v]), n = P.length;
    const m = P.map((p, i) => {
      if (pts[i][2] === 'h') return 0;                       // [t, v, 'h']：在这一帧停住（速度为零），动作之间的停顿用它
      if (i === 0) return o.ends === 'rest' || o.start === 'rest' ? 0 : (P[1][1] - P[0][1]) / (P[1][0] - P[0][0]);
      if (i === n - 1) return o.ends === 'rest' || o.end === 'rest' ? 0 : (P[n - 1][1] - P[n - 2][1]) / (P[n - 1][0] - P[n - 2][0]);
      return (P[i + 1][1] - P[i - 1][1]) / (P[i + 1][0] - P[i - 1][0]);
    });
    return t => {
      let v;
      if (t <= P[0][0]) v = P[0][1] + m[0] * (o.extrapolate ? t - P[0][0] : 0);
      else if (t >= P[n - 1][0]) v = P[n - 1][1] + m[n - 1] * (o.extrapolate ? t - P[n - 1][0] : 0);
      else {
        let i = 0; while (t > P[i + 1][0]) i++;
        const [t0, v0] = P[i], [t1, v1] = P[i + 1], h = t1 - t0, u = (t - t0) / h, u2 = u * u, u3 = u2 * u;
        v = (2 * u3 - 3 * u2 + 1) * v0 + (u3 - 2 * u2 + u) * h * m[i] + (-2 * u3 + 3 * u2) * v1 + (u3 - u2) * h * m[i + 1];
      }
      return lg ? Math.exp(v) : v;
    };
  }
  // 确定的随机数
  function rng(seed) { let s = seed >>> 0 || 1; return () => ((s = Math.imul(s ^ (s >>> 15), 2246822519) ^ Math.imul(s ^ (s >>> 13), 3266489917), (s ^= s >>> 16) >>> 0) / 4294967296); }

  const stage = document.createElement('div'); stage.id = 'stage';
  Object.assign(stage.style, {position: 'absolute', left: 0, top: 0, width: W + 'px', height: H + 'px', overflow: 'hidden', transformOrigin: '0 0', background: '#000'});
  document.body.appendChild(stage);
  function fit() { const k = Math.min(innerWidth / W, innerHeight / H); stage.style.transform = `scale(${k})`; }
  addEventListener('resize', fit); fit();

  // 时间线：temp_voice.py 写的 timeline.json（每句的起止、每个字的时刻）。画面时间一律从这里取
  let T = {beats: [], duration: 10, fps: 30};
  try { const q = new XMLHttpRequest(); q.open('GET', 'timeline.json', false); q.send(); if (q.status < 400) T = JSON.parse(q.responseText); } catch (e) {}
  const B = id => { const b = T.beats.find(x => x.id === id); if (!b) throw new Error('timeline.json 里没有这一句：' + id); return b; };
  const beat = id => B(id);                                             // {start, end, text, chars}
  function at(id, wd, k = 0) {                                          // 这句里第 k 次出现的 wd 的第一个字被读到的时刻
    const b = B(id); let i = -1; for (let n = 0; n <= k; n++) { i = b.text.indexOf(wd, i + 1); if (i < 0) throw new Error(`「${b.text}」里没有「${wd}」`); }
    return b.chars[i][1];
  }
  const scenes = []; const waits = [];
  // 音效事件表：画面里每个事件顺手登记一个音效，sfxlist.mjs 导出成 sfx.json 给 mix.py
  const EVENTS = [];
  function sfx(t, file, peak = -22, o = {}) { if (file) EVENTS.push(Object.assign({t: +t.toFixed(3), file: file.endsWith('.wav') ? file : file + '.wav', peak}, o)); }
  // ---------- 层
  // spec: {img|html|text, x, y, w, ax, ay, s, r, o, blur, depth, z, filter, cls, show:[t0,t1]}
  function layer(sc, spec) {
    let el;
    if (spec.img) {
      el = new Image(); el.src = spec.img; el.draggable = false; waits.push(el.decode().catch(() => { throw new Error('图片加载失败 ' + spec.img); }));
      if (spec.w) el.style.width = spec.w + 'px';
      if (spec.h) el.style.height = spec.h + 'px';
    } else { el = document.createElement('div'); el.innerHTML = spec.html ?? ''; if (spec.w) el.style.width = spec.w + 'px'; }
    if (spec.cls) el.className = spec.cls;
    if (spec.css) Object.assign(el.style, spec.css);
    el.style.position = 'absolute'; el.style.left = 0; el.style.top = 0;
    const ax = spec.ax ?? .5, ay = spec.ay ?? .5;
    el.style.transformOrigin = `${ax * 100}% ${ay * 100}%`;
    const L = Object.assign({el, ax, ay, depth: 1, x: W / 2, y: H / 2, s: 1, r: 0, o: 1, blur: 0}, spec);
    plane(sc, L.depth, L.pop || L.front ? 'pop' : L.back ? 'back' : 'box').appendChild(el); sc.layers.push(L); return L;
  }
  function plane(sc, d, where) {
    const P = where === 'pop' ? sc.pplanes : where === 'back' ? sc.bplanes : sc.planes;
    if (!P[d]) {
      const p = document.createElement('div'); const off = where === 'back' ? {left: W / 2 + 'px', top: H / 2 + 'px'} : {left: 0, top: 0};
      Object.assign(p.style, {position: 'absolute', width: W + 'px', height: H + 'px', transformOrigin: '50% 50%'}, off);
      p.style.zIndex = Math.round(d * 100); sc[where].appendChild(p); P[d] = p;
    }
    return P[d];
  }
  // ---------- 场
  // spec: {t0, t1, z, bg(css), cam:{z,x,y,r}, clip(t)->css|null, wrap(t)->transform css, filter}
  function scene(spec) {
    const root = document.createElement('div');
    Object.assign(root.style, {position: 'absolute', left: 0, top: 0, width: W + 'px', height: H + 'px', overflow: 'visible', transformOrigin: '50% 50%'});
    stage.appendChild(root);
    const mk = z => { const b = document.createElement('div'); Object.assign(b.style, {position: 'absolute', inset: 0, zIndex: z}); root.appendChild(b); return b; };
    const back = mk(0), mid = mk(1), box = mk(2), pop = mk(3);   // back 底（底色 + add({back:true}) 的底图）；mid 白圈；box 实物；pop 压在最上面的（破框的主角、要盖住一切的贴条）
    Object.assign(back.style, {inset: 'auto', left: -W / 2 + 'px', top: -H / 2 + 'px', width: 2 * W + 'px', height: 2 * H + 'px', background: spec.bg || 'transparent'});   // 出血一倍：缩小退场时底不会露出方边          // box 被圆裁；mid 放白圈；pop 是破框的主角（不被裁）
    const sc = Object.assign({root, back, box, mid, pop, layers: [], planes: {}, pplanes: {}, bplanes: {}, cam: {}, z: scenes.length}, spec);
    root.style.zIndex = Math.round(sc.z * 100);            // z 可以写小数（4.5 夹在 4 和 5 之间）；CSS 的 z-index 只认整数，这里换算
    (sc.whips || []).forEach(([a]) => sfx(a - .03, 'whip', -20));
    sc.add = s => layer(sc, s);
    scenes.push(sc); return sc;
  }

  // ---------- 颗粒 + 暗角（全片统一一层）
  const grain = document.createElement('canvas'); grain.width = 360; grain.height = 640;
  Object.assign(grain.style, {position: 'absolute', left: 0, top: 0, width: W + 'px', height: H + 'px', zIndex: 9000, mixBlendMode: 'overlay', opacity: .32, imageRendering: 'auto'});
  stage.appendChild(grain);
  const vig = document.createElement('div');
  Object.assign(vig.style, {position: 'absolute', inset: 0, zIndex: 8999, pointerEvents: 'none', background: 'radial-gradient(ellipse 75% 60% at 50% 48%, rgba(0,0,0,0) 55%, rgba(0,0,0,.38) 100%)'});
  stage.appendChild(vig);
  const gctx = grain.getContext('2d'); const gimg = gctx.createImageData(360, 640);
  function drawGrain(f) {
    const R = rng(f * 7919 + 13), d = gimg.data;
    for (let i = 0; i < d.length; i += 4) { const v = 128 + (R() - .5) * 150; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
    gctx.putImageData(gimg, 0, 0);
  }
  const FX = {grain: .32, vignette: true};

  // ---------- 一帧
  function seek(t) {
    for (const sc of scenes) {
      const on = t >= sc.t0 && t < sc.t1;
      sc.root.style.display = on ? 'block' : 'none'; if (!on) continue;
      const cz = kf(sc.cam.z ?? 1, t), cx = kf(sc.cam.x ?? 0, t), cy = kf(sc.cam.y ?? 0, t), cr = kf(sc.cam.r ?? 0, t);
      for (const P of [sc.planes, sc.pplanes, sc.bplanes]) for (const d in P) {
        const p = +d, z = 1 + (cz - 1) * p;
        P[d].style.transform = `rotate(${cr * p}deg) scale(${z}) translate(${-cx * p}px, ${-cy * p}px)`;
      }
      for (const L of sc.layers) {
        const vis = !L.show || (t >= L.show[0] && t < L.show[1]);
        L.el.style.display = vis ? '' : 'none'; if (!vis) continue;
        const x = kf(L.x, t), y = kf(L.y, t), s = kf(L.s, t), r = kf(L.r, t), o = kf(L.o, t), b = kf(L.blur, t), sx = kf(L.sx ?? 1, t);
        L.el.style.transform = `translate(${x}px, ${y}px) translate(${-L.ax * 100}%, ${-L.ay * 100}%) rotate(${r}deg) scale(${s * sx}, ${s})`;
        L.el.style.opacity = o;
        let mb = '';
        if (L.mblur) {                                     // 快速移动的物件（扫过的钞票、掉下来的纸）按自己的速度加方向模糊
          const dt = 1 / 30, vx = Math.abs(kf(L.x, t) - kf(L.x, t - dt)), vy = Math.abs(kf(L.y, t) - kf(L.y, t - dt));
          if (vx > 18 || vy > 18) { if (!L._mb) { const id = 'lmb' + Math.random().toString(36).slice(2, 8); const f = document.createElementNS(svgns, 'filter'); f.id = id; f.setAttribute('x', '-20%'); f.setAttribute('y', '-20%'); f.setAttribute('width', '140%'); f.setAttribute('height', '140%'); const g = document.createElementNS(svgns, 'feGaussianBlur'); f.appendChild(g); defs.appendChild(f); L._mb = g; L._mbid = id; }
            L._mb.setAttribute('stdDeviation', `${(vx * .35).toFixed(1)} ${(vy * .35).toFixed(1)}`); mb = `url(#${L._mbid}) `; }
        }
        const f = mb + (b > .05 ? `blur(${b}px) ` : '') + (L.filter || '');
        L.el.style.filter = f || '';
        if (L.update) L.update(t, L);
      }
      // 甩镜的方向模糊：只在 sc.whips 标出的时间窗里（[[t0, t1], …]），按相机速度给；普通摇镜、拉远不糊
      const inWhip = (sc.whips || []).some(([a, b]) => t >= a && t <= b);
      if (inWhip) {
        const dt = 1 / 30, vx = Math.abs(kf(sc.cam.x ?? 0, t) - kf(sc.cam.x ?? 0, t - dt)), vy = Math.abs(kf(sc.cam.y ?? 0, t) - kf(sc.cam.y ?? 0, t - dt));
        const id = sc._mb ? sc._mb.parentNode.id : mblur(sc); sc._mb.setAttribute('stdDeviation', `${(vx * .45).toFixed(1)} ${(vy * .45).toFixed(1)}`); sc.root.style.filter = `url(#${id})`;
      } else sc.root.style.filter = '';
      // 转场的圆：进场（irisIn）整场都裁；退场（irisOut）只裁底色，剪纸实物完整地跟着缩小、可以露在圈外
      const c = sc.clip ? sc.clip(t) : null, bgOnly = sc.bgOnlyFrom != null && t >= sc.bgOnlyFrom;
      const css = (dx, dy) => !c ? 'none' : typeof c === 'string' ? c : `circle(${c.r}px at ${c.x + dx}px ${c.y + dy}px)`;
      sc.back.style.clipPath = typeof c === 'string' ? 'none' : css(W / 2, H / 2);
      sc.box.style.clipPath = bgOnly ? 'none' : css(0, 0); sc.pop.style.clipPath = bgOnly ? 'none' : css(0, 0);
      if (typeof c === 'string') sc.root.style.clipPath = c; else sc.root.style.clipPath = 'none';
      sc.root.style.transform = sc.wrap ? (sc.wrap(t) || 'none') : 'none';
      if (sc.update) sc.update(t, sc);
    }
    for (const o of overlays) o(t);
    grain.style.display = FX.grain ? '' : 'none'; grain.style.opacity = FX.grain;
    if (FX.grain) drawGrain(Math.round(t * 30));
    vig.style.display = FX.vignette ? '' : 'none';
  }
  const overlays = [];
  const svgns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(svgns, 'svg'); defs.setAttribute('width', 0); defs.setAttribute('height', 0); defs.style.position = 'absolute';
  document.body.appendChild(defs);
  function mblur(sc) {               // 每场一个方向模糊滤镜
    const f = document.createElementNS(svgns, 'filter'); f.id = 'mb' + scenes.indexOf(sc); f.setAttribute('x', '-10%'); f.setAttribute('width', '120%');
    const g = document.createElementNS(svgns, 'feGaussianBlur'); g.setAttribute('stdDeviation', '0 0'); f.appendChild(g); defs.appendChild(f); sc._mb = g; return f.id;
  }

  // ---------- 转场
  const diag = Math.hypot(W, H);
  const TX = {
    // 圆圈揭开下一场（下一场在上面）：圆心 (x,y)，r 从 0 长到盖满
    irisIn(next, t0, dur, x = W / 2, y = H / 2, ease = 'lin') {
      sfx(t0 - .05, 'whoosh', -22);
      next.t0 = Math.min(next.t0, t0);
      const prev = next.clip, far = Math.max(Math.hypot(x, y), Math.hypot(W - x, y), Math.hypot(x, H - y), Math.hypot(W - x, H - y));   // 圆刚好盖满的半径
      next.clip = t => t < t0 + dur ? {r: kf([[t0, 0], [t0 + dur, far, ease]], t), x, y} : (prev ? prev(t) : null);
    },
    // 当前这一场整体缩进一个圆里退场（下一场在下面露出来），可带白圈
    irisOut(cur, t0, dur, x = W / 2, y = H / 2, ring = null, endScale = .55, rEnd = 390) {
      // 画面匀速缩小（lin），圆圈先快后慢收紧（out）；rEnd 是收完时屏上看到的圆半径
      cur.t1 = Math.max(cur.t1, t0 + dur); if (cur.cutoutsStay !== false) cur.bgOnlyFrom = t0; sfx(t0, 'whoosh', -22);
      const S = t => kf([[t0, 1], [t0 + dur, endScale, 'lin']], t), Rd = t => kf([[t0, 1150], [t0 + dur, rEnd, 'out']], t), R = t => Rd(t) / S(t);
      const prevClip = cur.clip, prevWrap = cur.wrap;
      cur.clip = t => t < t0 ? (prevClip ? prevClip(t) : null) : {r: R(t), x, y};
      cur.wrap = t => t < t0 ? (prevWrap ? prevWrap(t) : null) : `translate(${(x - W / 2) * (1 - S(t))}px, ${(y - H / 2) * (1 - S(t))}px) scale(${S(t)})`;
      if (ring) {
        
        const rg = document.createElement('div'); Object.assign(rg.style, {position: 'absolute', borderRadius: '50%', pointerEvents: 'none', boxSizing: 'border-box'});
        cur.mid.appendChild(rg);
        overlays.push(t => {
          const on = t >= t0 && t < cur.t1; rg.style.display = on ? '' : 'none'; if (!on) return;
          const r = R(t), bw = (ring.w || 10) / S(t);
          Object.assign(rg.style, {left: (x - r - bw) + 'px', top: (y - r - bw) + 'px', width: 2 * (r + bw) + 'px', height: 2 * (r + bw) + 'px', border: `${bw}px solid ${ring.c || '#fff'}`});
        });
      }
    },
    // 从一个画框（平板屏幕、窗户、相框）里放大出来：tIn 时下一场整场缩在框里（同位置、按框宽缩小），dur 内快进慢停放大到整屏。
    // rect = {x, y, w, h}：框此刻在屏幕上的位置（舞台坐标，左上角 + 宽高），要跟着上一场的相机算（见 engine.md）。
    // 对临 v1 1.15–1.22s：上一场的镜头只推到 ×1.13，不是一路推进屏幕；下一场比框高就露出框外（原片也是）
    fromRect(next, tIn, dur, rect, round = 10) {
      sfx(tIn - .03, 'whoosh', -22);
      next.t0 = Math.min(next.t0, tIn);
      const s0 = rect.w / W, cx0 = rect.x + rect.w / 2, cy0 = rect.y + rect.h / 2;
      const S = t => kf([[tIn, s0], [tIn + dur, 1, 'out']], t), U = t => (S(t) - s0) / (1 - s0), pw = next.wrap, pc = next.clip;
      next.wrap = t => t < tIn + dur ? `translate(${(cx0 - W / 2) * (1 - U(t))}px, ${(cy0 - H / 2) * (1 - U(t))}px) scale(${S(t)})` : (pw ? pw(t) : null);
      next.clip = t => t < tIn + dur ? `inset(0 round ${round / S(t)}px)` : (pc ? pc(t) : null);
    },
    // 可动的黑色圆孔：r / x / y 都可以是数字、关键帧 [[t, v, 缓动], …] 或函数；从 t0 到 t1 一直盖在所有场上面。
    // 圈进来不居中（x、y 从一角滑到中间）、第二次推近时圈先张开再收回，都用它（对临 v1 9.55s、15.3s）
    ring(t0, t1, {r, x = W / 2, y = H / 2, color = '#1c1c1c', sound = true} = {}) {
      if (sound) sfx(t0, 'whoosh', -22);
      const el = document.createElement('div'); Object.assign(el.style, {position: 'absolute', inset: 0, zIndex: 5000, pointerEvents: 'none'});
      stage.appendChild(el);
      overlays.push(t => {
        const on = t >= t0 && t < t1; el.style.display = on ? '' : 'none'; if (!on) return;
        const R = kf(r, t), X = kf(x, t), Y = kf(y, t);
        el.style.background = `radial-gradient(circle ${R}px at ${X}px ${Y}px, rgba(0,0,0,0) ${R - 1.5}px, ${color} ${R}px)`;
      });
      return el;
    },
    // 黑框圆孔：镜头像钻进一个圆孔（黑色圆环从外往里收，停在一个圆窗）
    porthole(sc, t0, dur, r1 = 640, x = W / 2, y = H / 2, ring = '#151515', tOpen = null) {   // tOpen：从这一刻起圆孔往外张开（0.3s），不要等场结束突然消失
      sfx(t0, 'whoosh', -24);
      const ph = document.createElement('div'); Object.assign(ph.style, {position: 'absolute', inset: 0, zIndex: 5000, pointerEvents: 'none'});
      stage.appendChild(ph);
      overlays.push(t => {
        const on = t >= t0 && t < sc.t1; ph.style.display = on ? '' : 'none'; if (!on) return;
        const r = tOpen != null && t >= tOpen ? kf([[tOpen, r1], [tOpen + .3, diag * .8, 'in']], t) : kf([[t0, diag * .75], [t0 + dur, r1, 'out5']], t);
        ph.style.background = `radial-gradient(circle ${r}px at ${x}px ${y}px, rgba(0,0,0,0) ${r - 1}px, ${ring} ${r}px)`;
      });
    },
  };

  // ---------- 字
  // 每个词一个层；kind 决定进场方式；style 决定外观（CSS class）
  // pop：从 1.35 弹回 1；rise：从下方 60px 升上来并淡入；far：从远处（小、糊）飞近；slide：从一侧甩进；type：逐字敲出；scramble：乱码解成字
  function word(sc, txt, x, y, t, o = {}) {
    const kind = o.kind || 'pop', d = o.dur ?? (kind === 'far' ? .35 : kind === 'slide' ? .35 : .18);
    const spec = Object.assign({html: `<span>${txt}</span>`, x, y, ax: o.ax ?? 0, ay: o.ay ?? .5, cls: 'w ' + (o.cls || 'ex'), depth: o.depth ?? 1, show: [t, o.until ?? 1e9]}, o.spec || {});
    if (kind === 'pop') { spec.s = [[t, o.s0 ?? 1.35], [t + d, o.s ?? 1, 'back']]; spec.o = [[t, 0], [t + d * .5, 1, 'lin']]; }
    if (kind === 'rise') { spec.y = [[t, y + 70], [t + d * 1.4, y, 'out5']]; spec.o = [[t, 0], [t + d, 1, 'lin']]; }
    if (kind === 'far') { spec.s = [[t, .35], [t + d, o.s ?? 1, 'out5']]; spec.o = [[t, 0], [t + d * .6, 1, 'lin']]; spec.blur = [[t, 14], [t + d, 0, 'out']]; }
    if (kind === 'slide') { const fx = o.from ?? (x > W / 2 ? W + 300 : -900); spec.x = [[t, fx], [t + d, x, 'out5']]; }
    if (o.s != null && kind !== 'pop' && kind !== 'far') spec.s = o.s;
    if (o.drift) { const base = spec.s; spec.s = tt => kf(base ?? 1, tt) * (1 + o.drift * Math.max(0, tt - t)); }
    const L = sc.add(spec);
    if (o.sfx !== false && kind !== 'type' && kind !== 'scramble') sfx(t, o.sfx || (kind === 'far' ? 'flick' : kind === 'slide' ? 'whip' : 'flick'), o.peak ?? (kind === 'far' ? -20 : -24));
    if (kind === 'type' || kind === 'scramble') { const per = o.per ?? .07; if (o.sfx !== false) [...txt].forEach((c, i) => c.trim() && sfx(t + i * per, o.sfx || 'key', o.peak ?? -30)); }
    if (kind === 'type' || kind === 'scramble') {
      const chars = [...txt], per = o.per ?? .07, glyph = '#$%&*~<>/\\|+=?';
      L.update = (tt) => {
        const n = clamp(Math.floor((tt - t) / per) + 1, 0, chars.length);
        if (kind === 'type') L.el.firstChild.textContent = chars.slice(0, n).join('');
        else { const R = rng(Math.floor(tt * 30) + 7); L.el.firstChild.textContent = chars.map((c, i) => i < n - 2 ? c : (i < n + 3 && c !== ' ' ? glyph[Math.floor(R() * glyph.length)] : (i < n ? c : ''))).join(''); if (n >= chars.length && tt - t > per * (chars.length + 3)) L.el.firstChild.textContent = txt; }
      };
    }
    return L;
  }

  // 一行词：每个词一个层，x 按量出来的字宽依次排开（字体加载完才量）。items: [[文字, 出现时刻, {opts}], ...]
  // align: 'left'（x 是左端）| 'center'（x 是整行中点）| 'right'
  const layouts = [];
  function row(sc, items, x, y, o = {}) {
    const Ls = items.map(([txt, t, oo]) => word(sc, txt, x, y, t, Object.assign({}, o, oo || {}, {ax: 0})));
    layouts.push(() => {
      const rd = sc.root.style.display; sc.root.style.display = 'block';
      const ws = Ls.map(L => { const d = L.el.style.display; L.el.style.display = ''; const w = L.el.firstChild.getBoundingClientRect().width / (stage.getBoundingClientRect().width / W) / (L.el.getBoundingClientRect().width ? 1 : 1); L.el.style.display = d; return w; });
      sc.root.style.display = rd;
      const gap = o.gap ?? 0.22 * parseFloat(getComputedStyle(Ls[0].el.firstChild).fontSize), tot = ws.reduce((a, b) => a + b, 0) + gap * (ws.length - 1);
      let cx = o.align === 'center' ? x - tot / 2 : o.align === 'right' ? x - tot : x;
      Ls.forEach((L, i) => { const base = cx; if (L.kind === 'slide') {} L.x = typeof L.x === 'number' ? base : L.x; if (typeof L.x !== 'number') L.x = base; cx += ws[i] + gap; });
    });
    return Ls;
  }

  // ---------- 字幕：全片一条，屏幕固定位置，按短句换，不做任何动画（《商业狠人图鉴 01》v4.1，用户认可）
  // 中文竖屏片默认要有。不跟相机走；y 默认 1400（9:16 抖音安全区：标题区 y>1560 之上、右侧按钮列 x>940 之左）。
  // o.skip：不出字幕的句子 id（屏上已经写着这句：片名卡、逐词排出来的原话）
  // o.breaks：{'整条短句': 前半的字数}，一条超过 o.max（默认 14）字时在语义处断成两条；没写断点就对半断并在控制台提醒
  // o.yield：[[t0, t1], …] 这些时间里开始的字幕推迟到 t1（镜头推近到片名、大字时让位）
  function captions(o = {}) {
    const sc = scene({t0: 0, t1: T.duration, z: o.z ?? 50, bg: 'transparent'}), skip = new Set(o.skip || []), max = o.max ?? 14, cuts = [];
    T.beats.forEach((b, bi) => {
      if (skip.has(b.id)) return;
      const parts = []; let cur = '', i0 = 0;
      [...b.text].forEach((c, i) => {
        if (!cur) i0 = i;
        if ('，。；：！？,;:!?'.includes(c)) { if (cur) parts.push([cur, i0]); cur = ''; } else if (!'“”"「」'.includes(c)) cur += c;
      });
      if (cur) parts.push([cur, i0]);
      const next = T.beats[bi + 1];
      parts.forEach(([txt, i], k) => {
        const t0 = b.chars[i][1] - .05, t1 = k + 1 < parts.length ? b.chars[parts[k + 1][1]][1] - .05 : Math.min(b.end + .35, next ? next.chars[0][1] - .05 : T.duration);
        let n = (o.breaks || {})[txt];
        if (!n && txt.length > max) { n = Math.ceil(txt.length / 2); console.warn(`字幕「${txt}」${txt.length} 字，对半断了；在 breaks 里写语义断点`); }
        if (n) { const tm = b.chars[b.text.indexOf(txt.slice(n), i)][1] - .05; cuts.push([txt.slice(0, n), t0, tm], [txt.slice(n), tm, t1]); }
        else cuts.push([txt, t0, t1]);
      });
    });
    for (const c of cuts) for (const [a, z] of o.yield || []) if (c[1] > a && c[1] < z) c[1] = z;
    cuts.forEach(([txt, t0, t1]) => t1 > t0 && sc.add({html: `<span class="o">${txt}</span><span class="f">${txt}</span>`, cls: 'cap', x: o.x ?? W / 2, y: o.y ?? 1400, ax: .5, ay: .5, depth: 1, show: [t0, t1]}));
    return cuts;
  }

  // ---------- 字的外观预设（filter 链；配合 look.css 的颜色类用）
  const LOOK = {
    EXO: 'drop-shadow(3px 3px 0 #9b1d0c) drop-shadow(3px 3px 0 #9b1d0c) drop-shadow(2px 2px 0 #7a1208) drop-shadow(0 10px 14px rgba(0,0,0,.45))',   // 橙黄字的深红挤出
    EXR: 'drop-shadow(2px 3px 0 #3a0507) drop-shadow(2px 3px 0 #3a0507) drop-shadow(0 8px 12px rgba(0,0,0,.55))',                                  // 暗红/红字
    EXW: 'drop-shadow(2px 3px 0 #2a0405) drop-shadow(2px 3px 0 #2a0405) drop-shadow(0 8px 12px rgba(0,0,0,.6))',                                   // 白字
    EXK: 'drop-shadow(2px 3px 0 rgba(0,0,0,.25)) drop-shadow(0 6px 10px rgba(0,0,0,.25))',                                                          // 浅底上的深灰字
    CHALK: 'drop-shadow(0 0 6px rgba(255,255,255,.55)) drop-shadow(0 0 16px rgba(255,255,255,.25))',                                               // 黑板上发光的粉笔字
    LABEL: 'drop-shadow(0 6px 8px rgba(0,0,0,.35))',                                                                                               // 贴条
    CUT: 'drop-shadow(0 18px 18px rgba(0,0,0,.35))',                                                                                               // 照片剪纸的投影
  };

  // ---------- 出口
  window.STAGE = {W, H, E, kf, spline, rng, clamp, scene, word, row, captions, sfx, at, beat, T, TX, FX, LOOK, scenes, overlays, stage};
  window.EVENTS = EVENTS;
  window.seek = seek;
  window.ready = new Promise(res => setTimeout(res, 0)).then(() => Promise.all([document.fonts.ready, ...waits])).then(() => Promise.all(waits)).then(() => { seek(0); layouts.forEach(f => f()); seek(0); });
})();
