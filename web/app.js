(() => {
  'use strict';
  const { THREATS, svg, explosion, kill } = window.DMIcons;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // per-viewer preferences (best effort: storage may be unavailable)
  const prefs = {
    get(k, d) { try { const v = localStorage.getItem('dm.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('dm.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
  };

  const FAMILY_ORDER = ['kinzhal', 'ballistic', 'cruise', 'missile', 'kab', 'jet_shahed', 'shahed', 'uav', 'gerbera', 'recon', 'lancet', 'molniya', 'fpv'];
  const TIER_LABEL = { official: 'Official', recon: 'Recon', regional: 'Regional', aggregator: 'Aggregator' };

  const S = {
    state: null, sources: null, etag: null, lastFetchOk: 0, offline: false,
    selected: null, tab: 'targets',
    hidden: new Set(prefs.get('hidden', [])),
    showUnconfirmed: prefs.get('showUnconfirmed', true),
    showHistory: prefs.get('showHistory', true),
    showAlerts: prefs.get('showAlerts', false),
    me: prefs.get('me', null), radius: prefs.get('radius', 25), nearOn: prefs.get('nearOn', false),
    pickingMe: false, notified: new Set(), dismissed: new Set(prefs.get('dismissed', [])),
    follow: null, lastPos: new Map(),
    heat: { on: prefs.get('heatOn', false), period: prefs.get('heatPeriod', '24h'), kind: prefs.get('heatKind', 'all'),
            data: null, key: null, loading: false, loadedAt: 0, table: false },
  };
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ------------------------------------------------------------------ time & geo helpers
  const now = () => Date.now() / 1000;
  function ago(ts) {
    const s = Math.max(0, Math.round(now() - ts));
    if (s < 45) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return m ? `${h} h ${m} min ago` : `${h} h ago`;
  }
  const clock = ts => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const toRad = d => d * Math.PI / 180, toDeg = r => r * 180 / Math.PI;
  function distKm(a, b) {
    const dLat = toRad(b.lat - a.lat), dLon = toRad(b.lon - a.lon);
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(x)));
  }
  function project(lat, lon, brg, km) {
    const d = km / 6371, b = toRad(brg), p1 = toRad(lat), l1 = toRad(lon);
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
    const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
    return [toDeg(p2), toDeg(l2)];
  }
  const compass = h => h == null ? '' : ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(h / 45) % 8];
  const info = t => THREATS[t] || THREATS.uav;
  const tLabel = t => {
    const i = info(t.threat);
    const n = t.count > 1 ? ` ×${t.count}` : (t.group && !t.count ? ' (group)' : '');
    return i.short + n;
  };

  // ------------------------------------------------------------------ map
  const map = L.map('map', { zoomControl: false, minZoom: 4, maxZoom: 13, worldCopyJump: false, preferCanvas: false })
    .setView([48.7, 31.4], 6);
  const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
  // OpenStreetMap tiles (dark mode = CSS-inverted); Esri grey canvas as automatic fallback
  const TILES = {
    osm: { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxZoom: 19, attribution: '&copy; OpenStreetMap contributors', invert: true },
    esri_dark: { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', maxZoom: 16, attribution: 'Tiles &copy; Esri', invert: false },
    esri_light: { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', maxZoom: 16, attribution: 'Tiles &copy; Esri', invert: false },
  };
  let tiles = null, tileSource = 'osm', tileErrors = 0, tileLoads = 0;
  function setTiles(source) {
    tileSource = source || tileSource;
    if (tiles) map.removeLayer(tiles);
    const src = TILES[tileSource];
    tileErrors = 0; tileLoads = 0;
    tiles = L.tileLayer(src.url, { maxZoom: src.maxZoom, attribution: src.attribution, crossOrigin: true })
      .on('tileload', () => { tileLoads++; })
      .on('tileerror', () => {
        tileErrors++;
        if (tileSource === 'osm' && tileErrors >= 6 && tileLoads === 0) setTiles(darkQuery.matches ? 'esri_dark' : 'esri_light');
      })
      .addTo(map);
    $('#map').classList.toggle('dark-tiles', src.invert && darkQuery.matches);
  }
  setTiles('osm');
  darkQuery.addEventListener?.('change', () => setTiles(tileSource === 'osm' ? 'osm' : (darkQuery.matches ? 'esri_dark' : 'esri_light')));

  const layers = {
    alerts: L.layerGroup().addTo(map),
    areas: L.layerGroup().addTo(map),
    tracks: L.layerGroup().addTo(map),
    events: L.layerGroup().addTo(map),
    markers: L.layerGroup().addTo(map),
    me: L.layerGroup().addTo(map),
  };

  const visible = () => (S.state?.tracks || []).filter(t => !S.hidden.has(t.threat) && (S.showUnconfirmed || t.confirmed));

  // how far ahead the dotted course line reaches when only a direction is known (no speed is shown:
  // post times are too coarse to measure one)
  const LOOKAHEAD_KM = { shahed: 40, uav: 40, gerbera: 40, jet_shahed: 70, recon: 20, lancet: 12, molniya: 12, fpv: 8,
    cruise: 120, missile: 120, ballistic: 150, kinzhal: 150, kab: 25 };
  const lookahead = t => LOOKAHEAD_KM[t.threat] || 40;

  // Where the course line points: the reported destination town, or a point ahead on the heading.
  // A region as destination ("курсом на Чернігівщину") only gives a direction, not a place to draw to.
  function aimPoint(t) {
    if (t.precision === 'inbound') return null;
    if (t.dest && t.heading_source === 'dest' && t.dest.precision === 'point') return [t.dest.lat, t.dest.lon];
    if (t.heading != null) return project(t.lat, t.lon, t.heading, lookahead(t));
    return null;
  }

  // Angle on screen (clockwise from up) from a to b. The map is Web Mercator, so a straight line on
  // screen is not exactly the compass bearing over long distances; measuring in screen space makes the
  // icon point exactly along the course line drawn for it. Angles do not depend on the zoom level.
  function screenAngle(a, b) {
    const pa = map.project(L.latLng(a[0], a[1]), 8), pb = map.project(L.latLng(b[0], b[1]), 8);
    return (toDeg(Math.atan2(pb.x - pa.x, pa.y - pb.y)) + 360) % 360;
  }
  function iconAngle(t) {
    const aim = aimPoint(t);
    if (aim) return screenAngle([t.lat, t.lon], aim);
    if (t.heading != null && t.precision === 'inbound') {
      return screenAngle([t.lat, t.lon], project(t.lat, t.lon, t.heading, 30));
    }
    return null;
  }

  function arrowIcon(c, deg, faded) {
    return L.divIcon({ className: '', iconSize: [12, 12], iconAnchor: [6, 6],
      html: `<svg class="trk-arrow" viewBox="0 0 12 12" width="12" height="12" style="transform:rotate(${deg}deg);opacity:${faded ? 0.4 : 0.95}"><path d="M6 1.5 L10.5 10 L6 7.6 L1.5 10 Z" fill="${c}" stroke="#0b0e12" stroke-width="1" stroke-linejoin="round"/></svg>` });
  }

  // glide a marker from where it was last drawn to its new position
  function glide(marker, from, to) {
    if (reduceMotion.matches || !from || (from[0] === to[0] && from[1] === to[1])) return;
    if (distKm({ lat: from[0], lon: from[1] }, { lat: to[0], lon: to[1] }) > 400) return;
    marker.setLatLng(from);
    const t0 = performance.now(), dur = 1100;
    const step = now => {
      const k = Math.min(1, (now - t0) / dur), e = 1 - (1 - k) ** 3;
      marker.setLatLng([from[0] + (to[0] - from[0]) * e, from[1] + (to[1] - from[1]) * e]);
      if (k < 1 && marker._map) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function zFor(t) {
    let z = 100 - FAMILY_ORDER.indexOf(t.threat) * 5;
    if (t.status !== 'active') z -= 200;
    if (S.selected === t.id) z += 1000;
    return z;
  }

  function tipHtml(t) {
    const where = t.precision === 'inbound' ? `heading to ${esc(t.place)}` : esc(t.place);
    const dest = t.dest && t.precision !== 'inbound' ? ` → ${esc(t.dest.name)}`
      : (t.heading != null && t.precision !== 'inbound' ? ` · heading ${compass(t.heading)}` : '');
    const unc = t.confirmed ? '' : ' · <b style="color:var(--warn)">unconfirmed</b>';
    return `<b>${esc(tLabel(t))}</b> · ${where}${dest}<br><span style="color:var(--muted)">${ago(t.last_seen)} · ${Math.round(t.confidence * 100)}% confidence${unc}</span>`;
  }

  function drawTrack(t) {
    const c = info(t.threat).color;
    const sel = S.selected === t.id;
    const faded = t.status !== 'active' || !t.confirmed;
    const real = t.points.filter(p => p.precision !== 'inbound');

    if ((S.showHistory || sel) && real.length > 1) {
      // coarse leading points (region centroid / launch area) get a faint dashed leg, observed points a solid line
      const firstExact = real.findIndex(p => p.precision === 'point');
      const solid = firstExact >= 0 ? real.slice(firstExact) : [];
      const lead = firstExact > 0 ? real.slice(0, firstExact + 1) : (firstExact < 0 ? real : []);
      if (lead.length > 1) {
        L.polyline(lead.map(p => [p.lat, p.lon]), { color: c, weight: 2, opacity: faded ? 0.2 : 0.45, dashArray: '3 8', interactive: false })
          .addTo(layers.tracks);
      }
      if (solid.length > 1) {
        L.polyline(solid.map(p => [p.lat, p.lon]), {
          color: c, weight: sel ? 4.5 : 2.8, opacity: faded ? 0.35 : 0.9, lineCap: 'round', lineJoin: 'round',
          dashArray: t.confirmed ? null : '6 7', interactive: false,
        }).addTo(layers.tracks);
        // arrowheads mid-leg show which way the target flew
        for (let i = 1; i < solid.length; i++) {
          const a = solid[i - 1], b = solid[i];
          if (distKm(a, b) < 8) continue;
          const mid = [(a.lat + b.lat) / 2, (a.lon + b.lon) / 2];
          L.marker(mid, { icon: arrowIcon(c, screenAngle([a.lat, a.lon], [b.lat, b.lon]), faded), interactive: false, keyboard: false })
            .addTo(layers.tracks);
        }
      }
      real.slice(0, -1).forEach(p => {
        L.circleMarker([p.lat, p.lon], { radius: sel ? 4 : 3, color: '#0b0e12', weight: 1, fillColor: c, fillOpacity: faded ? 0.35 : 0.95 })
          .bindTooltip(`${esc(p.place)} · ${clock(p.ts)}`, { className: 'dm-tip', direction: 'top' })
          .on('click', () => select(t.id, false))
          .addTo(layers.tracks);
      });
    }
    if (t.precision === 'region' && t.status !== 'ended') {
      L.circle([t.lat, t.lon], { radius: 32000, color: c, weight: 1, opacity: 0.4, fillOpacity: 0.05, dashArray: '3 5', interactive: false })
        .addTo(layers.tracks);
    }
    if (t.status === 'active' && t.precision !== 'inbound') {
      const target = aimPoint(t);
      if (target) {
        L.polyline([[t.lat, t.lon], target], { color: c, weight: sel ? 3 : 2, opacity: faded ? 0.3 : 0.75, dashArray: '1 7', lineCap: 'round', interactive: false })
          .addTo(layers.tracks);
      }
      if (t.dest && t.heading_source === 'dest' && t.dest.precision === 'point') {
        L.circleMarker([t.dest.lat, t.dest.lon], { radius: 5, color: c, weight: 2, dashArray: '2 3', fill: false, opacity: faded ? 0.4 : 0.9 })
          .bindTooltip(`→ ${esc(t.dest.name)}`, { permanent: sel, className: 'dest-label', direction: 'right', offset: [7, 0] })
          .addTo(layers.tracks);
      }
    }
    const hot = ['ballistic', 'kinzhal'].includes(t.threat) && t.status === 'active';
    const cls = ['mk', t.status, t.confirmed ? '' : 'unconf', sel ? 'sel' : '', t.precision === 'inbound' ? 'inbound' : '', hot ? 'hot' : ''].join(' ');
    // FPV icons are symmetric quadcopters; every other icon points along the course
    const ang = t.threat === 'fpv' ? null : iconAngle(t);
    const badge = t.count > 1 ? `<span class="mk-n">${t.count}</span>` : '';
    const icon = L.divIcon({
      className: '', iconSize: [36, 36], iconAnchor: [18, 18],
      html: `<div class="${cls} ${ang == null ? 'no-hdg' : ''}" style="--c:${c}"><div class="mk-rot" style="transform:rotate(${ang ?? 0}deg)">${svg(t.threat, c, 32)}</div>${badge}</div>`,
    });
    const pos = [t.lat, t.lon];
    const m = L.marker(pos, { icon, zIndexOffset: zFor(t), title: `${info(t.threat).label} – ${t.place}`, riseOnHover: true })
      .bindTooltip(tipHtml(t), { className: 'dm-tip', direction: 'top', offset: [0, -18] })
      .on('click', () => select(t.id, false))
      .addTo(layers.markers);
    glide(m, S.lastPos.get(t.id), pos);
    S.lastPos.set(t.id, pos);
  }

  function drawEvent(e) {
    if (e.threat && S.hidden.has(e.threat)) return;
    if (!S.showUnconfirmed && !e.confirmed) return;
    const age = now() - e.last_ts;
    if (e.kind === 'explosion') {
      const icon = L.divIcon({ className: '', html: `<div class="ex ${age > 900 ? 'old' : ''}">${explosion(26)}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] });
      L.marker([e.lat, e.lon], { icon, zIndexOffset: 500 })
        .bindTooltip(`<b>Explosions</b> · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)} · ${e.sources.length} source(s)</span>`, { className: 'dm-tip', direction: 'top' })
        .addTo(layers.events);
    } else if (e.kind === 'kill') {
      const icon = L.divIcon({ className: '', html: `<div class="kill-mk">${kill(18)}</div>`, iconSize: [18, 18], iconAnchor: [9, 9] });
      L.marker([e.lat, e.lon], { icon, zIndexOffset: -50 })
        .bindTooltip(`<b>Shot down</b>${e.threat ? ' · ' + esc(info(e.threat).short) : ''} · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)}</span>`, { className: 'dm-tip', direction: 'top' })
        .addTo(layers.events);
    } else if (e.kind === 'threat' && e.threat) {
      const c = info(e.threat).color;
      L.circle([e.lat, e.lon], { radius: e.precision === 'region' ? 75000 : 20000, color: c, weight: 2, dashArray: '6 6', fillColor: c, fillOpacity: 0.08, className: 'threat-area' })
        .bindTooltip(`<b>${esc(info(e.threat).label)} threat</b> · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)}</span>`, { className: 'dm-tip', sticky: true })
        .addTo(layers.areas);
    }
  }

  function drawAlerts() {
    layers.alerts.clearLayers();
    if (!S.showAlerts) return;
    for (const a of S.state?.alerts || []) {
      if (a.lat == null) continue;
      L.circle([a.lat, a.lon], { radius: a.oblast === 'kyiv_city' ? 18000 : 85000, color: '#f43f5e', weight: 1, opacity: 0.35, fillOpacity: 0.07, interactive: false })
        .addTo(layers.alerts);
    }
  }

  function drawMe() {
    layers.me.clearLayers();
    if (!S.me) return;
    L.circle([S.me.lat, S.me.lon], { radius: S.radius * 1000, color: '#4cc2ff', weight: 1.5, opacity: S.nearOn ? 0.8 : 0.35, fillOpacity: 0.05, dashArray: '4 6', interactive: false }).addTo(layers.me);
    L.marker([S.me.lat, S.me.lon], { icon: L.divIcon({ className: '', html: '<div class="me-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), interactive: false, zIndexOffset: 2000 }).addTo(layers.me);
  }

  function renderMap() {
    layers.tracks.clearLayers(); layers.markers.clearLayers(); layers.events.clearLayers(); layers.areas.clearLayers();
    if (!S.state) return;
    for (const e of S.state.events) drawEvent(e);
    for (const t of visible().slice().reverse()) drawTrack(t);
    drawAlerts();
    drawMe();
    drawHeat();
    if (S.follow) {
      const t = S.state.tracks.find(x => x.id === S.follow);
      if (t && t.status !== 'ended') map.panTo([t.lat, t.lon], { animate: !reduceMotion.matches, duration: 0.8 });
      else S.follow = null;
    }
  }

  // ------------------------------------------------------------------ header: status, summary, banners
  function updateStatus() {
    const el = $('#status');
    const txt = $('.txt', el);
    el.className = 'status';
    if (S.state?.mode === 'demo') {
      el.classList.add('demo'); txt.textContent = 'Demo data';
      el.title = 'Replaying a scripted scenario. Start without --demo for live Telegram data.';
      return;
    }
    if (S.offline) { el.classList.add('offline'); txt.textContent = 'Offline'; el.title = 'Cannot reach the server; showing the last data received.'; return; }
    const chans = S.sources ? S.sources.groups.flatMap(g => g.channels) : [];
    const lastSrc = Math.max(0, ...chans.map(c => c.last_ok || 0));
    const okCount = chans.filter(c => c.state === 'ok').length;
    const pending = chans.filter(c => c.state === 'pending').length;
    if (S.sources && !okCount && pending) {
      el.classList.add('lagging'); txt.textContent = 'Starting…';
      el.title = `Reading ${chans.length} channels for the first time`;
      return;
    }
    if (S.sources && (!lastSrc || now() - lastSrc > 180)) {
      el.classList.add('lagging'); txt.textContent = 'No fresh data';
      el.title = 'No Telegram channel has been read successfully in the last 3 minutes.';
      return;
    }
    el.classList.add('live'); txt.textContent = 'Live';
    el.title = `${okCount} channels OK · updated ${S.state ? ago(S.state.generated_at) : ''}`;
  }

  function renderSummary() {
    const stats = S.state?.stats || {};
    const keys = FAMILY_ORDER.filter(k => stats[k]);
    $('#summary').innerHTML = keys.length ? keys.map(k => `<span class="sum-chip" title="${esc(info(k).label)}: ${stats[k].tracks} track(s)">${svg(k, null, 18)}<b>${stats[k].objects}</b> ${esc(info(k).short)}</span>`).join('')
      : `<span class="sum-chip" style="padding-left:9px;color:var(--muted)">No active confirmed threats</span>`;
  }

  function renderBanners() {
    const list = (S.state?.banners || []).filter(b => !S.dismissed.has(b.key)).slice(0, 2);
    requestAnimationFrame(() => document.documentElement.style.setProperty('--banner-h', $('#banners').offsetHeight + 'px'));
    $('#banners').innerHTML = list.map(b => {
      const kind = b.kind === 'aviation' ? 'Aviation' : (b.kind.startsWith('threat:') ? info(b.kind.slice(7)).short + ' threat' : 'Notice');
      return `<div class="banner ${b.kind === 'aviation' ? 'aviation' : ''}"><span class="b-kind">${esc(kind)}</span>
        <span class="b-text" title="${esc(b.text)}">${esc(b.text)}</span><span class="b-time">${clock(b.ts)} · @${esc(b.channel)}</span>
        <button data-dismiss="${esc(b.key)}" aria-label="Dismiss">×</button></div>`;
    }).join('');
  }
  $('#banners').addEventListener('click', e => {
    const k = e.target.closest('[data-dismiss]')?.dataset.dismiss;
    if (!k) return;
    S.dismissed.add(k); prefs.set('dismissed', [...S.dismissed].slice(-50)); renderBanners();
    requestAnimationFrame(() => document.documentElement.style.setProperty('--banner-h', $('#banners').offsetHeight + 'px'));
  });

  // ------------------------------------------------------------------ filters
  function renderFilters() {
    const counts = {};
    for (const t of S.state?.tracks || []) if (t.status !== 'ended') counts[t.threat] = (counts[t.threat] || 0) + 1;
    const present = FAMILY_ORDER.filter(k => counts[k] || S.hidden.has(k));
    const chips = present.map(k => `<button class="chip ${S.hidden.has(k) ? 'off' : ''}" data-type="${k}" title="${esc(info(k).label)}" aria-pressed="${!S.hidden.has(k)}">
      ${svg(k, null, 18)}${esc(info(k).short)} <span class="n">${counts[k] || 0}</span></button>`);
    chips.push(`<button class="chip opt ${S.showUnconfirmed ? 'on' : ''}" data-opt="showUnconfirmed" title="Show reports that only aggregators have made">Unconfirmed</button>`);
    chips.push(`<button class="chip opt ${S.showHistory ? 'on' : ''}" data-opt="showHistory" title="Show flown path of every target">Tracks</button>`);
    chips.push(`<button class="chip opt ${S.showAlerts ? 'on' : ''}" data-opt="showAlerts" title="Shade regions under air-raid alert">Alert zones</button>`);
    $('#filters').innerHTML = chips.join('');
  }
  $('#filters').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.type) {
      const k = b.dataset.type;
      S.hidden.has(k) ? S.hidden.delete(k) : S.hidden.add(k);
      prefs.set('hidden', [...S.hidden]);
    } else if (b.dataset.opt) {
      S[b.dataset.opt] = !S[b.dataset.opt];
      prefs.set(b.dataset.opt, S[b.dataset.opt]);
    }
    renderAll(true);
  });

  // ------------------------------------------------------------------ panel: targets
  function confBar(c) {
    const cls = c >= 0.8 ? '' : c >= 0.5 ? 'mid' : 'low';
    return `<span class="conf ${cls}" title="${Math.round(c * 100)}% confidence"><i style="width:${Math.round(c * 100)}%"></i></span>`;
  }

  function targetRow(t) {
    const where = t.precision === 'inbound' ? `heading to ${t.place}` : t.place;
    const dest = t.dest && t.precision !== 'inbound' ? ` → ${t.dest.name}` : (t.heading != null && t.precision !== 'inbound' ? ` · heading ${compass(t.heading)}` : '');
    let tag = '';
    if (t.status === 'ended') tag = t.ended === 'destroyed' ? '<span class="tag destroyed">destroyed</span>' : `<span class="tag ended">${esc(t.ended)}</span>`;
    else if (!t.confirmed) tag = '<span class="tag unconf">unconfirmed</span>';
    else if (t.status === 'stale') tag = '<span class="tag stale">no update</span>';
    return `<div class="row ${S.selected === t.id ? 'sel' : ''} ${t.status !== 'active' ? 'dim' : ''}" data-track="${t.id}" tabindex="0">
      <div class="ic">${svg(t.threat, null, 26)}</div>
      <div class="main"><div class="t1">${esc(info(t.threat).short)}${t.count > 1 ? `<span class="cnt">×${t.count}</span>` : ''} ${tag}</div>
        <div class="t2">${esc(where + dest)}</div></div>
      <div class="side">${ago(t.last_seen)}<br>${confBar(t.confidence)}</div></div>`;
  }

  function renderTargets() {
    const all = visible();
    const active = all.filter(t => t.status === 'active');
    const rest = all.filter(t => t.status !== 'active');
    $('#tabCountTargets').textContent = active.length || '';
    let html = '';
    if (!all.length) {
      html = emptyExplanation();
    } else {
      if (active.length) html += `<div class="section-title">Active · ${active.length}</div>` + active.map(targetRow).join('');
      if (rest.length) html += `<div class="section-title">Ended or no recent update · ${rest.length}</div>` + rest.map(targetRow).join('');
    }
    $('#tab-targets').innerHTML = html;
  }

  // why is the list empty? channels still loading, Telegram unreachable, or really quiet
  function emptyExplanation() {
    const chans = S.sources ? S.sources.groups.flatMap(g => g.channels) : [];
    const ok = chans.filter(c => c.state === 'ok');
    const failing = chans.filter(c => c.state === 'error');
    const pending = chans.filter(c => c.state === 'pending');
    const filtered = S.hidden.size ? ' Some threat types are switched off in the filters.' : '';
    if (S.offline) return `<div class="empty"><b>Can't reach the Drone Map server</b>Is the terminal window with <code>python run.py</code> still open?</div>`;
    if (S.state?.mode !== 'demo' && chans.length && !ok.length && pending.length) {
      return `<div class="empty"><b>Reading the channels…</b>Checking ${chans.length} Telegram channels for the first time. This takes about a minute.</div>`;
    }
    if (S.state?.mode !== 'demo' && chans.length && !ok.length && failing.length) {
      return `<div class="empty" style="text-align:left"><b style="text-align:center">Can't reach Telegram</b>
        None of the ${chans.length} channels could be read. Open <a href="https://t.me/s/kpszsu" target="_blank" rel="noopener">t.me/s/kpszsu</a>
        in your browser: if it doesn't load, Telegram is blocked on this network or by a firewall, VPN or antivirus.
        <br><br><span style="color:var(--faint);font-size:12px">Error: ${esc(failing[0].error || 'unknown')}</span></div>`;
    }
    const newest = ok.reduce((a, c) => (c.last_post_ts || 0) > (a?.last_post_ts || 0) ? c : a, null);
    const posts = S.state?.messages_in_window || 0;
    const last = newest?.last_post_ts ? ` Latest post ${ago(newest.last_post_ts)} from @${esc(newest.handle)}.` : '';
    return `<div class="empty"><b>Quiet skies</b>No drones or missiles reported right now. ${ok.length ? `Reading ${ok.length} of ${chans.length} channels, ${posts} posts from the last hours checked.` : ''}${last}${filtered}</div>`;
  }

  // ------------------------------------------------------------------ panel: detail
  function renderDetail() {
    const t = (S.state?.tracks || []).find(x => x.id === S.selected);
    if (!t) { S.selected = null; showTab(S.tab); return; }
    const c = info(t.threat).color;
    const statusTxt = t.status === 'ended' ? (t.ended === 'destroyed' ? 'Destroyed' : `Ended (${t.ended})`) : t.status === 'stale' ? 'No recent update' : 'Active';
    const conf = Math.round(t.confidence * 100);
    const confNote = t.confirmed
      ? (t.sources.length > 1 ? `${t.sources.length} independent channels` : 'single source')
      : 'only aggregator channels so far, waiting for an official or regional source';
    const path = t.points.filter(p => p.precision !== 'inbound').map(p => `<li style="--c:${c}">${esc(p.place)}${p.precision === 'region' ? ' <span class="tag">region</span>' : p.precision === 'origin' ? ' <span class="tag">launch area</span>' : ''}<span class="tm">${clock(p.ts)}</span></li>`).join('');
    const destLi = t.dest ? `<li class="dest" style="--c:${c}">→ ${esc(t.dest.name)} <span class="tm">reported destination</span></li>` : '';
    const msgs = t.messages.map(m => {
      const link = S.state.mode === 'demo' ? `@${esc(m.channel)}` : `<a href="https://t.me/${encodeURIComponent(m.channel)}/${m.id}" target="_blank" rel="noopener">@${esc(m.channel)}</a>`;
      return `<div class="msg"><div class="mh">${link}<span>${clock(m.ts)}</span></div><div class="mt">${esc(m.text)}</div></div>`;
    }).join('');
    $('#detail').innerHTML = `
      <div class="detail-head"><button class="back" id="backBtn">← Back</button>
        ${t.status !== 'ended' ? `<button class="back ${S.follow === t.id ? 'on' : ''}" id="followBtn" aria-pressed="${S.follow === t.id}" title="Keep this target in the middle of the map as new reports arrive">${S.follow === t.id ? 'Following' : 'Follow on map'}</button>` : ''}</div>
      <div class="detail-title"><div class="ic">${svg(t.threat, null, 40)}</div>
        <div><h2>${esc(info(t.threat).label)}${t.count > 1 ? ` ×${t.count}` : ''}</h2>
        <div class="sub">${esc(statusTxt)} · last report ${ago(t.last_seen)}</div></div></div>
      <dl class="kv">
        <dt>Position</dt><dd>${esc(t.precision === 'inbound' ? 'not yet seen, reported heading to ' + t.place : t.place)}</dd>
        <dt>Heading</dt><dd>${headingText(t)}</dd>
        ${t.dest && t.heading_source !== 'dest' ? `<dt>Reported to</dt><dd>${esc(t.dest.name)}</dd>` : ''}
        <dt>Confidence</dt><dd>${conf}% ${confBar(t.confidence)}<br><span style="color:var(--muted);font-size:12px">${esc(confNote)}</span></dd>
        <dt>First seen</dt><dd>${clock(t.first_seen)} (${ago(t.first_seen)})</dd>
        ${t.destroyed ? `<dt>Shot down</dt><dd>${t.destroyed}</dd>` : ''}
        ${t.origin ? `<dt>Launched from</dt><dd>${esc(t.origin.name)}</dd>` : ''}
      </dl>
      <div class="section-title">Path</div><ul class="path">${path}${destLi}</ul>
      <div class="section-title">Sources · ${t.sources.length}</div>
      <div class="srcs">${t.sources.map(s => `<span title="${esc(TIER_LABEL[s.tier])}"><i class="tier-dot tier-${s.tier}"></i>${esc(s.name)}</span>`).join('')}</div>
      <div class="section-title">Reports</div>${msgs}`;
    $('#backBtn').onclick = () => select(null);
    const fb = $('#followBtn');
    if (fb) fb.onclick = () => {
      S.follow = S.follow === t.id ? null : t.id;
      if (S.follow) map.flyTo([t.lat, t.lon], Math.max(map.getZoom(), 8), { duration: 0.6 });
      renderDetail();
    };
  }

  const HEADING_SOURCE = {
    dest: 'towards the reported destination',
    reported: 'course given in the reports',
    track: 'from the path it has flown',
  };
  function headingText(t) {
    if (t.heading == null) return t.dest ? '→ ' + esc(t.dest.name) : 'unknown';
    const where = t.dest && t.heading_source === 'dest' ? '→ ' + esc(t.dest.name) + ' ' : '';
    return `${where}${compass(t.heading)} (${Math.round(t.heading)}°)<br><span style="color:var(--muted);font-size:12px">${esc(HEADING_SOURCE[t.heading_source] || '')}</span>`;
  }

  // ------------------------------------------------------------------ panel: feed
  function renderFeed() {
    const feed = S.state?.feed || [];
    if (!feed.length) { $('#tab-feed').innerHTML = `<div class="empty"><b>No reports yet</b>Messages from the channels appear here as they arrive.</div>`; return; }
    $('#tab-feed').innerHTML = feed.slice(0, 120).map(f => {
      const icons = (f.threats || []).slice(0, 3).map(k => svg(k, null, 16)).join('');
      const link = S.state.mode === 'demo' ? '' : ` · <a href="https://t.me/${encodeURIComponent(f.channel)}/${f.id}" target="_blank" rel="noopener">open</a>`;
      const dim = !f.kinds.length || (f.kinds.length === 1 && f.kinds[0] === 'summary');
      return `<div class="feed-item ${dim ? 'dim' : ''}"><div class="fh"><i class="tier-dot tier-${f.tier}" title="${esc(TIER_LABEL[f.tier])}"></i>
        <span class="ch">@${esc(f.channel)}</span><span>${clock(f.ts)}${link}</span><span class="ics">${icons}</span></div>
        <div class="ft">${esc(f.text)}</div></div>`;
    }).join('');
  }

  // ------------------------------------------------------------------ panel: alerts
  function renderAlertsTab() {
    const alerts = S.state?.alerts || [];
    const banners = S.state?.banners || [];
    $('#tabCountAlerts').textContent = alerts.length || '';
    const legend = FAMILY_ORDER.map(k => `<div>${svg(k, null, 20)}${esc(info(k).label)}</div>`).join('');
    $('#tab-alerts').innerHTML = `
      <div class="section-title">Near me</div>
      <div class="setting"><span>Warn when a confirmed target is within</span>
        <select id="radiusSel">${[10, 25, 50, 100].map(r => `<option value="${r}" ${S.radius === r ? 'selected' : ''}>${r} km</option>`).join('')}</select></div>
      <div class="setting"><span>${S.me ? `Location set (${S.me.lat.toFixed(2)}, ${S.me.lon.toFixed(2)})` : 'No location set'}</span>
        <span style="display:flex;gap:6px"><button class="btn" id="gpsBtn">Use GPS</button><button class="btn" id="pickBtn">Pick on map</button></span></div>
      <div class="setting"><span>Near-me warnings</span><button class="btn ${S.nearOn ? 'btn-accent' : ''}" id="nearToggle">${S.nearOn ? 'On' : 'Off'}</button></div>
      ${banners.length ? `<div class="section-title">Notices</div>` + banners.map(b => `<div class="alert-row"><span class="ad" style="background:var(--warn)"></span><span class="an" style="font-weight:500">${esc(b.text)}</span><span class="at">${clock(b.ts)}</span></div>`).join('') : ''}
      <div class="section-title">Air-raid alerts · ${alerts.length}</div>
      ${alerts.length ? alerts.map(a => `<div class="alert-row"><span class="ad"></span><span class="an">${esc(a.name)}</span><span class="at">since ${clock(a.since)}</span></div>`).join('')
        : '<div class="empty" style="padding:14px">No active air-raid alerts reported.</div>'}
      <div class="section-title">Legend</div><div class="legend">${legend}
        <div>${explosion(18)}Explosions reported</div><div>${kill(16)}Shot down</div></div>
      <div class="section-title">How confidence works</div>
      <p style="color:var(--muted);font-size:12.5px;margin:0 4px">Each target merges reports from several channels. Official sources weigh most, then reconnaissance and regional observers.
      Aggregators only count when they agree with someone else; a target seen only by aggregators is shown faded with a “?”. Solid lines are the flown path,
      dotted lines the reported destination or heading.</p>`;
    $('#radiusSel').onchange = e => { S.radius = +e.target.value; prefs.set('radius', S.radius); drawMe(); checkNear(); };
    $('#gpsBtn').onclick = locate;
    $('#pickBtn').onclick = () => { S.pickingMe = true; toast('Tap the map to set your location'); collapseSheet(); };
    $('#nearToggle').onclick = () => setNear(!S.nearOn);
  }

  // ------------------------------------------------------------------ heatmap (last 24 h / 7 days / 28 days)
  const HEAT_PERIODS = [['24h', '24 hours'], ['7d', '7 days'], ['28d', '28 days']];
  const HEAT_KINDS = [['all', 'All'], ['drone', 'Drones'], ['missile', 'Missiles'], ['kab', 'KAB'], ['explosion', 'Explosions']];
  const HEAT_KIND_TEXT = { all: 'drones, missiles & KABs', drone: 'drones (all types)', missile: 'missiles (all types)', kab: 'guided bombs (KAB)', explosion: 'explosions' };
  // one-hue sequential ramp (blue 100–700); in dark mode the light end means "most"
  const HEAT_RAMP = {
    dark: { 0.15: '#0f4a96', 0.35: '#2370cd', 0.55: '#338ced', 0.75: '#84b9f3', 1: '#cce3fd' },
    light: { 0.15: '#9dc8f7', 0.35: '#519ced', 0.55: '#257de0', 0.75: '#1757ac', 1: '#0e3d7e' },
  };
  const FAMILY_SERIES = [['drone', 'Drones', 'shahed'], ['missile', 'Missiles', 'cruise'], ['kab', 'KAB', 'kab']];
  let heatLayer = null;

  function heatKey() { return `${S.heat.period}|${S.heat.kind}`; }

  async function loadHeat(force = false) {
    const key = heatKey();
    if (S.heat.loading || (!force && S.heat.key === key && Date.now() - S.heat.loadedAt < 60000)) return;
    S.heat.loading = true;
    if (S.heat.key !== key) { S.heat.data = null; if (S.tab === 'history' && !S.selected) renderHistory(); }
    try {
      const q = new URLSearchParams({ period: S.heat.period, kind: S.heat.kind, tzo: new Date().getTimezoneOffset() });
      const r = await fetch('/api/heatmap?' + q, { cache: 'no-store' });
      if (r.ok && heatKey() === key) { S.heat.data = await r.json(); S.heat.key = key; S.heat.loadedAt = Date.now(); }
    } catch { /* offline: keep what we have */ }
    S.heat.loading = false;
    if (heatKey() !== key) return loadHeat(true);
    drawHeat();
    if (S.tab === 'history' && !S.selected) renderHistory();
  }

  function drawHeat() {
    const d = S.heat.data;
    const btn = $('#heatBtn');
    btn.classList.toggle('on', S.heat.on); btn.setAttribute('aria-pressed', S.heat.on);
    const legend = $('#heatLegend');
    if (!S.heat.on || !d || !window.L.heatLayer) {
      if (heatLayer) { map.removeLayer(heatLayer); heatLayer = null; }
      legend.hidden = !S.heat.on;
      if (S.heat.on) legend.innerHTML = `<span class="hl-t">Heatmap</span><span class="hl-s">loading…</span>`;
      return;
    }
    // maxZoom = minZoom: full intensity at every zoom (the points are already merged per place on the server)
    const dense = d.places > 120;
    const opts = { radius: dense ? 16 : 22, blur: dense ? 14 : 18, minOpacity: dense ? 0.25 : 0.35, maxZoom: map.getMinZoom(), max: d.scale,
      gradient: darkQuery.matches ? HEAT_RAMP.dark : HEAT_RAMP.light };
    if (!heatLayer) heatLayer = L.heatLayer(d.points, opts).addTo(map);
    else { heatLayer.setOptions(opts); heatLayer.setLatLngs(d.points); }
    const period = HEAT_PERIODS.find(p => p[0] === d.period)?.[1] || d.period;
    const grad = Object.entries(opts.gradient).sort((a, b) => a[0] - b[0]).map(([k, v]) => `${v} ${k * 100}%`).join(',');
    legend.hidden = false;
    legend.innerHTML = `<span class="hl-t">Heatmap · last ${esc(period)}</span>
      <span class="hl-s">${esc(HEAT_KIND_TEXT[d.kind])} · ${d.observations.toLocaleString()} reported position${d.observations === 1 ? '' : 's'}</span>
      <span class="hl-bar"><i style="background:linear-gradient(90deg,${grad})"></i></span><span class="hl-ends"><span>fewer</span><span>more reports</span></span>`;
  }

  function setHeat(patch) {
    Object.assign(S.heat, patch);
    prefs.set('heatOn', S.heat.on); prefs.set('heatPeriod', S.heat.period); prefs.set('heatKind', S.heat.kind);
    if (S.heat.on || S.tab === 'history') loadHeat();
    drawHeat();
    if (S.tab === 'history' && !S.selected) renderHistory();
  }
  $('#heatBtn').addEventListener('click', () => {
    setHeat({ on: !S.heat.on });
    toast(S.heat.on ? 'Heatmap on. Change the period in the Heatmap tab.' : 'Heatmap off');
  });
  $('#heatLegend').addEventListener('click', () => { S.selected = null; showTab('history'); expandSheet(); });
  darkQuery.addEventListener?.('change', drawHeat);

  function bucketLabel(t, step, long = false) {
    const d = new Date(t * 1000);
    if (step < 86400) {
      const h = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return long ? `${d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}, ${h}–${new Date((t + step) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : h;
    }
    return long ? d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' }) : d.toLocaleDateString([], { day: 'numeric', month: 'short' });
  }

  function seriesFor(d) {
    if (d.kind === 'all') return FAMILY_SERIES.map(([key, label, icon], i) => ({ key, label, icon, color: `var(--s${i + 1})` }));
    const label = HEAT_KINDS.find(k => k[0] === d.kind)?.[1] || 'Reports';
    return [{ key: '*', label, color: 'var(--s1)' }];
  }
  const valOf = (row, key) => key === '*' ? Object.entries(row).reduce((a, [k, v]) => k === 't' ? a : a + v, 0) : (row[key] || 0);

  // stacked columns: one per hour (24 h) or per day (7 / 28 days)
  function chartSvg(d, series) {
    const rows = d.series, W = 360, H = 132, padL = 28, padR = 6, padT = 8, padB = 22;
    const totals = rows.map(r => series.reduce((a, s) => a + valOf(r, s.key), 0));
    const max = Math.max(1, ...totals);
    const nice = max <= 5 ? Math.ceil(max) : max <= 10 ? 10 : Math.ceil(max / (max <= 50 ? 10 : max <= 200 ? 50 : 100)) * (max <= 50 ? 10 : max <= 200 ? 50 : 100);
    const plotW = W - padL - padR, plotH = H - padT - padB, slot = plotW / rows.length;
    const bw = Math.max(3, Math.min(24, slot * 0.68)), y = v => padT + plotH - (v / nice) * plotH;
    const grid = [nice / 2, nice].map(v => `<line x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" class="ch-grid"/>
      <text x="${padL - 5}" y="${y(v) + 3.5}" class="ch-tick" text-anchor="end">${Math.round(v)}</text>`).join('');
    const every = rows.length > 14 ? Math.ceil(rows.length / 6) : rows.length > 8 ? 2 : 1;
    let bars = '', ticks = '', hits = '';
    rows.forEach((r, i) => {
      const x = padL + i * slot + (slot - bw) / 2;
      let base = 0;
      const segs = series.map(s => ({ s, v: valOf(r, s.key) })).filter(x => x.v > 0);
      segs.forEach((g, j) => {
        const y0 = y(base), y1 = y(base + g.v);
        const gap = j > 0 ? 2 : 0;                             // 2px surface gap between stacked segments
        const top = y1, bottom = y0 - gap, h = Math.max(0, bottom - top);
        if (h > 0.5) {
          const last = j === segs.length - 1, rr = last ? Math.min(4, h, bw / 2) : 0;
          bars += rr ? `<path d="M${x},${bottom} V${top + rr} Q${x},${top} ${x + rr},${top} H${x + bw - rr} Q${x + bw},${top} ${x + bw},${top + rr} V${bottom} Z" fill="${g.s.color}"/>`
            : `<rect x="${x}" y="${top}" width="${bw}" height="${h}" fill="${g.s.color}"/>`;
        }
        base += g.v;
      });
      if (i % every === 0) ticks += `<text x="${x + bw / 2}" y="${H - 6}" class="ch-tick" text-anchor="middle">${esc(bucketLabel(r.t, d.step))}</text>`;
      hits += `<rect class="ch-hit" data-i="${i}" x="${padL + i * slot}" y="${padT}" width="${slot}" height="${plotH}" tabindex="0" aria-label="${esc(bucketLabel(r.t, d.step, true))}: ${totals[i]} reports"/>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Reported positions per ${d.step < 86400 ? 'hour' : 'day'}">
      ${grid}<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" class="ch-base"/>${bars}${ticks}${hits}</svg>`;
  }

  function renderHistory() {
    const d = S.heat.key === heatKey() ? S.heat.data : null;
    const seg = (name, items, cur) => `<div class="seg" role="radiogroup" aria-label="${name}">${items.map(([k, l]) =>
      `<button role="radio" aria-checked="${k === cur}" class="${k === cur ? 'on' : ''}" data-${name}="${k}">${esc(l)}</button>`).join('')}</div>`;
    let html = `${seg('period', HEAT_PERIODS.map(([k, l]) => [k, 'Last ' + l]), S.heat.period)}
      ${seg('kind', HEAT_KINDS, S.heat.kind)}
      <div class="setting"><span>Show heatmap on the map</span><button class="btn ${S.heat.on ? 'btn-accent' : ''}" id="heatToggle" aria-pressed="${S.heat.on}">${S.heat.on ? 'On' : 'Off'}</button></div>`;
    if (!d) {
      $('#tab-history').innerHTML = html + `<div class="empty">Loading history…</div>`;
      bindHistory(); return;
    }
    const series = seriesFor(d);
    const sum = key => d.series.reduce((a, r) => a + valOf(r, key), 0);
    const period = HEAT_PERIODS.find(p => p[0] === d.period)?.[1];
    html += `<div class="tiles">
        <div class="tile"><b>${d.observations.toLocaleString()}</b><span>reported positions</span></div>
        <div class="tile"><b>${d.places.toLocaleString()}</b><span>places</span></div>
        <div class="tile"><b>${esc(d.by_oblast[0]?.name || '–')}</b><span>most reports</span></div></div>`;
    if (d.partial) {
      html += `<p class="note">${d.history_since ? `History only goes back to ${esc(new Date(d.history_since * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))}.` : 'No history recorded yet.'}
        Drone Map records history while it is running (and reads back the last ${S.state?.mode === 'demo' ? 'nights' : '24 hours'} on start), so the last ${esc(period)} fill in over time.</p>`;
    }
    if (!d.observations) {
      html += `<div class="empty"><b>Nothing recorded</b>No ${esc(HEAT_KIND_TEXT[d.kind])} with a known position in the last ${esc(period)}.</div>`;
    } else {
      const legend = series.length > 1 ? `<div class="ch-legend">${series.map(s => `<span><i style="background:${s.color}"></i>${svg(s.icon, null, 14)}${esc(s.label)} <b>${sum(s.key).toLocaleString()}</b></span>`).join('')}</div>` : '';
      html += `<div class="section-title">Reports per ${d.step < 86400 ? 'hour' : 'day'}</div>
        <div class="chart-wrap">${legend}${chartSvg(d, series)}<div class="ch-tip" hidden></div></div>
        <button class="linkbtn" id="tableToggle" aria-expanded="${S.heat.table}">${S.heat.table ? 'Hide table' : 'Show as table'}</button>
        ${S.heat.table ? `<table class="dtable"><thead><tr><th>${d.step < 86400 ? 'Hour' : 'Day'}</th>${series.map(s => `<th>${esc(s.label)}</th>`).join('')}</tr></thead><tbody>
          ${d.series.slice().reverse().map(r => `<tr><td>${esc(bucketLabel(r.t, d.step, true))}</td>${series.map(s => `<td>${valOf(r, s.key)}</td>`).join('')}</tr>`).join('')}</tbody></table>` : ''}
        <div class="section-title">By type</div>
        <div class="bars">${d.by_threat.map(b => bar(svg(b.threat, null, 18) + esc(info(b.threat).label), b.n, d.by_threat[0].n)).join('') || '<div class="empty" style="padding:8px">–</div>'}</div>
        <div class="section-title">Regions with most reports</div>
        <div class="bars">${d.by_oblast.map(o => bar(esc(o.name), o.n, d.by_oblast[0].n)).join('')}</div>
        <div class="section-title">Places</div>
        <div class="bars">${d.top_places.map(p => bar(`${esc(p.place)} <span class="muted">${esc(p.oblast)}</span>`, p.n, d.top_places[0].n, `data-fly="${p.lat},${p.lon}"`)).join('')}</div>`;
    }
    html += `<p class="note">Each report of a drone or missile at a named town or village adds heat there. Region-wide reports
      ("drones over Sumy region") are left out, so the middle of every region does not light up. Only reports confirmed by an
      official, reconnaissance or regional channel count.</p>`;
    $('#tab-history').innerHTML = html;
    bindHistory(d, series);
  }

  function bar(label, n, max, attrs = '') {
    return `<div class="hbar" ${attrs} ${attrs ? 'tabindex="0" role="button"' : ''}><span class="hb-l">${label}</span><span class="hb-n">${n.toLocaleString()}</span>
      <span class="hb-t"><i style="width:${Math.max(2, Math.round(n / max * 100))}%"></i></span></div>`;
  }

  function bindHistory(d, series) {
    const root = $('#tab-history');
    root.querySelectorAll('[data-period]').forEach(b => b.onclick = () => setHeat({ period: b.dataset.period }));
    root.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => setHeat({ kind: b.dataset.kind }));
    $('#heatToggle').onclick = () => setHeat({ on: !S.heat.on });
    const tt = $('#tableToggle');
    if (tt) tt.onclick = () => { S.heat.table = !S.heat.table; renderHistory(); };
    root.querySelectorAll('[data-fly]').forEach(el => {
      const go = () => {
        const [la, lo] = el.dataset.fly.split(',').map(Number);
        if (!S.heat.on) setHeat({ on: true });
        map.flyTo([la, lo], Math.max(map.getZoom(), 9), { duration: 0.6 }); collapseSheet();
      };
      el.onclick = go; el.onkeydown = e => { if (e.key === 'Enter') go(); };
    });
    const tip = root.querySelector('.ch-tip');
    if (!d || !tip) return;
    const show = el => {
      const r = d.series[+el.dataset.i];
      const total = series.reduce((a, s) => a + valOf(r, s.key), 0);
      tip.innerHTML = `<b>${esc(bucketLabel(r.t, d.step, true))}</b>` + (series.length > 1
        ? series.map(s => `<div><i style="background:${s.color}"></i>${esc(s.label)}<span>${valOf(r, s.key)}</span></div>`).join('') + `<div class="tot">Total<span>${total}</span></div>`
        : `<div class="tot">${esc(series[0].label)}<span>${total}</span></div>`);
      tip.hidden = false;
      const wrap = root.querySelector('.chart-wrap').getBoundingClientRect(), b = el.getBoundingClientRect();
      const x = Math.min(wrap.width - tip.offsetWidth - 2, Math.max(2, b.left - wrap.left + b.width / 2 - tip.offsetWidth / 2));
      tip.style.left = x + 'px';
      root.querySelectorAll('.ch-hit.hover').forEach(h => h.classList.remove('hover'));
      el.classList.add('hover');
    };
    const hide = () => { tip.hidden = true; root.querySelectorAll('.ch-hit.hover').forEach(h => h.classList.remove('hover')); };
    root.querySelectorAll('.ch-hit').forEach(el => {
      el.addEventListener('mouseenter', () => show(el)); el.addEventListener('focus', () => show(el));
      el.addEventListener('mouseleave', hide); el.addEventListener('blur', hide);
      el.addEventListener('click', () => show(el));
    });
  }

  // ------------------------------------------------------------------ panel: sources
  async function loadSources() {
    try {
      const r = await fetch('/api/sources', { cache: 'no-store' });
      if (r.ok) S.sources = await r.json();
    } catch { /* offline */ }
    if (S.tab === 'sources' && !S.selected) renderSources();
    updateStatus();
  }
  function renderSources() {
    if (!S.sources) { $('#tab-sources').innerHTML = '<div class="empty">Loading…</div>'; return; }
    const all = S.sources.groups.flatMap(g => g.channels);
    const n = st => all.filter(c => c.state === st).length;
    const head = `<div class="setting" style="font-size:12.5px"><span><b>${all.length}</b> channels</span>
      <span style="display:flex;gap:10px;color:var(--muted)"><span><i class="sdot ok" style="display:inline-block"></i> ${n('ok')} ok</span>
      <span><i class="sdot error" style="display:inline-block"></i> ${n('error')} error</span>
      <span><i class="sdot no_preview" style="display:inline-block"></i> ${n('no_preview')} no preview</span>
      <span><i class="sdot" style="display:inline-block"></i> ${n('pending')} pending</span></span></div>`;
    const groups = S.sources.groups.map(g => `<div class="src-group"><h3><i class="tier-dot tier-${g.tier}"></i>${esc(g.label)} <span class="cnt">${g.channels.length}</span></h3>
      <p>${esc(g.description)}</p><div class="src-list">${g.channels.map(c => {
        const st = c.state === 'ok' ? (c.last_post_ts ? `post ${ago(c.last_post_ts)}` : 'ok') : c.state === 'no_preview' ? 'no web preview' : c.state === 'error' ? 'error' : 'waiting';
        const title = c.error ? ` title="${esc(c.error)}"` : '';
        return `<div class="src"${title}><i class="sdot ${c.state}"></i><div><div class="nm">${c.name ? `${esc(c.name)}<code>@${esc(c.handle)}</code>` : '@' + esc(c.handle)}</div>
          <div class="ar">${esc(c.area || '')}</div></div><div class="st">${esc(st)}${c.via && c.via !== 'web' ? `<br>${esc(c.via)}` : ''}</div></div>`;
      }).join('')}</div></div>`).join('');
    $('#tab-sources').innerHTML = head + groups;
  }

  // ------------------------------------------------------------------ tabs & selection
  function showTab(tab) {
    S.tab = tab;
    $$('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === tab && !S.selected));
    for (const id of ['targets', 'feed', 'history', 'alerts', 'sources']) $(`#tab-${id}`).hidden = !!S.selected || id !== tab;
    if (tab === 'history') loadHeat();
    $('#detail').hidden = !S.selected;
    renderPanel();
  }
  $$('.tabs button').forEach(b => b.addEventListener('click', () => { S.selected = null; showTab(b.dataset.tab); renderMap(); expandSheet(); }));

  function renderPanel() {
    if (S.selected) return renderDetail();
    if (S.tab === 'targets') renderTargets();
    else if (S.tab === 'feed') renderFeed();
    else if (S.tab === 'history') renderHistory();
    else if (S.tab === 'alerts') renderAlertsTab();
    else if (S.tab === 'sources') renderSources();
  }

  function select(id, fly = true) {
    if (id !== S.selected) S.follow = null;
    S.selected = id;
    showTab(S.tab);
    renderMap();
    if (id) {
      const t = S.state.tracks.find(x => x.id === id);
      if (t && fly) {
        const pts = t.points.map(p => [p.lat, p.lon]);
        if (t.dest) pts.push([t.dest.lat, t.dest.lon]);
        if (pts.length > 1) map.flyToBounds(pts, { padding: [70, 70], maxZoom: 9, duration: 0.6 });
        else map.flyTo([t.lat, t.lon], Math.max(map.getZoom(), 8), { duration: 0.6 });
      }
      $('#detail').scrollTop = 0;
      expandSheet();
    }
  }
  $('#tab-targets').addEventListener('click', e => { const r = e.target.closest('[data-track]'); if (r) select(r.dataset.track, true); });
  $('#tab-targets').addEventListener('keydown', e => { if (e.key === 'Enter') { const r = e.target.closest('[data-track]'); if (r) select(r.dataset.track, true); } });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.selected) select(null); });

  // ------------------------------------------------------------------ near me
  function locate() {
    if (!navigator.geolocation) return toast('Geolocation is not available in this browser');
    navigator.geolocation.getCurrentPosition(pos => {
      setMe(pos.coords.latitude, pos.coords.longitude);
      map.flyTo([S.me.lat, S.me.lon], 8, { duration: 0.6 });
      setNear(true);
    }, () => toast('Location permission denied. Use “Pick on map” instead.'), { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  }
  function setMe(lat, lon) {
    S.me = { lat, lon }; prefs.set('me', S.me); drawMe(); checkNear();
    if (S.tab === 'alerts' && !S.selected) renderAlertsTab();
  }
  function setNear(on) {
    S.nearOn = on; prefs.set('nearOn', on);
    $('#nearMe').classList.toggle('on', on);
    if (on && 'Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
    drawMe(); checkNear();
    if (S.tab === 'alerts' && !S.selected) renderAlertsTab();
  }
  map.on('click', e => { if (S.pickingMe) { S.pickingMe = false; setMe(e.latlng.lat, e.latlng.lng); setNear(true); toast('Location set'); } });
  $('#nearMe').addEventListener('click', () => {
    if (!S.me) return locate();
    if (S.nearOn) { setNear(false); toast('Near-me warnings off'); } else { setNear(true); map.flyTo([S.me.lat, S.me.lon], 8, { duration: 0.6 }); toast(`Warning when a target is within ${S.radius} km`); }
  });

  function checkNear() {
    const box = $('#nearAlert');
    if (!S.nearOn || !S.me || !S.state) { box.hidden = true; return; }
    const hits = [];
    for (const t of S.state.tracks) {
      if (t.status !== 'active' || !t.confirmed || t.precision === 'region') continue;
      const d = distKm(S.me, t);
      let why = null;
      if (t.precision !== 'inbound' && d <= S.radius) why = `${Math.round(d)} km from you`;
      else if (t.dest && distKm(S.me, t.dest) <= S.radius) why = `heading to ${t.dest.name}`;
      else if (t.heading != null && t.precision !== 'inbound') {
        const ahead = lookahead(t);
        for (let k = 5; k <= ahead; k += 5) {
          const [la, lo] = project(t.lat, t.lon, t.heading, k);
          if (distKm(S.me, { lat: la, lon: lo }) <= S.radius) { why = `on course toward you`; break; }
        }
      }
      if (why) hits.push({ t, why, d });
    }
    if (!hits.length) { box.hidden = true; return; }
    hits.sort((a, b) => a.d - b.d);
    const h = hits[0];
    box.hidden = false;
    box.textContent = `⚠ ${tLabel(h.t)} ${h.why}${hits.length > 1 ? ` (+${hits.length - 1} more)` : ''}`;
    box.onclick = () => select(h.t.id, true);
    for (const x of hits) {
      if (S.notified.has(x.t.id)) continue;
      S.notified.add(x.t.id);
      navigator.vibrate?.([200, 100, 200]);
      if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        try { new Notification('Drone Map', { body: `${info(x.t.threat).label}: ${x.why}`, icon: 'icons/icon-192.png', tag: x.t.id }); } catch { /* ignore */ }
      }
    }
  }

  // ------------------------------------------------------------------ map controls, mobile sheet, install
  $('#zoomIn').onclick = () => map.zoomIn();
  $('#zoomOut').onclick = () => map.zoomOut();
  $('#fitAll').onclick = () => {
    const pts = visible().filter(t => t.status === 'active').flatMap(t => [[t.lat, t.lon]]);
    if (pts.length) map.flyToBounds(pts, { padding: [80, 80], maxZoom: 9, duration: 0.6 });
    else map.flyTo([48.7, 31.4], 6, { duration: 0.6 });
  };
  const panel = $('#panel');
  const isMobile = () => window.matchMedia('(max-width: 820px)').matches;
  function collapseSheet() { if (isMobile()) { panel.classList.add('collapsed'); panel.classList.remove('expanded'); } }
  function expandSheet() { if (isMobile() && panel.classList.contains('collapsed')) panel.classList.remove('collapsed'); }
  $('#sheetHandle').addEventListener('click', () => {
    if (panel.classList.contains('collapsed')) panel.classList.remove('collapsed');
    else if (panel.classList.contains('expanded')) { panel.classList.remove('expanded'); panel.classList.add('collapsed'); }
    else panel.classList.add('expanded');
  });
  $('#panelToggle').addEventListener('click', () => panel.classList.toggle('collapsed'));

  let deferredInstall = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; $('#installBtn').hidden = false; });
  $('#installBtn').addEventListener('click', async () => {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    await deferredInstall.userChoice.catch(() => {});
    deferredInstall = null; $('#installBtn').hidden = true;
  });
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});

  let toastTimer = null;
  function toast(msg) {
    const el = $('#toast'); el.textContent = msg; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
  }

  // ------------------------------------------------------------------ data loop
  function renderAll(mapToo) {
    if (S.selected && !(S.state?.tracks || []).some(t => t.id === S.selected)) S.selected = null;
    renderSummary(); renderFilters(); renderBanners();
    if (S.selected || S.tab !== 'history') renderPanel();      // the heatmap tab refreshes on its own
    if (mapToo) renderMap();
    $('#tabCountTargets').textContent = visible().filter(t => t.status === 'active').length || '';
    $('#tabCountAlerts').textContent = (S.state?.alerts || []).length || '';
    checkNear(); updateStatus();
  }

  async function poll() {
    let changed = false;
    try {
      const r = await fetch('/api/state', { headers: S.etag ? { 'If-None-Match': S.etag } : {}, cache: 'no-store' });
      if (r.status === 200) {
        S.etag = r.headers.get('ETag');
        S.state = await r.json();
        changed = true;
      } else if (r.status !== 304) throw new Error(r.status);
      S.offline = false; S.lastFetchOk = Date.now();
    } catch {
      S.offline = true;
    }
    if (S.state) renderAll(changed);
    else updateStatus();
    setTimeout(poll, document.hidden ? 15000 : 4000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { S.etag = null; } });

  $('#nearMe').classList.toggle('on', S.nearOn);
  map.on('dragstart', () => { if (S.follow) { S.follow = null; if (S.selected) renderDetail(); toast('Stopped following'); } });
  drawMe();
  if (S.heat.on) loadHeat();
  setInterval(() => { if (S.heat.on || (S.tab === 'history' && !S.selected)) loadHeat(); }, 60000);
  poll();
  loadSources();
  setInterval(loadSources, 20000);
})();
