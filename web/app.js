(() => {
  'use strict';
  const { THREATS, svg, mapSvg, tint, explosion, kill } = window.DMIcons;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // per-viewer preferences (best effort: storage may be unavailable)
  const prefs = {
    get(k, d) { try { const v = localStorage.getItem('dm.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('dm.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
  };

  const FAMILY_ORDER = ['kinzhal', 'ballistic', 'cruise', 'missile', 'kab', 'jet_shahed', 'shahed', 'uav', 'gerbera', 'recon', 'lancet', 'molniya', 'fpv'];
  const TIER_LABEL = { official: 'Official', recon: 'Recon', regional: 'Regional', aggregator: 'Aggregator', russia: 'Russia-side' };

  const S = {
    state: null, sources: null, etag: null, lastFetchOk: 0, offline: false,
    selected: null, tab: 'targets',
    hidden: new Set(prefs.get('hidden', [])),
    showUnconfirmed: prefs.get('showUnconfirmed', true),
    showAlerts: prefs.get('alertsOn', true),
    showOccupied: prefs.get('showOccupied', true),
    showRussia: prefs.get('showRussia', true),
    showDetail: prefs.get('showDetail', false),
    me: prefs.get('me', null), radius: prefs.get('radius', 25), nearOn: prefs.get('nearOn', false),
    pickingMe: false, notified: new Set(), dismissed: new Set(prefs.get('dismissed', [])),
  };

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
  map.attributionControl.addAttribution('Districts &copy; OCHA · Occupied &copy; DeepState · &copy; OpenStreetMap');
  DMBase.init(map).then(() => {
    DMBase.setOptions({ showAlerts: S.showAlerts, showOccupied: S.showOccupied, showRussia: S.showRussia });
    if (S.showDetail) DMBase.setDetail(true);
    if (S.state) renderMap();
  }).catch(err => {
    // never leave a blank map: fall back to the street map and say why
    console.error('base map', err);
    DMBase.setDetail(true);
    S.baseMapFailed = true;
    toast('The district map could not load, showing the street map instead. Try restarting with start.bat.');
  });

  const layers = {
    areas: L.layerGroup().addTo(map),
    tracks: L.layerGroup().addTo(map),
    events: L.layerGroup().addTo(map),
    markers: L.layerGroup().addTo(map),
    me: L.layerGroup().addTo(map),
  };

  const visible = () => (S.state?.tracks || []).filter(t => !S.hidden.has(t.threat) && (S.showUnconfirmed || t.confirmed));

  // ---------------------------------------------------------------- predicted movement
  // Between reports a target keeps flying: its icon advances along the reported destination or
  // heading at its observed (or typical) speed. A new report re-anchors it.
  const PREDICT_MIN = { shahed: 25, uav: 25, gerbera: 25, jet_shahed: 12, cruise: 10, missile: 8 };
  const SPEED_RANGE = { shahed: [120, 220], uav: [120, 220], gerbera: [100, 200], jet_shahed: [300, 550], cruise: [550, 900], missile: [550, 900] };
  function bearing(a, b) {
    const p1 = toRad(a.lat), p2 = toRad(b.lat), dl = toRad(b.lon - a.lon);
    const x = Math.sin(dl) * Math.cos(p2), y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
    return (toDeg(Math.atan2(x, y)) + 360) % 360;
  }
  function predicted(t, at = now()) {
    const still = { lat: t.lat, lon: t.lon, est: false, brg: t.heading };
    const maxMin = PREDICT_MIN[t.threat];
    if (!maxMin || t.status !== 'active' || ['inbound', 'origin'].includes(t.precision)) return still;
    const dtMin = Math.min(maxMin, (at - t.last_seen) / 60);
    if (dtMin <= 0.2) return still;
    const [lo, hi] = SPEED_RANGE[t.threat];
    const speed = Math.max(lo, Math.min(hi, t.speed_kmh || t.nominal_speed_kmh || lo));
    let km = speed * dtMin / 60, brg = t.heading;
    if (t.dest) {
      const left = distKm(t, t.dest) - 3;
      if (left <= 1) return still;
      brg = bearing(t, t.dest);
      km = Math.min(km, left);
    }
    if (brg == null) return still;
    if (t.precision === 'region') km = Math.min(km, 25);          // coarse position: do not run far with it
    const [lat, lon] = project(t.lat, t.lon, brg, km);
    return { lat, lon, est: true, brg, km, mins: dtMin };
  }

  function zFor(t) {
    let z = 100 - FAMILY_ORDER.indexOf(t.threat) * 5;
    if (t.status !== 'active') z -= 200;
    if (S.selected === t.id) z += 1000;
    return z;
  }

  function tipHtml(t) {
    const p = predicted(t);
    const where = t.precision === 'inbound' ? `heading to ${esc(t.place)}` : esc(t.place) + (t.precision === 'approx' ? ' <span style="color:var(--muted)">(est.)</span>' : '');
    const dest = t.dest && t.precision !== 'inbound' && t.precision !== 'approx' ? ` → ${esc(t.dest.name)}` : '';
    const unc = t.confirmed ? '' : ' · <b style="color:var(--warn)">unconfirmed</b>';
    const est = p.est ? `<br><span style="color:var(--muted)">estimated ~${Math.round(p.km)} km further since the last report</span>` : '';
    return `<b>${esc(tLabel(t))}</b> · ${where}${dest}${est}<br><span style="color:var(--muted)">last report ${ago(t.last_seen)} · ${Math.round(t.confidence * 100)}% confidence${unc}</span>`;
  }

  // Targets are drawn as icons only: where each one is now (estimated between reports), pointing
  // and moving in its direction of travel. When a new report arrives the icon glides to the
  // corrected position instead of jumping.
  const drawn = new Map();       // track id -> { t, marker, iconKey, pos, glide, rot }
  const GLIDE_MS = 1600;

  function iconFor(t) {
    const sel = S.selected === t.id;
    const hot = ['ballistic', 'kinzhal'].includes(t.threat) && t.status === 'active';
    const cls = ['mk', t.status, t.confirmed ? '' : 'unconf', sel ? 'sel' : '', t.precision === 'inbound' ? 'inbound' : '',
      ['region', 'approx'].includes(t.precision) ? 'approx' : '', hot ? 'hot' : ''].join(' ');
    const badge = t.count > 1 ? `<span class="mk-n">${t.count}</span>` : '';
    const size = info(t.threat).family === 'drone' ? 30 : 32;          // drones a touch smaller: "mini drones"
    return { key: [cls, t.threat, t.count].join('|'), icon: L.divIcon({
      className: '', iconSize: [34, 34], iconAnchor: [17, 17],
      html: `<div class="${cls}" style="--c:${info(t.threat).color}"><div class="mk-rot">${mapSvg(t.threat, size)}</div>${badge}</div>`,
    }) };
  }

  function upsertTrack(t) {
    let d = drawn.get(t.id);
    if (!d) {
      d = { marker: null, iconKey: '', pos: null, glide: null, rot: null };
      d.marker = L.marker([t.lat, t.lon], { riseOnHover: true, keyboard: true })
        .bindTooltip(() => tipHtml(d.t), { className: 'dm-tip', direction: 'top', offset: [0, -17] })
        .on('click', () => select(d.t.id, false))
        .addTo(layers.markers);
      drawn.set(t.id, d);
    } else if (d.pos && (d.t.last_seen !== t.last_seen || d.t.lat !== t.lat || d.t.lon !== t.lon)) {
      d.glide = { from: d.pos, start: performance.now() };            // new report: glide to it
    }
    d.t = t;
    const { key, icon } = iconFor(t);
    if (key !== d.iconKey) { d.marker.setIcon(icon); d.iconKey = key; d.rot = null; }
    d.marker.setZIndexOffset(zFor(t));
    placeTrack(d, performance.now());
  }

  function placeTrack(d, nowMs) {
    const t = d.t;
    const p = predicted(t);
    let lat = p.lat, lon = p.lon;
    if (d.glide) {
      const k = Math.min(1, (nowMs - d.glide.start) / GLIDE_MS);
      const e = k < 0.5 ? 2 * k * k : 1 - (2 - 2 * k) ** 2 / 2;      // ease in-out
      lat = d.glide.from[0] + (lat - d.glide.from[0]) * e;
      lon = d.glide.from[1] + (lon - d.glide.from[1]) * e;
      if (k >= 1) d.glide = null;
    }
    d.pos = [lat, lon];
    d.marker.setLatLng(d.pos);
    const rot = t.precision === 'inbound' ? 0 : (p.brg ?? t.heading ?? 0);
    if (d.rot === null || Math.abs(rot - d.rot) > 0.5) {
      const el = d.marker.getElement()?.querySelector('.mk-rot');
      if (el) { el.style.transform = `rotate(${rot}deg)`; d.rot = rot; }
    }
  }

  // the map shows live targets only; ended ones stay in the list
  const mapTracks = () => visible().filter(t => t.status !== 'ended');

  function renderTracks() {
    const vis = mapTracks();
    const ids = new Set(vis.map(t => t.id));
    for (const [id, d] of drawn) {
      if (!ids.has(id)) { layers.markers.removeLayer(d.marker); drawn.delete(id); }
    }
    for (const t of vis.slice().reverse()) upsertTrack(t);
  }

  let lastFrame = 0;
  function frame(ts) {
    if (!document.hidden && ts - lastFrame > 80) {                    // ~12 updates a second is smooth enough
      lastFrame = ts;
      for (const d of drawn.values()) placeTrack(d, ts);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  function drawEvent(e) {
    if (e.threat && S.hidden.has(e.threat)) return;
    if (!S.showUnconfirmed && !e.confirmed) return;
    const age = now() - e.last_ts;
    if (e.kind === 'explosion') {
      const icon = L.divIcon({ className: '', html: `<div class="ex ${age > 900 ? 'old' : ''}">${explosion(24)}</div>`, iconSize: [24, 24], iconAnchor: [12, 12] });
      L.marker([e.lat, e.lon], { icon, zIndexOffset: 500 })
        .bindTooltip(`<b>Explosions</b> · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)} · ${e.sources.length} source(s)</span>`, { className: 'dm-tip', direction: 'top' })
        .addTo(layers.events);
    } else if (e.kind === 'kill') {
      const icon = L.divIcon({ className: '', html: `<div class="kill-mk">${kill(16)}</div>`, iconSize: [16, 16], iconAnchor: [8, 8] });
      L.marker([e.lat, e.lon], { icon, zIndexOffset: -50 })
        .bindTooltip(`<b>Shot down</b>${e.threat ? ' · ' + esc(info(e.threat).short) : ''} · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)}</span>`, { className: 'dm-tip', direction: 'top' })
        .addTo(layers.events);
    } else if (e.kind === 'threat' && e.threat) {
      const c = info(e.threat).color;
      L.circle([e.lat, e.lon], { radius: e.precision === 'region' ? 60000 : 16000, color: c, weight: 1.6, dashArray: '5 6', fillColor: c, fillOpacity: 0.08, className: 'threat-area' })
        .bindTooltip(`<b>${esc(info(e.threat).label)} threat</b> · ${esc(e.place)}<br><span style="color:var(--muted)">${ago(e.ts)}</span>`, { className: 'dm-tip', sticky: true })
        .addTo(layers.areas);
    }
  }

  function drawMe() {
    layers.me.clearLayers();
    if (!S.me) return;
    L.circle([S.me.lat, S.me.lon], { radius: S.radius * 1000, color: '#4cc2ff', weight: 1.5, opacity: S.nearOn ? 0.8 : 0.35, fillOpacity: 0.05, dashArray: '4 6', interactive: false }).addTo(layers.me);
    L.marker([S.me.lat, S.me.lon], { icon: L.divIcon({ className: '', html: '<div class="me-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }), interactive: false, zIndexOffset: 2000 }).addTo(layers.me);
  }

  function renderMap() {
    layers.events.clearLayers(); layers.areas.clearLayers();
    if (!S.state) return;
    for (const e of S.state.events) drawEvent(e);
    renderTracks();
    DMBase.setAlerts(S.state.alerts);
    DMBase.setRuZones(S.state.ru_zones);
    drawMe();
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
    const up = S.state?.app;
    if (up?.available && !S.dismissed.has('update:' + up.latest)) {
      list.unshift({ key: 'update:' + up.latest, kind: 'update', ts: now(), channel: 'drone-map',
        text: `A newer version (${up.latest}) is available. Close this window's terminal and double-click start.bat (or run: git pull).` });
    }
    list.splice(2);                                           // never more than two strips over the map
    requestAnimationFrame(() => document.documentElement.style.setProperty('--banner-h', $('#banners').offsetHeight + 'px'));
    $('#banners').innerHTML = list.map(b => {
      const kind = b.kind === 'update' ? 'Update' : b.kind === 'aviation' ? 'Aviation' : (b.kind.startsWith('threat:') ? info(b.kind.slice(7)).short + ' threat' : 'Notice');
      return `<div class="banner ${b.kind === 'aviation' ? 'aviation' : b.kind === 'update' ? 'update' : ''}"><span class="b-kind">${esc(kind)}</span>
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

  // ------------------------------------------------------------------ on-map legend
  S.legendHidden = prefs.get('legendHidden', window.matchMedia('(max-width: 820px)').matches);
  function renderLegend() {
    const el = $('#legend');
    if (!el) return;
    const shown = mapTracks();
    const items = FAMILY_ORDER.filter(k => shown.some(t => t.threat === k))
      .map(k => `<div class="lg-i">${mapSvg(k, 18)}<span>${esc(info(k).short)}</span></div>`);
    const sw = (c, l) => `<div class="lg-i"><i class="swatch" style="background:${c}"></i><span>${l}</span></div>`;
    if (S.showAlerts) items.push(sw('#a52f30', 'Red alert'), sw('#c2981f', 'Yellow alert'));
    if (S.showOccupied) items.push(sw('#4f2027', 'Occupied'));
    if (S.showRussia && (S.state?.ru_zones || []).length) items.push(sw('#1fb5cc', 'Danger in Russia'));
    el.innerHTML = `<button class="lg-toggle" aria-expanded="${!S.legendHidden}">Legend ${S.legendHidden ? '▴' : '▾'}</button>` +
      (S.legendHidden ? '' : `<div class="lg-body">${items.join('') || '<span class="hint">No targets on the map</span>'}</div>`);
  }
  $('#legend').addEventListener('click', e => {
    if (!e.target.closest('.lg-toggle')) return;
    S.legendHidden = !S.legendHidden; prefs.set('legendHidden', S.legendHidden); renderLegend();
  });

  // ------------------------------------------------------------------ filters
  function renderFilters() {
    const counts = {};
    for (const t of S.state?.tracks || []) if (t.status !== 'ended') counts[t.threat] = (counts[t.threat] || 0) + 1;
    const present = FAMILY_ORDER.filter(k => counts[k] || S.hidden.has(k));
    const chips = present.map(k => `<button class="chip ${S.hidden.has(k) ? 'off' : ''}" data-type="${k}" title="${esc(info(k).label)}" aria-pressed="${!S.hidden.has(k)}">
      ${svg(k, null, 16)}${esc(info(k).short)} <span class="n">${counts[k] || 0}</span></button>`);
    const opt = (key, label, title) => `<button class="chip opt ${S[key] ? 'on' : ''}" data-opt="${key}" title="${title}">${label}</button>`;
    chips.push(opt('showUnconfirmed', 'Unconfirmed', 'Show reports that only aggregators have made'));
    chips.push(opt('showAlerts', 'Alerts', 'Shade districts under air-raid alert (red / yellow level)'));
    chips.push(opt('showOccupied', 'Occupied', 'Occupied territory (DeepState)'));
    const ru = (S.state?.ru_zones || []).length;
    chips.push(opt('showRussia', `Russia${ru ? ' <span class="n">' + ru + '</span>' : ''}`, 'Drone and missile danger over Russia and occupied areas, from Russian-side channels'));
    chips.push(opt('showDetail', 'Detail', 'Street map underneath, for finding villages'));
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
      const k = b.dataset.opt;
      S[k] = !S[k];
      prefs.set(k === 'showAlerts' ? 'alertsOn' : k, S[k]);
      if (k === 'showDetail') DMBase.setDetail(S.showDetail);
      else DMBase.setOptions({ showAlerts: S.showAlerts, showOccupied: S.showOccupied, showRussia: S.showRussia });
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
    const path = t.points.filter(p => p.precision !== 'inbound').map(p => `<li style="--c:${c}">${esc(p.place)}${p.precision === 'region' ? ' <span class="tag">region</span>' : p.precision === 'origin' ? ' <span class="tag">launch area</span>' : p.precision === 'approx' ? ' <span class="tag">estimated</span>' : ''}<span class="tm">${clock(p.ts)}</span></li>`).join('');
    const destLi = t.dest ? `<li class="dest" style="--c:${c}">→ ${esc(t.dest.name)} <span class="tm">reported destination</span></li>` : '';
    const msgs = t.messages.map(m => {
      const link = S.state.mode === 'demo' ? `@${esc(m.channel)}` : `<a href="https://t.me/${encodeURIComponent(m.channel)}/${m.id}" target="_blank" rel="noopener">@${esc(m.channel)}</a>`;
      return `<div class="msg"><div class="mh">${link}<span>${clock(m.ts)}</span></div><div class="mt">${esc(m.text)}</div></div>`;
    }).join('');
    $('#detail').innerHTML = `
      <div class="detail-head"><button class="back" id="backBtn">← Back</button></div>
      <div class="detail-title"><div class="ic">${svg(t.threat, null, 40)}</div>
        <div><h2>${esc(info(t.threat).label)}${t.count > 1 ? ` ×${t.count}` : ''}</h2>
        <div class="sub">${esc(statusTxt)} · last report ${ago(t.last_seen)}</div></div></div>
      <dl class="kv">
        <dt>Position</dt><dd>${esc(t.precision === 'inbound' ? 'not yet seen, reported heading to ' + t.place : t.place)}${t.precision === 'approx' ? '<br><span style="color:var(--muted);font-size:12px">estimated: the report gave where it is heading, not where it is</span>' : ''}</dd>
        <dt>Heading</dt><dd>${t.dest ? '→ ' + esc(t.dest.name) : ''}${t.heading != null ? ` (${compass(t.heading)}, ${Math.round(t.heading)}°)` : (t.dest ? '' : 'unknown')}</dd>
        <dt>Speed</dt><dd>${t.speed_kmh ? `~${t.speed_kmh} km/h observed` : `typical ${t.nominal_speed_kmh} km/h`}</dd>
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
  function alertGroups(alerts) {
    const by = {};
    for (const a of alerts) (by[a.oblast] = by[a.oblast] || []).push(a);
    const oblastName = k => (DMBase.data?.oblasts.features.find(f => f.properties.key === k)?.properties.name) || k;
    return Object.entries(by).sort((x, y) => oblastName(x[0]).localeCompare(oblastName(y[0]))).map(([ob, list]) => {
      const whole = list.find(a => a.kind === 'oblast');
      const parts = list.filter(a => a.kind === 'raion');
      const lvl = a => `<i class="lvl lvl-${a.level}" title="${a.level} level"></i>`;
      const items = whole ? `${lvl(whole)} whole region` : parts.map(a => `${lvl(a)}${esc(a.name.replace(' raion', ''))}`).join(' · ');
      const since = Math.min(...list.map(a => a.since));
      return `<div class="alert-row"><span class="an"><b>${esc(oblastName(ob))}</b><br><span class="alert-parts">${items}</span></span><span class="at">since ${clock(since)}</span></div>`;
    }).join('');
  }

  function renderAlertsTab() {
    const alerts = S.state?.alerts || [];
    const banners = S.state?.banners || [];
    const ruZones = S.state?.ru_zones || [];
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
      ${alerts.length ? alertGroups(alerts) : '<div class="empty" style="padding:14px">No active air-raid alerts reported.</div>'}
      ${ruZones.length ? `<div class="section-title">Danger over Russia / occupied · ${ruZones.length}</div>
        <p class="hint">From Russian-side channels: where Ukrainian drones or missiles are announced. Shown in cyan on the map.</p>` +
        ruZones.map(z => `<div class="alert-row"><span class="ad" style="background:#1fb5cc;box-shadow:0 0 0 3px rgba(31,181,204,.25)"></span>
          <span class="an">${esc(z.name)}</span><span class="at">${z.kind === 'missile' ? 'missiles' : 'drones'} · ${clock(z.since)}</span></div>`).join('') : ''}
      <div class="section-title">Legend</div><div class="legend">${legend}
        <div>${explosion(18)}Explosions reported</div><div>${kill(16)}Shot down</div>
        <div><i class="swatch" style="background:#a52f30"></i>Air alert, red level</div><div><i class="swatch" style="background:#c2981f"></i>Air alert, yellow level</div>
        <div><i class="swatch" style="background:#4f2027"></i>Occupied territory</div><div><i class="swatch" style="background:#1fb5cc"></i>Danger over Russia</div></div>
      <div class="section-title">How it works</div>
      <p class="hint">Each target merges reports from several channels. Official sources weigh most, then reconnaissance and regional observers.
      Aggregators only count when they agree with someone else; a target seen only by aggregators is shown faded with a “?”.
      Each icon sits where the target is now and points the way it is flying. Between reports it keeps moving along its reported
      course at its estimated speed, and glides to the real position when the next report arrives.</p>`;
    $('#radiusSel').onchange = e => { S.radius = +e.target.value; prefs.set('radius', S.radius); drawMe(); checkNear(); };
    $('#gpsBtn').onclick = locate;
    $('#pickBtn').onclick = () => { S.pickingMe = true; toast('Tap the map to set your location'); collapseSheet(); };
    $('#nearToggle').onclick = () => setNear(!S.nearOn);
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
    for (const id of ['targets', 'feed', 'alerts', 'sources']) $(`#tab-${id}`).hidden = !!S.selected || id !== tab;
    $('#detail').hidden = !S.selected;
    renderPanel();
  }
  $$('.tabs button').forEach(b => b.addEventListener('click', () => { S.selected = null; showTab(b.dataset.tab); renderMap(); expandSheet(); }));

  function renderPanel() {
    if (S.selected) return renderDetail();
    if (S.tab === 'targets') renderTargets();
    else if (S.tab === 'feed') renderFeed();
    else if (S.tab === 'alerts') renderAlertsTab();
    else if (S.tab === 'sources') renderSources();
  }

  function select(id, fly = true) {
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
      const pp = predicted(t);
      const d = distKm(S.me, pp);
      let why = null;
      if (t.precision !== 'inbound' && d <= S.radius) why = `${Math.round(d)} km from you`;
      else if (t.dest && distKm(S.me, t.dest) <= S.radius) why = `heading to ${t.dest.name}`;
      else if ((pp.brg ?? t.heading) != null && t.precision !== 'inbound') {
        const ahead = Math.min(150, (t.speed_kmh || t.nominal_speed_kmh) * 0.25);
        for (let k = 5; k <= ahead; k += 5) {
          const [la, lo] = project(pp.lat, pp.lon, pp.brg ?? t.heading, k);
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

  // ------------------------------------------------------------------ area snapshot (download a graphic)
  let snapRect = null, snapStart = null;
  function enterSnap() {
    if (!DMBase.data) return toast('Map data is still loading');
    S.snapping = true;
    document.body.classList.add('snap-mode');
    map.dragging.disable(); map.boxZoom.disable();
    $('#snapBtn').classList.add('on');
    toast('Drag a box over the area to capture. Tap once for the whole view. Esc cancels.');
  }
  function exitSnap() {
    S.snapping = false; snapStart = null;
    document.body.classList.remove('snap-mode');
    map.dragging.enable(); map.boxZoom.enable();
    $('#snapBtn').classList.remove('on');
    if (snapRect) { map.removeLayer(snapRect); snapRect = null; }
  }
  const mapEl = $('#map');
  mapEl.addEventListener('pointerdown', e => {
    if (!S.snapping) return;
    e.preventDefault(); e.stopPropagation();
    snapStart = { ll: map.mouseEventToLatLng(e), x: e.clientX, y: e.clientY };
    mapEl.setPointerCapture?.(e.pointerId);
  }, true);
  mapEl.addEventListener('pointermove', e => {
    if (!S.snapping || !snapStart) return;
    const b = L.latLngBounds(snapStart.ll, map.mouseEventToLatLng(e));
    if (!snapRect) snapRect = L.rectangle(b, { color: '#4cc2ff', weight: 2, dashArray: '6 5', fillOpacity: 0.08, interactive: false }).addTo(map);
    else snapRect.setBounds(b);
  }, true);
  mapEl.addEventListener('pointerup', e => {
    if (!S.snapping || !snapStart) return;
    const small = Math.hypot(e.clientX - snapStart.x, e.clientY - snapStart.y) < 12;
    const bounds = small ? map.getBounds() : L.latLngBounds(snapStart.ll, map.mouseEventToLatLng(e));
    exitSnap();
    openSnapshot(bounds);
  }, true);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (S.snapping) exitSnap(); else closeSnapshot(); } });
  $('#snapBtn').addEventListener('click', () => (S.snapping ? exitSnap() : enterSnap()));

  let snapBounds = null, snapUrl = null, snapTitle = '';
  function snapOptions() {
    return { bounds: snapBounds, state: S.state, base: DMBase, tracks: visible(), predicted,
      show: { alerts: S.showAlerts, occupied: S.showOccupied, russia: S.showRussia }, title: snapTitle };
  }
  async function openSnapshot(bounds) {
    snapBounds = bounds;
    snapTitle = `Air situation · ${DMSnapshot.areaName(bounds, DMBase)}`;
    const m = $('#snapModal');
    m.hidden = false;
    m.innerHTML = `<div class="modal-card" role="dialog" aria-label="Area snapshot">
      <div class="modal-head"><b>Area snapshot</b><button class="btn" id="snapClose">Close</button></div>
      <div class="snap-preview" id="snapPreview"><div class="empty">Rendering…</div></div>
      <div class="modal-actions">
        <input id="snapTitleIn" class="text-in" value="${esc(snapTitle)}" aria-label="Title">
        <button class="btn btn-accent" id="snapPng">Download PNG</button>
        <button class="btn" id="snapJson">Download data (GeoJSON)</button>
      </div></div>`;
    $('#snapClose').onclick = closeSnapshot;
    m.onclick = e => { if (e.target === m) closeSnapshot(); };
    let tmr = null;
    $('#snapTitleIn').oninput = e => { snapTitle = e.target.value; clearTimeout(tmr); tmr = setTimeout(drawSnapshot, 350); };
    $('#snapPng').onclick = () => { if (snapUrl) download(snapUrl, `drone-map-${stamp()}.png`); };
    $('#snapJson').onclick = () => {
      const blob = new Blob([JSON.stringify(DMSnapshot.geojson(snapBounds, S.state, visible(), predicted), null, 1)], { type: 'application/geo+json' });
      const url = URL.createObjectURL(blob);
      download(url, `drone-map-${stamp()}.geojson`);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    };
    drawSnapshot();
  }
  async function drawSnapshot() {
    try {
      const cv = await DMSnapshot.render(snapOptions());
      const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
      if (snapUrl) URL.revokeObjectURL(snapUrl);
      snapUrl = URL.createObjectURL(blob);
      const pv = $('#snapPreview');
      if (pv) pv.innerHTML = `<img src="${snapUrl}" alt="Snapshot of the selected area">`;
    } catch (err) {
      console.error(err);
      const pv = $('#snapPreview');
      if (pv) pv.innerHTML = '<div class="empty">Could not render the snapshot.</div>';
    }
  }
  function closeSnapshot() { $('#snapModal').hidden = true; }
  function stamp() { return new Date().toISOString().slice(0, 16).replace(/[-:T]/g, ''); }
  function download(url, name) {
    const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  }

  // ------------------------------------------------------------------ data loop
  function renderAll(mapToo) {
    if (S.selected && !(S.state?.tracks || []).some(t => t.id === S.selected)) S.selected = null;
    renderSummary(); renderFilters(); renderBanners(); renderPanel(); renderLegend();
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
  drawMe();
  async function loadOccupied() {
    try {
      const r = await fetch('/api/occupied');
      if (r.ok) DMBase.setOccupied(await r.json());
    } catch { /* offline: keep what we have */ }
  }
  poll();
  loadSources();
  loadOccupied();
  setInterval(loadOccupied, 30 * 60 * 1000);
  setInterval(loadSources, 20000);
})();
