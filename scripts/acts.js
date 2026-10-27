// 动作语法（engine.md「动作语法」）：坏事从上砸、好事从下弹、贴条转着拍、换姿势压扁一下、离场被带走。
// 在 stage.js 之后载入；scene.js 里 const {person, actor, drop, rise, slap, dust, shakeOf, ring_, out, plus} = ACTS;
(function () {
  const {kf, word, sfx, LOOK, clamp} = STAGE;
  const fs = (px, more = {}) => Object.assign({fontSize: px + 'px'}, more);
  const J = n => { const q = new XMLHttpRequest(); q.open('GET', `img/${n}.json`, false); q.send(); return JSON.parse(q.responseText); };
  // 人：脚踩在 (x, y)，从头顶到脚高 tall（json 由 cutout.py --anchor 写）
  function person(sc, name, x, y, tall, o = {}) {
    const a = J(name), w = tall * a.size[0] / (a.feet[1] - (a.top || 0));
    return sc.add(Object.assign({img: `img/${name}.png`, w, x, y, ax: a.feet[0] / a.size[0], ay: a.feet[1] / a.size[1], depth: 1, filter: LOOK.CUT}, o));
  }
  // 冲击后的衰减振荡（换姿势压扁、落地回弹都用它）
  const pulse = hits => t => { let v = 0; for (const th of hits) if (t >= th) v += Math.exp(-(t - th) / .09) * Math.cos((t - th) * 28); return v; };
  // 震屏：hits = [[时刻, 像素], …]；加到相机 x / y 上（y 用 ph 错一下相位）
  const shakeOf = (hits, ph = 0) => t => { let v = 0; for (const [th, a] of hits) if (t >= th && t < th + .6) v += a * Math.exp(-(t - th) / .08) * Math.sin((t - th) * 95 + ph); return v; };
  // 到位后的余震（角度）
  const ring_ = (t0, a = 4, k = .25) => t => t > t0 ? a * Math.exp(-(t - t0) / k) * Math.sin((t - t0) * 22) : 0;
  // 退场位移：t0 起加速离开 d 像素；plus 把几段位移加起来（进场关键帧 + 退场）
  const out = (t0, d = 1500, dur = .35) => t => t > t0 ? kf([[t0, 0], [t0 + dur, d, 'in']], t) : 0;
  const plus = (...fs_) => t => fs_.reduce((a, f) => a + kf(f, t), 0);
  // 角色：一串姿势 [[图, 起, 止, {flip, tall, x, y, o}]]；换图那一刻压扁一下，一直有呼吸
  function actor(sc, poses, x, y, tall, o = {}) {
    const pz = pulse(poses.map(p => p[1]));
    return poses.map(([name, t0, t1, oo = {}]) => person(sc, name, oo.x ?? x, oo.y ?? y, oo.tall ?? tall, Object.assign({show: [t0, t1],
      s: t => 1 - .09 * Math.max(0, pz(t)) + .008 * Math.sin(t * 5.2),
      sx: t => (oo.flip ? -1 : 1) * (1 + .13 * Math.max(0, pz(t)))}, o, oo.o || {})));
  }
  // 坏事：从屏外 0.24s 加速砸下来，落地压扁、回弹；配 thud
  function drop(sc, spec, tHit, from = -700) {
    const y = spec.y, p = pulse([tHit]);
    Object.assign(spec, {y: [[tHit - .24, from], [tHit, y, 'in']], s: t => 1 - .1 * Math.max(0, p(t)), sx: t => 1 + .15 * Math.max(0, p(t)), mblur: true});
    spec.show = spec.show || [tHit - .24, 999]; sfx(tHit, 'thud', spec.peak ?? -16);
    return sc.add(spec);
  }
  // 好事：从下面 0.3s 弹上来，过冲再回落，之后晃一晃
  function rise(sc, spec, t, from = 500) {
    const y = spec.y; spec.y = [[t, y + from], [t + .3, y, 'back']]; spec.show = spec.show || [t, 999];
    if (spec.r == null) spec.r = ring_(t + .3, 4, .2); sfx(t, 'pop', -22); return sc.add(spec);
  }
  // 落地扬灰
  function dust(sc, t, x, y, n = 8, f = 'none', depth = 1.05) {
    for (let i = 0; i < n; i++) {
      const a = Math.PI * (i + .5) / n, d = 110 + (i * 37) % 90;
      sc.add({html: '<div style="width:80px;height:80px;border-radius:50%;background:radial-gradient(rgba(236,226,206,.9),rgba(236,226,206,0) 70%)"></div>',
        x: [[t, x], [t + .55, x - Math.cos(a) * d * 1.7, 'out']], y: [[t, y], [t + .55, y - Math.sin(a) * d * .55, 'out']], s: [[t, .4], [t + .55, 1.7, 'out']],
        o: [[t, .9], [t + .55, 0, 'lin']], show: [t, t + .55], depth, filter: f});
    }
  }
  // 贴条：从 −40°、×1.7 转着拍上去，0.25s 快进慢停，再小回摆
  function slap(sc, txt, x, y, t, o = {}) {
    const r = o.r ?? -4;
    return word(sc, txt, x, y, t, {kind: 'slap', ax: .5, cls: o.cls ?? 'label cn', sfx: 'click', peak: -20, until: o.until,
      spec: Object.assign({css: fs(o.size ?? 96), filter: LOOK.LABEL, r: [[t, -40], [t + .25, r, 'out5'], [t + .42, r + 2.5, 'io']], s: [[t, 1.7], [t + .25, 1, 'out5']], o: [[t, 0], [t + .05, 1, 'lin']]}, o.spec || {})});
  }
  window.ACTS = {person, J, pulse, shakeOf, ring_, out, plus, actor, drop, rise, dust, slap, fs};
})();
