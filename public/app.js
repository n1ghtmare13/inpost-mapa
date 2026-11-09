/**
 * InPost Cut-off Zones Client Controller
 * Renders spatial zone partitions, clusters lockers, and provides instant postcode lookup.
 */

const zoneColors = {
  'A': '#10b981',
  'B': '#0284c7',
  'C': '#f59e0b',
  'D': '#ef4444'
};

const zoneTimes = {
  'A': '16:00',
  'B': '15:00',
  'C': '14:00',
  'D': '13:00'
};

// Fixed fill opacity for spatial zone partitions
const FIXED_OPACITY = 0.25;

// Initialize base map instance
const map = L.map('map', { 
  center: [52.0688, 19.4797], 
  zoom: 7,
  zoomControl: false 
});

L.control.zoom({ position: 'bottomright' }).addTo(map);

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
  attribution: '&copy; InPost® &copy; OpenStreetMap',
  maxZoom: 17
}).addTo(map);

// Reactive state tracking
const activeZones = { 'A': true, 'B': true, 'C': true, 'D': true };
const activeTypes = { 'locker': true, 'pop': true };

const polygonLayers = {};
const clusterGroups = {};
const markersStore = { 
  'A': { locker: [], pop: [] }, 
  'B': { locker: [], pop: [] }, 
  'C': { locker: [], pop: [] }, 
  'D': { locker: [], pop: [] } 
};

let postcodesIndex = {};
let searchMarker = null;

// DOM element references
const drawerEl = document.getElementById('drawer');
const dragHandle = document.getElementById('dragHandle');
const inputEl = document.getElementById('postcode-input');
const resultEl = document.getElementById('search-result');
const clearBtn = document.getElementById('search-clear-btn');

/**
 * Mobile drawer interaction controller
 */
function toggleDrawer() {
  drawerEl.classList.toggle('collapsed');
}

if (dragHandle) {
  dragHandle.addEventListener('click', toggleDrawer);
}

// Automatically collapse drawer on mobile drag to prioritize map visibility
if (window.innerWidth <= 640) {
  map.on('dragstart', () => {
    drawerEl.classList.add('collapsed');
  });
}

// Auto-expand drawer when search input gains user focus
inputEl.addEventListener('focus', () => {
  drawerEl.classList.remove('collapsed');
});

// Custom point markers
const lockerIcon = L.divIcon({ 
  html: '<div class="point-dot dot-locker"></div>', 
  className: 'custom-cluster-marker', 
  iconSize: [9, 9], 
  iconAnchor: [4.5, 4.5] 
});

const popIcon = L.divIcon({ 
  html: '<div class="point-dot dot-pop"></div>', 
  className: 'custom-cluster-marker', 
  iconSize: [9, 9], 
  iconAnchor: [4.5, 4.5] 
});

/**
 * Factory for creating optimized zone-specific cluster groups
 * @param {string} zone - Zone identifier ('A', 'B', 'C', 'D')
 * @returns {L.MarkerClusterGroup}
 */
function createClusterGroup(zone) {
  return L.markerClusterGroup({
    chunkedLoading: true,
    removeOutsideVisibleBounds: true,
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    iconCreateFunction: function(cluster) {
      const count = cluster.getChildCount();
      const size = count >= 1000 ? 40 : (count >= 100 ? 34 : 28);
      return L.divIcon({
        html: `<div class="cluster-bubble cluster-${zone}" style="font-size:${size > 30 ? 12 : 11}px;">${count}</div>`,
        className: 'custom-cluster-marker',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
      });
    }
  });
}

/**
 * Synchronizes visible markers in a cluster group based on active filters
 * @param {string} zone - Zone identifier ('A', 'B', 'C', 'D')
 */
function updateZoneClusters(zone) {
  const group = clusterGroups[zone];
  if (!group) return;
  group.clearLayers();

  if (!activeZones[zone]) return;

  const toAdd = [];
  if (activeTypes.locker) toAdd.push(...markersStore[zone].locker);
  if (activeTypes.pop) toAdd.push(...markersStore[zone].pop);
  group.addLayers(toAdd);
}

// 1. Fetch and render zone boundaries
fetch('data/zones.geojson')
  .then(res => res.json())
  .then(data => {
    data.features.forEach(feature => {
      const zone = feature.properties.z;
      const layer = L.geoJSON(feature, {
        interactive: false,
        style: {
          fillColor: zoneColors[zone],
          fillOpacity: FIXED_OPACITY,
          color: zoneColors[zone],
          weight: 1.2,
          opacity: 0.8
        }
      });
      polygonLayers[zone] = layer;
      layer.addTo(map);
    });
  });

// 2. Fetch point payload (lockers and PUDO locations)
fetch('data/points.json')
  .then(res => res.json())
  .then(data => {
    ['A', 'B', 'C', 'D'].forEach(zone => {
      const group = createClusterGroup(zone);
      clusterGroups[zone] = group;
      map.addLayer(group);

      const items = data[zone] || [];
      const badge = document.getElementById(`count-${zone.toLowerCase()}`);
      if (badge) badge.innerText = items.length.toLocaleString('pl-PL');

      items.forEach(pt => {
        const isPop = pt[6] === 'pop';
        const typeLabel = isPop ? 'PaczkoPunkt®' : 'Paczkomat®';
        const marker = L.marker([pt[0], pt[1]], { icon: isPop ? popIcon : lockerIcon });
        marker.bindPopup(`
          <div style="font-size:13px; line-height:1.4;">
            <div style="font-size:10px; font-weight:700; text-transform:uppercase; color:#64748b; margin-bottom:2px;">
              ${typeLabel}
            </div>
            <b style="font-size:14px; color:#0f172a;">${pt[2]}</b><br>
            ${pt[3]}, ${pt[4]} ${pt[5]}<br>
            <span style="display:inline-block; margin-top:5px; padding:2px 6px; border-radius:4px; background:${zoneColors[zone]}; color:#fff; font-weight:bold; font-size:11px;">
              Strefa ${zone} (godz. graniczna ${zoneTimes[zone]})
            </span>
          </div>
        `);

        if (isPop) markersStore[zone].pop.push(marker);
        else markersStore[zone].locker.push(marker);
      });

      updateZoneClusters(zone);
    });
  });

// 3. Load pre-indexed postal code lookup table
fetch('data/postcodes_lookup.json')
  .then(res => res.json())
  .then(data => {
    postcodesIndex = data;
  });

// 4. Postal code input formatter and search execution
inputEl.addEventListener('input', (e) => {
  let cleaned = e.target.value.replace(/[^\d-]/g, '');
  let digits = cleaned.replace(/-/g, '').slice(0, 5);

  let formatted = '';
  if (digits.length <= 2) {
    formatted = digits;
    if (cleaned.endsWith('-') && digits.length === 2) {
      formatted = digits + '-';
    }
  } else {
    formatted = digits.slice(0, 2) + '-' + digits.slice(2);
  }

  e.target.value = formatted;
  clearBtn.style.display = formatted.length > 0 ? 'block' : 'none';

  if (digits.length === 5) {
    executeSearch(formatted);
  } else {
    resultEl.style.display = 'none';
    if (searchMarker) map.removeLayer(searchMarker);
  }
});

clearBtn.addEventListener('click', () => {
  inputEl.value = '';
  clearBtn.style.display = 'none';
  resultEl.style.display = 'none';
  if (searchMarker) map.removeLayer(searchMarker);
});

/**
 * Executes postal code lookup and smoothly pans map to target coordinates
 * @param {string} postcodeFormatted - Formatted postcode string (e.g. "01-234")
 */
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

    map.flyTo([lat, lon], 13, { duration: 1.2 });

    if (searchMarker) map.removeLayer(searchMarker);
    searchMarker = L.circleMarker([lat, lon], {
      radius: 9,
      fillColor: zoneColors[zone],
      color: '#ffffff',
      weight: 3,
      fillOpacity: 0.95
    }).addTo(map);

  } else {
    resultEl.className = 'search-result-card error';
    resultEl.style.display = 'block';
    resultEl.innerText = `Nie znaleziono kodu ${postcodeFormatted} w oficjalnej bazie InPost.`;
  }
}

/**
 * Toggles visibility of spatial zone boundaries
 * @param {string} zone - Zone identifier ('A', 'B', 'C', 'D')
 * @param {boolean} isVisible
 */
function toggleZone(zone, isVisible) {
  activeZones[zone] = isVisible;
  if (isVisible && polygonLayers[zone]) map.addLayer(polygonLayers[zone]);
  else if (!isVisible && polygonLayers[zone]) map.removeLayer(polygonLayers[zone]);
  updateZoneClusters(zone);
}

/**
 * Toggles visibility of specific point categories (Lockers vs PUDO)
 * @param {string} type - Point category identifier ('locker' or 'pop')
 * @param {boolean} isVisible
 */
function togglePointType(type, isVisible) {
  activeTypes[type] = isVisible;
  ['A', 'B', 'C', 'D'].forEach(zone => updateZoneClusters(zone));
}