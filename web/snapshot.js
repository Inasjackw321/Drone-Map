/* Area snapshot: renders a clean, minimal infographic of a selected map area to a canvas (PNG).
   Everything is drawn from data (districts, alerts, occupied areas, tracks), no map tiles. */
window.DMSnapshot = (() => {
  'use strict';
  const { THREATS, mapSvg, explosion, tint, svgDataUrl } = window.DMIcons;
  const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  const R = 6371;

  const mx = lon => (lon + 180) / 360;
  const my = lat => { const s = Math.sin(lat * Math.PI / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };

  const imgCache = new Map();
  function image(markup) {
    if (imgCache.has(markup)) return imgCache.get(markup);
    const p = new Promise(resolve => {
      const im = new Image();
      im.onload = () => resolve(im);
      im.onerror = () => resolve(null);
      im.src = svgDataUrl(markup);
    });
    imgCache.set(markup, p);
    return p;
  }

  function areaName(bounds, base) {
    const c = bounds.getCenter();
    const spanLon = bounds.getEast() - bounds.getWest();
    if (spanLon > 9) return 'Ukraine';
    let best = null, bd = Infinity;
    for (const f of base.data.oblasts.features) {
      const [lon, lat] = f.properties.label;
      const d = (lon - c.lng) ** 2 + (lat - c.lat) ** 2;
      if (d < bd) { bd = d; best = f.properties; }
    }
    if (!best) return 'Selected area';
    const en = { kyiv_city: 'Kyiv', sevastopol: 'Sevastopol', crimea: 'Crimea' }[best.key];
    return en || `${best.key.replace('_', '-').replace(/^./, ch => ch.toUpperCase())} region`;
  }

  const colorOf = t => (THREATS[t.threat] || THREATS.uav).color;

  function niceKm(maxKm) {
    for (const v of [500, 200, 100, 50, 20, 10, 5, 2, 1]) if (v <= maxKm) return v;
    return 1;
  }

  async function render(opts) {
    const { bounds, state, base, tracks, predicted, show } = opts;
    const title = opts.title || `Air situation · ${areaName(bounds, base)}`;
    const PAL = base.PAL;
    const x0 = mx(bounds.getWest()), x1 = mx(bounds.getEast());
    const y0 = my(bounds.getNorth()), y1 = my(bounds.getSouth());
    let W = 1600;
    let H = Math.round(W * (y1 - y0) / (x1 - x0));
    if (H > 1500) { W = Math.round(1500 * (x1 - x0) / (y1 - y0)); H = 1500; }
    if (W < 900) { H = Math.round(H * 900 / W); W = 900; }
    const HEAD = 104, FOOT = 132, PAD = 0;
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = HEAD + H + FOOT;
    const ctx = cv.getContext('2d');
    const X = lon => PAD + (mx(lon) - x0) / (x1 - x0) * W;
    const Y = lat => HEAD + (my(lat) - y0) / (y1 - y0) * H;
    const inView = (lat, lon, m = 0) => lat <= bounds.getNorth() + m && lat >= bounds.getSouth() - m && lon >= bounds.getWest() - m && lon <= bounds.getEast() + m;
    const kmPx = (lat, km) => {                       // pixels for a distance at a latitude
      const dLon = km / (R * Math.cos(lat * Math.PI / 180)) * 180 / Math.PI;
      return Math.abs(X(dLon) - X(0));
    };

    // ---- page
    ctx.fillStyle = '#0f1318';
    ctx.fillRect(0, 0, cv.width, cv.height);

    // ---- map area (clipped)
    ctx.save();
    ctx.beginPath(); ctx.rect(0, HEAD, W, H); ctx.clip();
    ctx.fillStyle = PAL.sea; ctx.fillRect(0, HEAD, W, H);
    const geomPath = g => {
      const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : [];
      ctx.beginPath();
      for (const poly of polys) for (const ring of poly) {
        ring.forEach(([lon, lat], i) => (i ? ctx.lineTo(X(lon), Y(lat)) : ctx.moveTo(X(lon), Y(lat))));
        ctx.closePath();
      }
    };
    const fillGeo = (fc, fill, stroke, lw) => {
      for (const f of fc.features || []) {
        geomPath(f.geometry);
        if (fill) { ctx.fillStyle = fill(f); ctx.fill('evenodd'); }
        if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
      }
    };
    const d = base.data;
    fillGeo(d.neighbors, () => PAL.neighbor, PAL.russiaLine, 1);
    fillGeo(d.russia, () => PAL.russia, PAL.russiaLine, 1);
    const levels = new Set();
    fillGeo(d.raions, f => {
      const a = show.alerts ? base.alertFor(f.properties) : null;
      if (a) levels.add(a.level);
      return a ? (a.level === 'red' ? PAL.red : PAL.yellow) : PAL.land;
    });
    const occ = base.state.occupied;
    if (show.occupied && occ?.features?.length) {
      ctx.globalAlpha = 0.92; fillGeo(occ, () => PAL.occupied, PAL.occupiedLine, 1); ctx.globalAlpha = 1;
    }
    // danger over Russia / occupied (Russian sources)
    let ruCount = 0;
    if (show.russia) {
      ctx.fillStyle = 'rgba(31,181,204,0.32)'; ctx.strokeStyle = PAL.ruDanger; ctx.lineWidth = 1.6;
      for (const z of state.ru_zones || []) {
        const feat = z.unit && (d.russia.features.find(f => f.properties.key === z.unit)
          || d.raions.features.find(f => f.properties.id === z.unit) || d.oblasts.features.find(f => f.properties.key === z.unit));
        if (!inView(z.lat, z.lon, 3)) continue;
        ruCount++;
        if (feat && !/^(north|south|east|west)/.test(z.name)) { geomPath(feat.geometry); }
        else { ctx.beginPath(); ctx.arc(X(z.lon), Y(z.lat), kmPx(z.lat, feat ? 70 : 16), 0, Math.PI * 2); }
        ctx.fill(); ctx.stroke();
      }
    }
    fillGeo(d.raions, null, PAL.raionLine, 0.9);
    fillGeo(d.oblasts, null, PAL.oblastLine, 2.2);

    // threat areas
    for (const e of state.events || []) {
      if (e.kind !== 'threat' || !e.threat || !inView(e.lat, e.lon, 1)) continue;
      const c = (THREATS[e.threat] || THREATS.uav).color;
      ctx.beginPath(); ctx.arc(X(e.lon), Y(e.lat), kmPx(e.lat, e.precision === 'region' ? 60 : 16), 0, Math.PI * 2);
      ctx.setLineDash([8, 8]); ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]);
    }

    // labels
    const spanLon = bounds.getEast() - bounds.getWest();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const text = (s, x, y, size, color, weight = 400) => {
      ctx.font = `${weight} ${size}px ${FONT}`;
      ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(14,18,23,0.85)'; ctx.strokeText(s, x, y);
      ctx.fillStyle = color; ctx.fillText(s, x, y);
    };
    if (spanLon < 5.5) {
      for (const f of d.raions.features) {
        const [lon, lat] = f.properties.label;
        if (inView(lat, lon)) text(/Київ|Севастополь|зона/.test(f.properties.name) ? f.properties.name : `${f.properties.name} р-н`, X(lon), Y(lat), 15, PAL.labelMuted);
      }
    }
    if (spanLon >= 3) {
      for (const f of d.oblasts.features) {
        const [lon, lat] = f.properties.label;
        if (inView(lat, lon) && !['kyiv_city', 'sevastopol'].includes(f.properties.key)) text(f.properties.name.replace('Автономна Республіка ', ''), X(lon), Y(lat) + (spanLon < 5.5 ? 20 : 0), 19, PAL.label, 600);
      }
    }
    for (const [n, lat, lon, rank] of base.CITIES) {
      if (!inView(lat, lon) || (rank > 1 && spanLon > 12) || (rank > 2 && spanLon > 6)) continue;
      ctx.beginPath(); ctx.arc(X(lon), Y(lat), 3.5, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.textAlign = 'left'; text(n, X(lon) + 8, Y(lat), 17, '#ffffff', 600); ctx.textAlign = 'center';
    }

    // tracks: path so far, estimated leg, icon at the estimated position
    const shown = tracks.filter(t => {
      const p = predicted(t);
      return inView(p.lat, p.lon, 0.3) || t.points.some(q => inView(q.lat, q.lon));
    });
    for (const t of shown) {
      const c = tint((THREATS[t.threat] || THREATS.uav).color, 0.35);
      const pts = t.points.filter(q => q.precision === 'point');
      if (pts.length > 1) {
        ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath(); pts.forEach((q, i) => (i ? ctx.lineTo(X(q.lon), Y(q.lat)) : ctx.moveTo(X(q.lon), Y(q.lat))));
        ctx.strokeStyle = 'rgba(11,14,18,0.6)'; ctx.lineWidth = 7; ctx.stroke();
        ctx.strokeStyle = c; ctx.lineWidth = 3.4; ctx.setLineDash(t.confirmed ? [] : [10, 10]); ctx.stroke(); ctx.setLineDash([]);
        for (const q of pts.slice(0, -1)) { ctx.beginPath(); ctx.arc(X(q.lon), Y(q.lat), 3.6, 0, Math.PI * 2); ctx.fillStyle = c; ctx.fill(); }
      }
      const p = predicted(t);
      if (p.est) {
        ctx.beginPath(); ctx.moveTo(X(t.lon), Y(t.lat)); ctx.lineTo(X(p.lon), Y(p.lat));
        ctx.setLineDash([2, 7]); ctx.strokeStyle = c; ctx.lineWidth = 2.4; ctx.stroke(); ctx.setLineDash([]);
      }
    }
    const icons = await Promise.all(shown.map(t => image(mapSvg(t.threat, 64))));
    const boom = await image(explosion(48));
    for (const e of state.events || []) {
      if (e.kind === 'explosion' && boom && inView(e.lat, e.lon)) ctx.drawImage(boom, X(e.lon) - 15, Y(e.lat) - 15, 30, 30);
    }
    shown.forEach((t, i) => {
      const im = icons[i];
      const p = predicted(t);
      const x = X(p.lon), y = Y(p.lat);
      ctx.save();
      ctx.globalAlpha = t.status === 'active' ? (t.confirmed ? 1 : 0.6) : 0.4;
      ctx.translate(x, y);
      ctx.rotate(((t.precision === 'inbound' ? 0 : (p.brg ?? t.heading ?? 0)) * Math.PI) / 180);
      ctx.shadowColor = 'rgba(0,0,0,0.85)'; ctx.shadowBlur = 5;
      if (im) ctx.drawImage(im, -21, -21, 42, 42);
      ctx.restore();
      if (t.count > 1) {
        ctx.beginPath(); ctx.arc(x + 19, y - 17, 12, 0, Math.PI * 2);
        ctx.fillStyle = '#0b0e12'; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = colorOf(t); ctx.stroke();
        ctx.font = `700 14px ${FONT}`; ctx.fillStyle = '#fff'; ctx.fillText(String(t.count), x + 19, y - 16);
      }
    });

    // scale bar
    const cLat = (bounds.getNorth() + bounds.getSouth()) / 2;
    const km = niceKm(kmPx(cLat, 1) ? 220 / kmPx(cLat, 1) : 50);
    const bw = kmPx(cLat, km);
    const sx = 28, sy = HEAD + H - 30;
    ctx.fillStyle = 'rgba(15,19,24,0.75)'; ctx.fillRect(sx - 12, sy - 26, bw + 24, 42);
    ctx.strokeStyle = '#e7eaef'; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.moveTo(sx, sy - 6); ctx.lineTo(sx, sy); ctx.lineTo(sx + bw, sy); ctx.lineTo(sx + bw, sy - 6); ctx.stroke();
    ctx.textAlign = 'center'; ctx.font = `500 15px ${FONT}`; ctx.fillStyle = '#e7eaef'; ctx.fillText(`${km} km`, sx + bw / 2, sy - 15);
    ctx.restore();

    // ---- header
    const nowD = new Date();
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#e7eaef'; ctx.font = `700 34px ${FONT}`; ctx.fillText(title, 32, 52);
    const utc = nowD.toISOString().slice(11, 16);
    ctx.fillStyle = '#8e99aa'; ctx.font = `400 18px ${FONT}`;
    ctx.fillText(`${nowD.toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' })}, ${nowD.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · UTC ${utc} · Drone Map`, 32, 84);
    // counts of active targets in the area
    const counts = {};
    for (const t of shown) if (t.status === 'active' && t.confirmed) counts[t.threat] = (counts[t.threat] || 0) + (t.count || 1);
    const keys = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    let cx = W - 32;
    ctx.textAlign = 'right';
    const countIcons = await Promise.all(keys.map(k => image(mapSvg(k, 64))));
    keys.slice(0, 6).forEach((k, i) => {
      ctx.font = `700 30px ${FONT}`; ctx.fillStyle = '#ffffff';
      const label = String(counts[k]);
      ctx.fillText(label, cx, 62);
      const tw = ctx.measureText(label).width;
      if (countIcons[i]) ctx.drawImage(countIcons[i], cx - tw - 44, 30, 38, 38);
      ctx.font = `400 14px ${FONT}`; ctx.fillStyle = '#8e99aa'; ctx.fillText(THREATS[k].short, cx, 86);
      cx -= tw + 70;
    });
    if (!keys.length) { ctx.font = `500 18px ${FONT}`; ctx.fillStyle = '#8e99aa'; ctx.fillText('No confirmed targets in this area', W - 32, 62); }

    // ---- footer: legend of what is actually shown, sources
    const fy = HEAD + H;
    ctx.fillStyle = '#12161c'; ctx.fillRect(0, fy, W, FOOT);
    ctx.strokeStyle = '#232a33'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(0, fy + 0.5); ctx.lineTo(W, fy + 0.5); ctx.stroke();
    const legend = [];
    const types = [...new Set(shown.map(t => t.threat))];
    const typeIcons = await Promise.all(types.map(k => image(mapSvg(k, 48))));
    types.forEach((k, i) => legend.push({ img: typeIcons[i], label: THREATS[k].label }));
    if (levels.has('red')) legend.push({ swatch: PAL.red, label: 'Air alert, red level' });
    if (levels.has('yellow')) legend.push({ swatch: PAL.yellow, label: 'Air alert, yellow level' });
    if (show.occupied && occ?.features?.length) legend.push({ swatch: PAL.occupied, label: 'Occupied' });
    if (ruCount) legend.push({ swatch: PAL.ruDanger, label: 'Danger over Russia (RU sources)' });
    if ((state.events || []).some(e => e.kind === 'explosion' && inView(e.lat, e.lon))) legend.push({ img: boom, label: 'Explosions' });
    let lx = 32, ly = fy + 38;
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.font = `400 16px ${FONT}`;
    for (const it of legend) {
      const w = ctx.measureText(it.label).width + 42;
      if (lx + w > W - 32) { lx = 32; ly += 34; }
      if (it.img) ctx.drawImage(it.img, lx, ly - 13, 26, 26);
      else { ctx.fillStyle = it.swatch; ctx.fillRect(lx + 2, ly - 8, 22, 16); }
      ctx.fillStyle = '#c9d0da'; ctx.fillText(it.label, lx + 32, ly);
      lx += w + 18;
    }
    ctx.fillStyle = '#6f7a8a'; ctx.font = `400 13.5px ${FONT}`;
    ctx.fillText('Fused from public Telegram monitoring channels. Lines: reported path. Dotted: estimated since the last report. ' +
      'Districts © OCHA · Occupied © DeepState · Borders © OpenStreetMap', 32, fy + FOOT - 22);
    return cv;
  }

  function geojson(bounds, state, tracks, predicted) {
    const inB = (lat, lon) => bounds.contains([lat, lon]);
    const feats = [];
    for (const t of tracks) {
      if (!t.points.some(q => inB(q.lat, q.lon)) && !inB(t.lat, t.lon)) continue;
      const p = predicted(t);
      const props = { id: t.id, type: t.threat, label: t.label, count: t.count, status: t.status, confidence: t.confidence,
        confirmed: t.confirmed, last_report: new Date(t.last_seen * 1000).toISOString(), place: t.place,
        destination: t.dest?.name || null, sources: t.sources.map(s => s.channel) };
      feats.push({ type: 'Feature', properties: { ...props, kind: 'path' },
        geometry: { type: 'LineString', coordinates: t.points.map(q => [q.lon, q.lat]) } });
      feats.push({ type: 'Feature', properties: { ...props, kind: p.est ? 'estimated position' : 'last reported position' },
        geometry: { type: 'Point', coordinates: [p.lon, p.lat] } });
    }
    for (const e of state.events || []) if (inB(e.lat, e.lon)) {
      feats.push({ type: 'Feature', properties: { kind: e.kind, threat: e.threat, place: e.place, time: new Date(e.ts * 1000).toISOString() },
        geometry: { type: 'Point', coordinates: [e.lon, e.lat] } });
    }
    for (const z of state.ru_zones || []) if (inB(z.lat, z.lon)) {
      feats.push({ type: 'Feature', properties: { kind: 'danger over Russia', danger: z.kind, place: z.name, since: new Date(z.since * 1000).toISOString() },
        geometry: { type: 'Point', coordinates: [z.lon, z.lat] } });
    }
    return { type: 'FeatureCollection', generated: new Date().toISOString(),
      alerts: (state.alerts || []).map(a => ({ id: a.id, name: a.name, level: a.level, since: new Date(a.since * 1000).toISOString() })),
      features: feats };
  }

  return { render, geojson, areaName };
})();
