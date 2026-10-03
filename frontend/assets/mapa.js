// Mapa da rede (Painel e Planta): base OSM/satélite, camadas vetoriais extraídas do PDF
// (tools/georef_plantas.py → assets/plantas/redes.geojson), adutora do OSM (infra.json)
// e marcadores dos elementos hidráulicos com o estado atual.
// Depende de Leaflet e de statusColor (shared.js).
const aguadaMapa = (() => {
  const BOUNDS = [[-22.856, -43.120], [-22.830, -43.088]];
  const CENTER = [-22.8382228, -43.1080717];
  const INK = '#0b1626';

  // Camadas sobre a base; `key` é o que as páginas usam para ligar/desligar
  const OVERLAYS = [
    { key:'adutora',  label:'Adutora (OSM)',        color:'#0891b2' },
    { key:'agua',     label:'Rede de água potável', color:'#2563eb' },
    { key:'incendio', label:'Rede de incêndio',     color:'#dc2626' },
    { key:'predios',  label:'Prédios',              color:'#475569' },
    { key:'areas',    label:'Áreas A / B / C',      color:'#a16207' },
  ];

  const key = (value) => String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');

  function coords(feature) {
    const lat = Number(feature?.lat);
    const lng = Number(feature?.lng ?? feature?.lon);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
  }

  function findInfra(infra, collection, name) {
    const target = key(name);
    return (infra?.[collection] || []).find((item) => [item.name, item.ref, item.id].some((c) => key(c) === target)) || null;
  }

  // Reservatório → local do infra.json (pares CB31/32, CIE1/2, CBIF1/2 dividem o ponto)
  function siteOf(alias) {
    const k = key(alias);
    if (k.startsWith('CB3')) return 'CB03';
    if (k.startsWith('CIE')) return 'CIE';
    if (k.startsWith('CBIF')) return 'CBIF';
    return k;
  }

  function pumpSite(name) {
    const k = key(name);
    if (k.includes('IF')) return 'CBIF';
    if (k.includes('02') || k.includes('CB2')) return 'CB2';
    if (k.includes('01') || k.includes('CB1')) return 'CB1';
    if (k.includes('03') || k.includes('CB3')) return 'CB3';
    return k || 'BOMBA';
  }

  function pumpSummary(pumps, site) {
    const related = (pumps || []).filter((item) => pumpSite(item.pump_name) === site);
    if (!related.length) return { label:'—', color:'#64748b', detail:'Sem registro' };
    const active = related.filter((item) => item.state === 'ligada').length;
    const inAlarm = related.some((item) => item.state === 'falha');
    return {
      label:`${active}/${related.length}`,
      color:inAlarm ? '#dc2626' : (active > 0 ? '#2563eb' : '#64748b'),
      detail:related.map((item) => `${item.pump_name}: ${item.state || '—'}`).join('<br>'),
    };
  }

  function valveSummary(valves, name) {
    const state = (valves || []).find((item) => key(item.valve_name) === key(name))?.state || 'desconhecida';
    return {
      label:state === 'aberta' ? 'ABR' : (state === 'fechada' ? 'FEC' : 'VAL'),
      color:state === 'aberta' ? '#16a34a' : (state === 'fechada' ? '#dc2626' : '#64748b'),
      detail:`<b>${name}</b><br>${state}`,
    };
  }

  function hydrometerSummary(hydrometers, name) {
    const current = (hydrometers || []).find((item) => key(item.meter_name) === key(name));
    const reading = Number(current?.reading);
    return {
      label:Number.isFinite(reading) ? `${reading.toFixed(1)}m3` : 'HID',
      color:'#0f766e',
      detail:Number.isFinite(reading) ? `<b>${name}</b><br>${reading.toFixed(3)} ${current?.unit || 'm3'}` : `<b>${name}</b><br>Sem leitura`,
    };
  }

  // data = { reservoirs, pumps, valves, hydrometers, infra }; visible(type) aplica os filtros da página
  function buildElements(data, zoom = 17, visible = () => true) {
    const infra = data.infra;
    const tanks = (data.reservoirs || []).map((r) => {
      const c = coords(r) || coords(findInfra(infra, 'reservoirs', siteOf(r.alias)));
      return c ? { ...r, ...c, key:`res:${r.alias}`, type:'res' } : null;
    }).filter(Boolean);
    // Pares no mesmo local viram um marcador com dois tanques
    const bySite = new Map();
    tanks.forEach((t) => bySite.set(siteOf(t.alias), [...(bySite.get(siteOf(t.alias)) || []), t]));
    const reservoirs = [...bySite.entries()].map(([site, group]) => group.length === 1 ? group[0]
      : { ...group[0], key:`res:${site}`, site:site === 'CB03' ? 'CB3' : site, tanks:group });

    const pumps = [
      { alias:'CB3', name:'Casa de Bombas 3 — recalque CIE → CON/CAV', feature:findInfra(infra, 'reservoirs', 'CB03'), colocated:true },
      { alias:'CB2', name:'Casa de Bombas 2 — pressurização da rede de incêndio', feature:findInfra(infra, 'pumps', 'CB02') },
      { alias:'CB1', name:'Casa de Bombas 1 — emergência (água do mar)', feature:findInfra(infra, 'pumps', 'CB01') },
      { alias:'CBIF', name:'Casa de Bombas Ilha das Flores', feature:findInfra(infra, 'reservoirs', 'CBIF'), colocated:true },
    ].map((item) => {
      const c = coords(item.feature);
      if (!c) return null;
      const summary = pumpSummary(data.pumps, item.alias);
      // colocated: bomba no ponto dos tanques da casa — o rótulo dos tanques já identifica o local
      return { key:`pump:${item.alias}`, alias:item.alias, name:item.name, type:'pump', colocated:item.colocated, ...c,
        summary:{ ...summary, detail:`<b>${item.name}</b><br>${summary.detail}` } };
    }).filter(Boolean);

    const valves = (infra?.valves || []).filter((item) => String(item.name || '').startsWith('V-')).map((item) => {
      const c = coords(item);
      return c ? { key:`valve:${item.name}`, alias:item.name.replace(/^V-/, ''), name:item.name, type:'valve', ...c, summary:valveSummary(data.valves, item.name) } : null;
    }).filter(Boolean);

    const hydrometers = (infra?.hydrometers || []).map((item) => {
      const c = coords(item);
      return c ? { key:`hyd:${item.name}`, alias:item.name, name:item.name, type:'hydrometer', ...c, summary:hydrometerSummary(data.hydrometers, item.name) } : null;
    }).filter(Boolean);

    // ETE e caixa de gordura levantadas em campo; fossas (approx) no prédio da oficina
    const sanitation = (infra?.sanitation || []).map((item) => ({
      key:`site:${item.id}`, alias:item.id, name:item.name, type:item.type, lat:item.lat, lng:item.lon,
      summary:{ detail:`<b>${item.name}</b>${item.approx ? '<br>posição aproximada (prédio da oficina)' : ''}` },
    }));

    // Válvulas e hidrômetros ficam a poucos metros dos reservatórios: no zoom 17 cairiam um em cima do outro
    const detail = zoom >= 18 ? [...valves, ...hydrometers] : [];
    return [...reservoirs, ...pumps, ...detail, ...sanitation].filter((item) => visible(item.type));
  }

  // Marcadores a menos de 28 px um do outro se abrem em anel em volta do ponto comum
  function spread(map, elements) {
    const clusters = [];
    elements.forEach((item) => {
      const point = map.latLngToLayerPoint([item.lat, item.lng]);
      let cluster = clusters.find((c) => Math.hypot(c.point.x - point.x, c.point.y - point.y) <= 28);
      if (!cluster) clusters.push(cluster = { point, items:[] });
      cluster.items.push(item);
    });
    return clusters.flatMap((cluster) => cluster.items.length === 1 ? cluster.items : cluster.items.map((item, index) => {
      const ring = Math.floor(index / 6);
      const slots = ring === 0 ? Math.min(cluster.items.length, 6) : 6;
      const angle = ((Math.PI * 2) / slots) * (index % 6);
      const radius = 26 + ring * 16;
      const ll = map.layerPointToLatLng(L.point(cluster.point.x + Math.cos(angle) * radius, cluster.point.y + Math.sin(angle) * radius));
      return { ...item, renderLat:ll.lat, renderLng:ll.lng };
    }));
  }

  // Símbolos no estilo P&ID: tanque com nível, bomba (círculo + triângulo), válvula gaveta
  // (mesma gravata do SCADA), hidrômetro (m³), ETE/caixa de gordura e fossa. Cor = estado.
  function symbol(item) {
    if (item.type === 'res') {
      const group = item.tanks || [item];
      const pctText = (t) => t.online ? (t.pct != null ? Math.round(t.pct) + '%' : '?') : 'OFF';
      const tank = (t, x) => {
        const c = statusColor(t.pct, t.online);
        const p = t.online && Number.isFinite(Number(t.pct)) ? Math.max(0, Math.min(100, Number(t.pct))) / 100 : 0;
        const h = 22 * p;
        return `<g data-alias="${t.alias}"><rect x="${x}" y="3" width="22" height="26" rx="4" fill="#fff" stroke="${INK}" stroke-width="2"/><rect x="${x + 2}" y="${5 + 22 - h}" width="18" height="${h}" rx="2" fill="${c}"/><rect x="${x}" y="3" width="22" height="26" rx="4" fill="none" stroke="${c}" stroke-width="2.5"/></g>`;
      };
      const size = group.length > 1 ? 54 : 32;
      return { size, h:32, label:`${item.site || item.alias} ${group.map(pctText).join(' · ')}`,
        svg:`<svg width="${size}" height="32" viewBox="0 0 ${size} 32">${group.map((t, i) => tank(t, 5 + i * 24)).join('')}</svg>` };
    }
    if (item.type === 'pump') {
      const c = item.summary.color;
      return { size:30, label:item.colocated ? null : `${item.alias} ${item.summary.label}`,
        svg:`<svg width="30" height="30" viewBox="0 0 30 30"><path d="M15 4 H27 V10" fill="none" stroke="${INK}" stroke-width="5"/><path d="M15 4 H27 V10" fill="none" stroke="${c}" stroke-width="2.5"/><circle cx="15" cy="16" r="11" fill="#fff" stroke="${c}" stroke-width="2.5"/><path d="M10 10.5 L22 16 L10 21.5 Z" fill="${c}"/></svg>` };
    }
    if (item.type === 'valve') {
      return { size:24, label:null,
        svg:`<svg width="24" height="24" viewBox="0 0 24 24"><path d="M12 13 V4 M7.5 4 H16.5" stroke="${INK}" stroke-width="2" stroke-linecap="round"/><path d="M3 8 V22 L21 8 V22 Z" fill="${item.summary.color}" stroke="${INK}" stroke-width="1.5" stroke-linejoin="round"/></svg>` };
    }
    if (item.type === 'hydrometer') {
      const c = item.summary.color;
      return { size:24, label:null,
        svg:`<svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="#fff" stroke="${c}" stroke-width="2.5"/><text x="12" y="15.5" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" font-weight="700" fill="${c}">m³</text></svg>` };
    }
    if (item.type === 'fossa') {
      return { size:22, label:null,
        svg:`<svg width="22" height="22" viewBox="0 0 22 22"><circle cx="11" cy="11" r="9.5" fill="#92400e" stroke="${INK}" stroke-width="1.5"/><path d="M5.5 9 q1.4-1.8 2.8 0 t2.8 0 t2.8 0 t2.8 0 M5.5 13.5 q1.4-1.8 2.8 0 t2.8 0 t2.8 0 t2.8 0" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>` };
    }
    const c = item.type === 'ete' ? '#8b5cf6' : '#d97706';
    return { size:30, label:item.alias,
      svg:`<svg width="30" height="30" viewBox="0 0 30 30"><rect x="2" y="2" width="26" height="26" rx="6" fill="${c}" stroke="${INK}" stroke-width="1.5"/><path d="M7 11 q2-2.5 4 0 t4 0 t4 0 t4 0 M7 16 q2-2.5 4 0 t4 0 t4 0 t4 0 M7 21 q2-2.5 4 0 t4 0 t4 0 t4 0" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>` };
  }

  function icon(item) {
    const { size, h = size, label, svg } = symbol(item);
    return L.divIcon({
      className:'aguada-marker',
      html:`<div class="mk">${svg}${label ? `<div class="mk-lbl">${label}</div>` : ''}</div>`,
      iconSize:[size, h],
      iconAnchor:[size / 2, h / 2],
    });
  }

  // Atualiza os marcadores de `dict` (key → L.marker); bind(marker, item) só roda na criação
  function syncMarkers(map, dict, elements, bind) {
    if (!map) return;
    const placed = spread(map, elements);
    const active = new Set(placed.map((item) => item.key));
    Object.keys(dict).forEach((k) => { if (!active.has(k)) { dict[k].remove(); delete dict[k]; } });
    placed.forEach((item) => {
      const ll = [item.renderLat ?? item.lat, item.renderLng ?? item.lng];
      if (dict[item.key]) {
        dict[item.key].setLatLng(ll).setIcon(icon(item));
        return;
      }
      dict[item.key] = L.marker(ll, { icon:icon(item) }).addTo(map);
      bind(dict[item.key], item);
    });
  }

  let redesPromise = null;
  const loadRedes = () => redesPromise ??= fetch('assets/plantas/redes.geojson').then((r) => r.json()).catch(() => null);

  function adutoraLayer(infra, renderer) {
    const group = L.layerGroup();
    (infra?.pipelines || []).forEach((pipe) => {
      const pts = (pipe.coords || []).map((c) => [c[0], c[1]]);
      if (!pts.length) return;
      L.polyline(pts, { renderer, color:'#ffffff', weight:6, opacity:0.7, lineCap:'round', lineJoin:'round', interactive:false }).addTo(group);
      L.polyline(pts, { renderer, color:pipe.submarine ? '#06b6d4' : '#0891b2', weight:3, opacity:0.9,
        dashArray:pipe.submarine ? '8 4' : null, lineCap:'round', lineJoin:'round', interactive:false }).addTo(group);
    });
    return group;
  }

  // Cria o mapa. opts: { infra, on:[keys ligadas], control:true (lista de camadas do Leaflet), ...opções do L.map }
  async function createMap(el, { infra = null, on = ['adutora'], control = true, ...mapOpts } = {}) {
    const osm = L.tileLayer('assets/leaflet-tiles/{z}/{x}/{y}.png', { minZoom:13, maxZoom:19, maxNativeZoom:17, attribution:'© OpenStreetMap' });
    const sat = L.tileLayer('assets/leaflet-tiles-sat/{z}/{x}/{y}.jpg', { minZoom:13, maxZoom:19, maxNativeZoom:17, attribution:'© Esri WorldImagery' });
    const map = L.map(el, {
      minZoom:13, maxZoom:19, maxBounds:L.latLngBounds(BOUNDS), maxBoundsViscosity:0.8, layers:[osm], ...mapOpts,
    }).setView(mapOpts.center || CENTER, mapOpts.zoom || 17);

    const renderer = L.canvas({ padding:0.5 });
    const overlays = { adutora:adutoraLayer(infra, renderer) };
    const redes = await loadRedes();
    const style = Object.fromEntries(OVERLAYS.map((o) => [o.key, o.color]));
    ['agua', 'incendio', 'predios', 'areas'].forEach((k) => {
      const features = (redes?.features || []).filter((f) => f.properties.layer === k);
      if (!features.length) return;
      overlays[k] = L.geoJSON(features, { renderer, interactive:false,
        style:{ color:style[k], weight:k === 'predios' ? 1.2 : (k === 'areas' ? 1.5 : 2.2), opacity:0.9 } });
    });
    if (overlays.areas) {
      (redes.features || []).filter((f) => f.properties.layer === 'rotulo').forEach((f) => {
        const [lng, lat] = f.geometry.coordinates;
        L.marker([lat, lng], { interactive:false, keyboard:false,
          icon:L.divIcon({ className:'area-label', html:f.properties.label, iconSize:null }) }).addTo(overlays.areas);
      });
    }
    // Prédios em cinza-escuro somem no satélite: clareia ao trocar a base
    map.on('baselayerchange', (e) => overlays.predios?.setStyle({ color:e.layer === sat ? '#e2e8f0' : style.predios }));
    on.forEach((k) => overlays[k]?.addTo(map));

    const named = Object.fromEntries(OVERLAYS.filter((o) => overlays[o.key]).map((o) => [o.label, overlays[o.key]]));
    L.control.layers({ 'Mapa':osm, 'Satélite':sat }, control ? named : {}, { position:'topright', collapsed:true }).addTo(map);
    return { map, overlays };
  }

  return { OVERLAYS, createMap, buildElements, syncMarkers };
})();
