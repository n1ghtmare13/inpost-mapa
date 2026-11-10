/**
 * InPost Cut-off Zones Client Controller (MapLibre GL JS + OpenFreeMap Vector Engine)
 */

const zoneColors = {
  'A': '#10b981', // Emerald Green
  'B': '#6366f1', // Indigo
  'C': '#f59e0b', // Amber
  'D': '#e11d48'  // Carmine
};

const zoneTimes = {
  'A': '16:00',
  'B': '15:00',
  'C': '14:00',
  'D': '13:00'
};

const FIXED_OPACITY = 0.22;

// Initialize WebGL Map with up-to-date vector tiles from OpenFreeMap (OSM)
const map = new maplibregl.Map({
  container: 'map',
  center: [19.4797, 52.0688],
  zoom: 6,
  style: 'https://tiles.openfreemap.org/styles/liberty',
  dragRotate: false,      // Disables mouse right-click and Ctrl+drag rotation
  pitchWithRotate: false, // Prevents 3D tilting
  maxPitch: 0             // Strictly locks map to flat 2D
});

map.touchZoomRotate.disableRotation();

map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

// Active filter state
const activeZones = { 'A': true, 'B': true, 'C': true, 'D': true };
const activeTypes = { 'locker': true, 'pop': true };

let allPointsFeatures = [];
let postcodesIndex = {};
let searchMarker = null;

// DOM element references
const drawerEl = document.getElementById('drawer');
const dragHandle = document.getElementById('dragHandle');
const inputEl = document.getElementById('postcode-input');
const resultEl = document.getElementById('search-result');
const clearBtn = document.getElementById('search-clear-btn');

// Mobile drawer controls
function toggleDrawer() {
  drawerEl.classList.toggle('collapsed');
}

if (dragHandle) {
  dragHandle.addEventListener('click', toggleDrawer);
}

if (window.innerWidth <= 640) {
  map.on('dragstart', () => drawerEl.classList.add('collapsed'));
}

inputEl.addEventListener('focus', () => drawerEl.classList.remove('collapsed'));

/**
 * Filter generator for WebGL layers
 */
function updateMapFilters() {
  const allowedZones = Object.keys(activeZones).filter(z => activeZones[z]);
  const allowedTypes = Object.keys(activeTypes).filter(t => activeTypes[t]);

  // Update polygon fill and line visibility in GPU
  const zoneFilter = ['in', ['get', 'z'], ['literal', allowedZones]];
  if (map.getLayer('zones-fill')) map.setFilter('zones-fill', zoneFilter);
  if (map.getLayer('zones-line')) map.setFilter('zones-line', zoneFilter);

  // Update points source dataset to dynamically recalculate supercluster in WebWorker
  const filtered = allPointsFeatures.filter(f => 
    activeZones[f.properties.z] && activeTypes[f.properties.t]
  );

  const source = map.getSource('points-source');
  if (source) {
    source.setData({
      type: 'FeatureCollection',
      features: filtered
    });
  }
}

map.on('load', async () => {
  // Find the first symbol/label layer so polygon fills sit UNDER street & city labels
  const layers = map.getStyle().layers;
  let firstSymbolId;
  for (let i = 0; i < layers.length; i++) {
    if (layers[i].type === 'symbol') {
      firstSymbolId = layers[i].id;
      break;
    }
  }

  // 1. Load and configure spatial zone boundaries
  map.addSource('zones-source', {
    type: 'geojson',
    data: 'data/zones.geojson'
  });

  map.addLayer({
    id: 'zones-fill',
    type: 'fill',
    source: 'zones-source',
    paint: {
      'fill-color': [
        'match',
        ['get', 'z'],
        'A', zoneColors['A'],
        'B', zoneColors['B'],
        'C', zoneColors['C'],
        'D', zoneColors['D'],
        '#cccccc'
      ],
      'fill-opacity': FIXED_OPACITY
    }
  }, firstSymbolId);

  map.addLayer({
    id: 'zones-line',
    type: 'line',
    source: 'zones-source',
    paint: {
      'line-color': [
        'match',
        ['get', 'z'],
        'A', zoneColors['A'],
        'B', zoneColors['B'],
        'C', zoneColors['C'],
        'D', zoneColors['D'],
        '#cccccc'
      ],
      'line-width': 1.2,
      'line-opacity': 0.8
    }
  }, firstSymbolId);

  // 2. Fetch point locations and construct internal GeoJSON representation
  const res = await fetch('data/points.json');
  const pointsData = await res.json();

  ['A', 'B', 'C', 'D'].forEach(zone => {
    const items = pointsData[zone] || [];
    const badge = document.getElementById(`count-${zone.toLowerCase()}`);
    if (badge) badge.innerText = items.length.toLocaleString('pl-PL');

    items.forEach(pt => {
      allPointsFeatures.push({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [pt[1], pt[0]] // lon, lat
        },
        properties: {
          n: pt[2],
          s: pt[3],
          p: pt[4],
          c: pt[5],
          t: pt[6], // 'locker' or 'pop'
          z: zone
        }
      });
    });
  });

  // Add clustered GeoJSON source directly to WebGL engine
  map.addSource('points-source', {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: allPointsFeatures
    },
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 70
  });

  // Layer: Cluster Circles
  map.addLayer({
    id: 'clusters',
    type: 'circle',
    source: 'points-source',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': '#1e293b',
      'circle-radius': [
        'step',
        ['get', 'point_count'],
        14,
        25, 17,
        100, 21,
        500, 25
      ],
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff'
    }
  });

  // Layer: Cluster Count Labels
  map.addLayer({
    id: 'cluster-count',
    type: 'symbol',
    source: 'points-source',
    filter: ['has', 'point_count'],
    layout: {
      'text-field': ['get', 'point_count_abbreviated'],
      'text-size': 11.5,
      'text-font': ['Noto Sans Bold']
    },
    paint: {
      'text-color': '#ffffff'
    }
  });

  // Layer: Individual Unclustered Points
  map.addLayer({
    id: 'unclustered-points',
    type: 'circle',
    source: 'points-source',
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': [
        'match',
        ['get', 't'],
        'pop', '#7c3aed',
        '#111827'
      ],
      'circle-radius': 4.5,
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff'
    }
  });

  map.on('click', 'clusters', async (e) => {
    const features = map.queryRenderedFeatures(e.point, { layers: ['clusters'] });
    const clusterId = features[0].properties.cluster_id;
    const zoom = await map.getSource('points-source').getClusterExpansionZoom(clusterId);
    map.easeTo({ center: features[0].geometry.coordinates, zoom });
  });

  map.on('click', 'unclustered-points', (e) => {
    const props = e.features[0].properties;
    const coords = e.features[0].geometry.coordinates.slice();
    const isPop = props.t === 'pop';
    const typeLabel = isPop ? 'PaczkoPunkt®' : 'Paczkomat®';
    const z = props.z;

    new maplibregl.Popup({ offset: 10 })
      .setLngLat(coords)
      .setHTML(`
        <div style="font-size:13px; line-height:1.4;">
          <div style="font-size:10px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:2px;">
            ${typeLabel}
          </div>
          <b style="font-size:14px; color:#0f172a;">${props.n}</b><br>
          ${props.s}, ${props.p} ${props.c}<br>
          <span style="display:inline-block; margin-top:5px; padding:2px 6px; border-radius:4px; background:${zoneColors[z]}; color:#fff; font-weight:bold; font-size:11px;">
            Strefa ${z} (godz. graniczna ${zoneTimes[z]})
          </span>
        </div>
      `)
      .addTo(map);
  });

  // Pointer cursor interactions
  map.on('mouseenter', 'clusters', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'clusters', () => map.getCanvas().style.cursor = '');
  map.on('mouseenter', 'unclustered-points', () => map.getCanvas().style.cursor = 'pointer');
  map.on('mouseleave', 'unclustered-points', () => map.getCanvas().style.cursor = '');
});

// Load postal code lookup table
fetch('data/postcodes_lookup.json')
  .then(res => res.json())
  .then(data => {
    postcodesIndex = data;
  });

// Postcode search input controller
inputEl.addEventListener('input', (e) => {
  let cleaned = e.target.value.replace(/[^\d-]/g, '');
  let digits = cleaned.replace(/-/g, '').slice(0, 5);

  let formatted = '';
  if (digits.length <= 2) {
    formatted = digits;
    if (cleaned.endsWith('-') && digits.length === 2) formatted = digits + '-';
  } else {
    formatted = digits.slice(0, 2) + '-' + digits.slice(2);
  }

  e.target.value = formatted;
  clearBtn.style.display = formatted.length > 0 ? 'block' : 'none';

  if (digits.length === 5) {
    executeSearch(formatted);
  } else {
    resultEl.style.display = 'none';
    if (searchMarker) {
      searchMarker.remove();
      searchMarker = null;
    }
  }
});

clearBtn.addEventListener('click', () => {
  inputEl.value = '';
  clearBtn.style.display = 'none';
  resultEl.style.display = 'none';
  if (searchMarker) {
    searchMarker.remove();
    searchMarker = null;
  }
});

function executeSearch(postcodeFormatted) {
  const norm = postcodeFormatted.replace('-', '');
  const entry = postcodesIndex[norm];

  if (entry) {
    const [zone, lat, lon] = entry;
    resultEl.className = 'search-result-card success';
    resultEl.style.display = 'block';
    resultEl.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          Kod <b>${postcodeFormatted}</b> to <b>Strefa ${zone}</b>
          <div style="font-size:11.5px; color:#475569; margin-top:2px;">Godzina graniczna: <b>${zoneTimes[zone]}</b></div>
        </div>
        <span style="background:${zoneColors[zone]}; color:#fff; font-weight:800; font-size:15px; padding:3px 9px; border-radius:6px;">${zone}</span>
      </div>
    `;

    map.flyTo({ center: [lon, lat], zoom: 13, speed: 1.4 });

    if (searchMarker) searchMarker.remove();
    searchMarker = new maplibregl.Marker({ color: zoneColors[zone] })
      .setLngLat([lon, lat])
      .addTo(map);

  } else {
    resultEl.className = 'search-result-card error';
    resultEl.style.display = 'block';
    resultEl.innerText = `Nie znaleziono kodu ${postcodeFormatted} w oficjalnej bazie InPost.`;
  }
}

// Global filter event handlers
function toggleZone(zone, isVisible) {
  activeZones[zone] = isVisible;
  updateMapFilters();
}

function togglePointType(type, isVisible) {
  activeTypes[type] = isVisible;
  updateMapFilters();
}