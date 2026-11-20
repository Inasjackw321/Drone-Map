/* Threat icon set. All icons point north (up) and are rotated to the heading on the map. */
(function () {
  const INK = '#0b0e12';

  const THREATS = {
    shahed:     { label: 'Shahed',            short: 'Shahed',  color: '#ff9f1c', family: 'drone' },
    jet_shahed: { label: 'Jet Shahed (Geran-3)', short: 'Jet Shahed', color: '#ff5a1f', family: 'drone' },
    gerbera:    { label: 'Gerbera decoy',     short: 'Gerbera', color: '#c9b79c', family: 'drone' },
    uav:        { label: 'UAV, type unknown', short: 'UAV',     color: '#ffd166', family: 'drone' },
    recon:      { label: 'Recon UAV (Orlan/ZALA)', short: 'Recon', color: '#5ec8ff', family: 'drone' },
    lancet:     { label: 'Lancet',            short: 'Lancet',  color: '#2ec4b6', family: 'drone' },
    molniya:    { label: 'Molniya',           short: 'Molniya', color: '#a3e635', family: 'drone' },
    fpv:        { label: 'FPV drone',         short: 'FPV',     color: '#4ade80', family: 'drone' },
    cruise:     { label: 'Cruise missile',    short: 'Cruise',  color: '#ff4d6d', family: 'missile' },
    ballistic:  { label: 'Ballistic missile', short: 'Ballistic', color: '#ff1f4b', family: 'missile' },
    kinzhal:    { label: 'Kinzhal',           short: 'Kinzhal', color: '#c084fc', family: 'missile' },
    missile:    { label: 'Missile, type unknown', short: 'Missile', color: '#ff8a8a', family: 'missile' },
    kab:        { label: 'Guided bomb (KAB)', short: 'KAB',     color: '#ff66c4', family: 'kab' },
  };

  const S = `stroke="${INK}" stroke-width="1.6" stroke-linejoin="round"`;

  const BODY = {
    shahed: c => `
      <path d="M16 3 L29.5 24.5 L23.5 25.5 L16 21 L8.5 25.5 L2.5 24.5 Z" fill="${c}" ${S}/>
      <path d="M3.2 24.3 L3.2 20.5 M28.8 24.3 L28.8 20.5" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"/>
      <rect x="12.5" y="21.2" width="7" height="2.4" rx="1.2" fill="${INK}"/>`,
    jet_shahed: c => `
      <path d="M13.6 23.2 L16 31 L18.4 23.2 Z" fill="#ffd166" stroke="${INK}" stroke-width="1"/>
      <path d="M16 2 L26.5 25 L16 21.8 L5.5 25 Z" fill="${c}" ${S}/>
      <path d="M16 7 L16 19" stroke="${INK}" stroke-width="1.4"/>`,
    gerbera: c => `
      <path d="M16 4 L28.5 24.5 L16 21 L3.5 24.5 Z" fill="${c}" fill-opacity="0.45" stroke="${c}" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="M16 4 L28.5 24.5 L16 21 L3.5 24.5 Z" fill="none" stroke="${INK}" stroke-width="0.8" stroke-dasharray="2 2"/>`,
    uav: c => `
      <path d="M16 20.5 L22.6 26.8 L21.1 28.4 L16 24.4 L10.9 28.4 L9.4 26.8 Z" fill="${c}" ${S}/>
      <path d="M16 8.6 L29.2 13.6 L29.2 16.4 L16 13.9 L2.8 16.4 L2.8 13.6 Z" fill="${c}" ${S}/>
      <path d="M16 2.6 C17.5 2.6 18.1 4.4 18.1 6.6 V24.6 L16 27.6 L13.9 24.6 V6.6 C13.9 4.4 14.5 2.6 16 2.6 Z" fill="${c}" ${S}/>
      <circle cx="16" cy="6.4" r="1.15" fill="${INK}"/>`,
    recon: c => `
      <rect x="13.9" y="2.5" width="4.2" height="25" rx="2" fill="${c}" ${S}/>
      <rect x="1" y="9.8" width="30" height="4.8" rx="2" fill="${c}" ${S}/>
      <rect x="8.5" y="23" width="15" height="4" rx="1.8" fill="${c}" ${S}/>
      <path d="M11 2.8 H21" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`,
    lancet: c => `
      <rect x="13.8" y="2" width="4.4" height="27" rx="2" fill="${c}" ${S}/>
      <path d="M16 6.5 L26 12 L26 15.2 L16 11.6 L6 15.2 L6 12 Z" fill="${c}" ${S}/>
      <path d="M16 16.5 L28.5 23.5 L28.5 27 L16 22.4 L3.5 27 L3.5 23.5 Z" fill="${c}" ${S}/>`,
    molniya: c => `
      <rect x="13.9" y="3.5" width="4.2" height="22" rx="2" fill="${c}" ${S}/>
      <rect x="3.5" y="10" width="25" height="4.4" rx="2" fill="${c}" ${S}/>
      <path d="M16 20.5 L23 26.5 L21 28.6 L16 24.6 L11 28.6 L9 26.5 Z" fill="${c}" ${S}/>`,
    fpv: c => `
      <path d="M8.5 8.5 L23.5 23.5 M23.5 8.5 L8.5 23.5" stroke="${INK}" stroke-width="4.6" stroke-linecap="round"/>
      <path d="M8.5 8.5 L23.5 23.5 M23.5 8.5 L8.5 23.5" stroke="${c}" stroke-width="2.6" stroke-linecap="round"/>
      <circle cx="8" cy="8" r="4.2" fill="${c}" ${S}/><circle cx="24" cy="8" r="4.2" fill="${c}" ${S}/>
      <circle cx="8" cy="24" r="4.2" fill="${c}" ${S}/><circle cx="24" cy="24" r="4.2" fill="${c}" ${S}/>
      <path d="M16 11.5 L19 17 H13 Z" fill="${INK}"/>`,
    cruise: c => `
      <path d="M18.8 11.5 L27.5 17.5 L27.5 20 L18.8 17.4 Z M13.2 11.5 L4.5 17.5 L4.5 20 L13.2 17.4 Z" fill="${c}" ${S}/>
      <path d="M18.6 22 L23.5 28.6 L18.6 27.4 Z M13.4 22 L8.5 28.6 L13.4 27.4 Z" fill="${c}" ${S}/>
      <path d="M16 1 L19.2 5.8 V27 L16 30.5 L12.8 27 V5.8 Z" fill="${c}" ${S}/>`,
    missile: c => `
      <path d="M18.8 19.5 L24 27.8 L18.8 26.6 Z M13.2 19.5 L8 27.8 L13.2 26.6 Z" fill="${c}" ${S}/>
      <path d="M16 1.5 L19.2 6.5 V27.5 H12.8 V6.5 Z" fill="${c}" ${S}/>`,
    ballistic: c => `
      <path d="M13.4 24.5 L16 31 L18.6 24.5 Z" fill="#ffd166" stroke="${INK}" stroke-width="1"/>
      <path d="M12.6 17.5 L7.5 26 L12.6 24.2 Z M19.4 17.5 L24.5 26 L19.4 24.2 Z" fill="${c}" ${S}/>
      <path d="M16 1 C19.2 4 19.6 8 19.6 11 V24.8 H12.4 V11 C12.4 8 12.8 4 16 1 Z" fill="${c}" ${S}/>
      <path d="M12.6 9.5 H19.4" stroke="${INK}" stroke-width="1.2"/>`,
    kinzhal: c => `
      <path d="M13.6 25.5 L16 31 L18.4 25.5 Z" fill="#ffd166" stroke="${INK}" stroke-width="1"/>
      <path d="M16 1 L19.8 9 V21.5 L24 26.8 H8 L12.2 21.5 V9 Z" fill="${c}" ${S}/>
      <path d="M12.6 12 H19.4" stroke="${INK}" stroke-width="1.3"/>`,
    kab: c => `
      <path d="M11.8 11.5 L2.5 18.5 L2.5 21 L11.8 17.2 Z M20.2 11.5 L29.5 18.5 L29.5 21 L20.2 17.2 Z" fill="${c}" ${S}/>
      <path d="M12.6 21.5 L8.8 29 H23.2 L19.4 21.5 Z" fill="${c}" ${S}/>
      <ellipse cx="16" cy="14" rx="5.2" ry="11" fill="${c}" ${S}/>`,
  };

  function svg(threat, color, size = 32) {
    const t = THREATS[threat] || THREATS.uav;
    const c = color || t.color;
    const body = (BODY[threat] || BODY.uav)(c);
    return `<svg viewBox="0 0 32 32" width="${size}" height="${size}" aria-hidden="true">${body}</svg>`;
  }

  // mix a colour with white: map icons are white silhouettes with a faint type tint (neptun style)
  function tint(hex, amount = 0.78) {
    const n = parseInt(hex.slice(1), 16);
    const mix = (v) => Math.round(v + (255 - v) * amount);
    const r = mix((n >> 16) & 255), g = mix((n >> 8) & 255), b = mix(n & 255);
    return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
  }

  function mapSvg(threat, size = 30) {
    const t = THREATS[threat] || THREATS.uav;
    return svg(threat, tint(t.color, t.family === 'drone' ? 0.86 : 0.62), size);
  }

  function svgDataUrl(markup) {
    const m = markup.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ');
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(m);
  }

  function explosion(size = 26, color = '#ffb020') {
    return `<svg viewBox="0 0 32 32" width="${size}" height="${size}" aria-hidden="true">
      <path d="M16 1.5 L19 10 L27.5 5.5 L23 13.5 L31 16 L23 18.5 L27.5 26.5 L19 22 L16 30.5 L13 22 L4.5 26.5 L9 18.5 L1 16 L9 13.5 L4.5 5.5 L13 10 Z"
        fill="${color}" stroke="${INK}" stroke-width="1.4" stroke-linejoin="round"/>
      <circle cx="16" cy="16" r="4.2" fill="#fff3c4"/></svg>`;
  }

  function kill(size = 18) {
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="#1d232b" stroke="#9aa4b2" stroke-width="1.5"/>
      <path d="M7.5 7.5 L16.5 16.5 M16.5 7.5 L7.5 16.5" stroke="#e6e9ee" stroke-width="2.4" stroke-linecap="round"/></svg>`;
  }

  window.DMIcons = { THREATS, svg, mapSvg, tint, svgDataUrl, explosion, kill };
})();
