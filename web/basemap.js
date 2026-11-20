/* Vector base map in the style of alert maps: districts shaded by alert level, oblast borders,
   occupied territory, danger zones over Russia, and labels. Data: data/admin.json, /api/occupied. */
window.DMBase = (() => {
  'use strict';
  const PAL = {
    sea: '#12161c', land: '#28303c', raionLine: '#1b212a', oblastLine: '#0e1217',
    russia: '#1d222a', russiaLine: '#2b323c', neighbor: '#1a1e25',
    yellow: '#c2981f', red: '#a52f30', occupied: '#4f2027', occupiedLine: '#7a2f39', ruDanger: '#1fb5cc',
    label: '#e7eaef', labelMuted: '#8e99aa', labelOcc: '#e6a3aa', labelRu: '#6f7a8a',
  };
  const CITIES = [
    ['Київ', 50.45, 30.523, 1], ['Харків', 49.994, 36.23, 1], ['Одеса', 46.482, 30.723, 1], ['Дніпро', 48.464, 35.046, 1],
    ['Львів', 49.842, 24.031, 1], ['Запоріжжя', 47.838, 35.139, 1], ['Миколаїв', 46.975, 31.995, 2], ['Херсон', 46.636, 32.617, 2],
    ['Суми', 50.907, 34.798, 2], ['Полтава', 49.589, 34.551, 2], ['Чернігів', 51.494, 31.289, 2], ['Черкаси', 49.444, 32.06, 2],
    ['Житомир', 50.254, 28.658, 2], ['Вінниця', 49.233, 28.468, 2], ['Хмельницький', 49.422, 26.987, 2], ['Рівне', 50.619, 26.251, 2],
    ['Луцьк', 50.747, 25.325, 2], ['Тернопіль', 49.553, 25.594, 2], ['Івано-Франківськ', 48.922, 24.711, 2], ['Ужгород', 48.621, 22.288, 2],
    ['Чернівці', 48.292, 25.936, 2], ['Кропивницький', 48.508, 32.262, 2], ['Кривий Ріг', 47.91, 33.392, 2], ['Кременчук', 49.066, 33.42, 3],
    ['Краматорськ', 48.723, 37.556, 2], ['Донецьк', 48.016, 37.803, 2], ['Луганськ', 48.574, 39.307, 2], ['Маріуполь', 47.097, 37.543, 3],
    ['Мелітополь', 46.849, 35.367, 3], ['Сімферополь', 44.952, 34.102, 2], ['Севастополь', 44.616, 33.525, 3],
    ['Бєлгород', 50.597, 36.588, 2], ['Курськ', 51.73, 36.193, 2], ['Брянськ', 53.243, 34.364, 2], ['Воронеж', 51.67, 39.2, 2],
    ['Ростов-на-Дону', 47.235, 39.7, 2], ['Краснодар', 45.04, 38.98, 3], ['Москва', 55.76, 37.62, 1], ['Мінськ', 53.9, 27.567, 2],
    ['Кишинів', 47.01, 28.86, 3],
  ];

  let map, data = null, raionIndex = {}, ruIndex = {}, oblastIndex = {};
  const layers = {};
  const state = { alerts: [], occupied: null, ruZones: [], showAlerts: true, showOccupied: true, showRussia: true, detail: false };
  let detailTiles = null;

  function pane(name, z, noEvents) {
    const p = map.createPane(name);
    p.style.zIndex = z;
    if (noEvents) p.style.pointerEvents = 'none';
  }

  function label(text, lat, lon, cls) {
    return L.marker([lat, lon], {
      pane: 'dm-labels', interactive: false, keyboard: false,
      icon: L.divIcon({ className: 'lbl ' + cls, html: `<span>${text}</span>`, iconSize: null }),
    });
  }

  function raionLabelText(p) {
    return /Київ|Севастополь|зона/.test(p.name) ? p.name : `${p.name} р-н`;
  }

  async function init(m) {
    map = m;
    pane('dm-base', 210);
    pane('dm-occ', 250, true);
    pane('dm-ru', 260);
    pane('dm-lines', 300, true);
    pane('dm-labels', 350, true);
    map.getContainer().style.background = PAL.sea;
    const r = await fetch('data/admin.json');
    data = await r.json();

    layers.neighbors = L.geoJSON(data.neighbors, { pane: 'dm-base', interactive: false,
      style: { fillColor: PAL.neighbor, fillOpacity: 1, color: PAL.russiaLine, weight: 1 } }).addTo(map);
    layers.russia = L.geoJSON(data.russia, { pane: 'dm-base',
      style: () => ({ fillColor: PAL.russia, fillOpacity: 1, color: PAL.russiaLine, weight: 1 }),
      onEachFeature: (f, l) => { ruIndex[f.properties.key] = l; },
    }).addTo(map);
    layers.raions = L.geoJSON(data.raions, { pane: 'dm-base',
      style: () => ({ fillColor: PAL.land, fillOpacity: 1, stroke: false }),
      onEachFeature: (f, l) => {
        raionIndex[f.properties.id] = l;
        l.bindTooltip(() => raionTip(f.properties, l), { className: 'dm-tip', sticky: true, direction: 'top', offset: [0, -6] });
      },
    }).addTo(map);
    layers.occupied = L.geoJSON(null, { pane: 'dm-occ', interactive: false,
      style: { fillColor: PAL.occupied, fillOpacity: 0.92, color: PAL.occupiedLine, weight: 0.8 } }).addTo(map);
    layers.ruZones = L.layerGroup().addTo(map);
    layers.raionLines = L.geoJSON(data.raions, { pane: 'dm-lines', interactive: false,
      style: { fill: false, color: PAL.raionLine, weight: 0.7, opacity: 0.9 } }).addTo(map);
    layers.oblastLines = L.geoJSON(data.oblasts, { pane: 'dm-lines', interactive: false,
      style: { fill: false, color: PAL.oblastLine, weight: 1.8, opacity: 1 },
      onEachFeature: (f, l) => { oblastIndex[f.properties.key] = l; } }).addTo(map);

    layers.oblastLabels = L.layerGroup(data.oblasts.features.filter(f => !['kyiv_city', 'sevastopol'].includes(f.properties.key))
      .map(f => label(f.properties.name.replace('Автономна Республіка ', ''), f.properties.label[1], f.properties.label[0], 'lbl-oblast')));
    layers.raionLabels = L.layerGroup(data.raions.features.map(f =>
      label(raionLabelText(f.properties), f.properties.label[1], f.properties.label[0], 'lbl-raion')));
    layers.russiaLabels = L.layerGroup(data.russia.features.map(f =>
      label(f.properties.name, f.properties.label[1], f.properties.label[0], 'lbl-ru')));
    layers.cityLabels = { 1: L.layerGroup(), 2: L.layerGroup(), 3: L.layerGroup() };
    for (const [n, lat, lon, rank] of CITIES) layers.cityLabels[rank].addLayer(label(n, lat, lon, 'lbl-city'));
    map.on('zoomend', updateLabels);
    updateLabels();
    applyAll();
  }

  function updateLabels() {
    const z = map.getZoom();
    const show = (layer, on) => { if (on && !map.hasLayer(layer)) layer.addTo(map); if (!on && map.hasLayer(layer)) map.removeLayer(layer); };
    show(layers.oblastLabels, z >= 5 && z < 8);
    show(layers.raionLabels, z >= 7);
    show(layers.russiaLabels, z >= 5 && z < 8);
    show(layers.cityLabels[1], z >= 5);
    show(layers.cityLabels[2], z >= 7);
    show(layers.cityLabels[3], z >= 8);
  }

  // ---------------------------------------------------------------- alerts
  function alertFor(props) {
    if (!state.showAlerts) return null;
    const own = state.alerts.find(a => a.kind === 'raion' && a.id === props.id);
    const obl = state.alerts.find(a => a.kind === 'oblast' && a.id === props.oblast);
    if (own && obl) return own.level === 'red' || obl.level !== 'red' ? own : obl;
    return own || obl || null;
  }

  function raionTip(p, l) {
    const a = l._alert;
    const t = a ? `<br><span style="color:${a.level === 'red' ? '#ff8a8a' : '#f2cc5b'}">${a.level === 'red' ? 'Red' : 'Yellow'}-level air alert since ${new Date(a.since * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>` : '';
    return `<b>${raionLabelText(p)}</b> · ${p.name_en}${t}`;
  }

  function applyAlerts() {
    if (!data) return;
    const landOpacity = state.detail ? 0.25 : 1;
    for (const l of Object.values(raionIndex)) {
      const a = alertFor(l.feature.properties);
      l._alert = a;
      l.setStyle({
        fillColor: a ? (a.level === 'red' ? PAL.red : PAL.yellow) : PAL.land,
        fillOpacity: a ? (state.detail ? 0.5 : 1) : landOpacity,
      });
    }
    for (const l of Object.values(ruIndex)) l.setStyle({ fillColor: PAL.russia, fillOpacity: state.detail ? 0.3 : 1 });
    layers.neighbors.setStyle({ fillOpacity: state.detail ? 0.3 : 1 });
  }

  // ---------------------------------------------------------------- occupied
  function applyOccupied() {
    if (!data) return;
    layers.occupied.clearLayers();
    if (state.showOccupied && state.occupied?.features?.length) layers.occupied.addData(state.occupied);
    layers.occupied.setStyle({ fillOpacity: state.detail ? 0.55 : 0.92 });
  }

  // ---------------------------------------------------------------- danger zones over Russia (Russian sources)
  function zoneTip(z) {
    const kind = z.kind === 'missile' ? 'Missile danger' : 'Drone danger';
    return `<b>${kind}</b> · ${z.name}<br><span style="color:var(--muted)">Russian sources (@${z.channel}) · since ${new Date(z.since * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>`;
  }

  function applyRuZones() {
    if (!data) return;
    layers.ruZones.clearLayers();
    if (!state.showRussia) return;
    const style = { pane: 'dm-ru', color: PAL.ruDanger, weight: 1.4, fillColor: PAL.ruDanger, fillOpacity: 0.32, className: 'ru-zone' };
    for (const z of state.ruZones) {
      const poly = z.unit && (ruIndex[z.unit] || raionIndex[z.unit] || oblastIndex[z.unit]);
      const partial = /^(north|south|east|west)/.test(z.name);       // "south of Rostov region"
      let shape;
      if (poly && !partial) shape = L.geoJSON(poly.feature, { style: () => style, pane: 'dm-ru' });
      else shape = L.circle([z.lat, z.lon], { ...style, radius: poly ? 70000 : 16000 });
      shape.bindTooltip(zoneTip(z), { className: 'dm-tip', sticky: true }).addTo(layers.ruZones);
    }
  }

  function applyAll() { applyAlerts(); applyOccupied(); applyRuZones(); }

  function setDetail(on) {
    state.detail = on;
    if (on && !detailTiles) {
      detailTiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; OpenStreetMap contributors', className: 'dm-detail-tiles',
      });
    }
    if (on) detailTiles.addTo(map); else if (detailTiles) map.removeLayer(detailTiles);
    applyAll();
  }

  return {
    PAL, CITIES, init, setDetail,
    get data() { return data; },
    get state() { return state; },
    setAlerts(a) { state.alerts = a || []; applyAlerts(); },
    setOccupied(g) { state.occupied = g; applyOccupied(); },
    setRuZones(z) { state.ruZones = z || []; applyRuZones(); },
    setOptions(o) { Object.assign(state, o); applyAll(); },
    alertFor,
  };
})();
