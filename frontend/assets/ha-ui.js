// Aguada — HA UI utils. Gauge radial estilo Home Assistant (arco 270°) com bandas de severidade.
(function (global) {
  const NS = 'http://www.w3.org/2000/svg';

  function polar(cx, cy, r, deg) {
    const rad = (deg - 90) * Math.PI / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }
  function arcPath(cx, cy, r, startDeg, endDeg) {
    const [x1, y1] = polar(cx, cy, r, startDeg);
    const [x2, y2] = polar(cx, cy, r, endDeg);
    const large = (endDeg - startDeg) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  }
  // severity: thresholds em % { green, yellow, red } — abaixo de red=vermelho, abaixo de yellow=amarelo, senão verde
  function colorFor(pct, severity) {
    if (!severity) return 'var(--blue)';
    if (pct <= severity.red) return 'var(--red)';
    if (pct <= severity.yellow) return 'var(--yellow)';
    return 'var(--green)';
  }

  function renderGauge(el, opts) {
    if (!el) return;
    const o = opts || {};
    const value = Number(o.value) || 0;
    const min = o.min != null ? o.min : 0;
    const max = o.max != null ? o.max : 100;
    const unit = o.unit || '';
    const severity = o.severity || null;
    const size = o.size || 120;
    const cx = size / 2, cy = size / 2, r = size / 2 - 10;
    const START = -135, SWEEP = 270;
    const frac = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
    const endDeg = START + SWEEP * frac;
    const pct = ((value - min) / (max - min || 1)) * 100;

    el.classList.add('ha-gauge');
    el.innerHTML = '';

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size * 0.72}`);
    svg.setAttribute('width', size);

    const track = document.createElementNS(NS, 'path');
    track.setAttribute('d', arcPath(cx, cy, r, START, START + SWEEP));
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', 'var(--bg3)');
    track.setAttribute('stroke-width', '10');
    track.setAttribute('stroke-linecap', 'round');
    svg.appendChild(track);

    if (frac > 0) {
      const val = document.createElementNS(NS, 'path');
      val.setAttribute('d', arcPath(cx, cy, r, START, endDeg));
      val.setAttribute('fill', 'none');
      val.setAttribute('stroke', colorFor(pct, severity));
      val.setAttribute('stroke-width', '10');
      val.setAttribute('stroke-linecap', 'round');
      svg.appendChild(val);
    }
    el.appendChild(svg);

    const label = document.createElement('div');
    label.className = 'ha-gauge-value';
    label.textContent = Math.round(value) + (unit ? ' ' + unit : '');
    el.appendChild(label);
  }

  global.renderGauge = renderGauge;
})(window);
