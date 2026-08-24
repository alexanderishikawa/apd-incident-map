import maplibregl from "maplibre-gl";
import "./styles.css";
import { applyFilters, fillSelect, readFilters } from "./filters";
import type { Incident, Meta } from "./types";

const SOURCE_ID = "incidents";
const CLUSTER_LAYER = "clusters";
const CLUSTER_COUNT = "cluster-count";
const POINT_LAYER = "unclustered";

async function loadJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return r.json() as Promise<T>;
}

async function loadGzipJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  if (!r.body) throw new Error(`No body for ${url}`);
  const decompressed = r.body.pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(decompressed).text();
  return JSON.parse(text) as T;
}

function toGeoJSON(rows: Incident[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: rows
      .filter((r) => r.lat != null && r.lon != null)
      .map((r) => ({
        type: "Feature",
        properties: {
          case_number: r.case_number,
          offenses: r.offenses.join(", "),
          location_raw: r.location_raw || "",
          report_datetime: r.report_datetime || "",
          offense_datetime: r.offense_datetime || "",
          area_command: r.area_command || "",
          district_zone: r.district_zone || "",
        },
        geometry: {
          type: "Point",
          coordinates: [r.lon as number, r.lat as number],
        },
      })),
  };
}

function popupHtml(p: Record<string, unknown> | null | undefined): string {
  return `<strong>${p?.case_number ?? ""}</strong><br/>${p?.offenses ?? ""}<br/>
    <em>${p?.offense_datetime ?? ""}</em><br/>
    ${p?.location_raw ?? ""}<br/>
    Zone ${p?.district_zone ?? "?"} · ${p?.area_command ?? ""}`;
}

async function main() {
  let incidents: Incident[] = [];
  let meta: Meta = {
    last_pulled_at: null,
    count: 0,
    geocoded_count: 0,
    offenses: [],
    zips: [],
    zones: [],
    area_commands: [],
  };

  try {
    [incidents, meta] = await Promise.all([
      loadGzipJson<Incident[]>("./data/incidents.json.gz"),
      loadJson<Meta>("./data/meta.json"),
    ]);
  } catch (e) {
    console.warn(e);
    document.getElementById("stats")!.textContent =
      "No data yet. Run: apd pull && apd geocode && apd export";
  }

  fillSelect("offenses", meta.offenses);
  fillSelect("zips", meta.zips);
  fillSelect("zones", meta.zones);
  fillSelect("areas", meta.area_commands);

  const map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap",
        },
      },
      layers: [{ id: "osm", type: "raster", source: "osm" }],
    },
    center: [-97.74, 30.27],
    zoom: 10,
  });
  map.addControl(new maplibregl.NavigationControl(), "top-right");

  const render = () => {
    const f = readFilters();
    const filtered = applyFilters(incidents, f);
    const plotted = filtered.filter((r) => r.lat != null && r.lon != null);
    const ungeocoded = filtered.filter((r) => r.lat == null || r.lon == null);

    const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    const data = toGeoJSON(plotted);
    if (src) src.setData(data);
    else {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data,
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 45,
      });
      map.addLayer({
        id: CLUSTER_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#0b3d2e",
          "circle-radius": ["step", ["get", "point_count"], 16, 25, 22, 100, 30],
          "circle-opacity": 0.75,
        },
      });
      map.addLayer({
        id: CLUSTER_COUNT,
        type: "symbol",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
        },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: POINT_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "#c45c26",
          "circle-radius": 5,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#fff",
        },
      });
      map.on("click", POINT_LAYER, (e) => {
        const feat = e.features?.[0];
        if (!feat || feat.geometry.type !== "Point") return;
        const coords = feat.geometry.coordinates.slice() as [number, number];
        new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(popupHtml(feat.properties))
          .addTo(map);
      });
      map.on("click", CLUSTER_LAYER, async (e) => {
        const features = map.queryRenderedFeatures(e.point, {
          layers: [CLUSTER_LAYER],
        });
        const clusterId = features[0]?.properties?.cluster_id;
        if (clusterId == null) return;
        const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource;
        const zoom = await source.getClusterExpansionZoom(clusterId);
        const geom = features[0].geometry;
        if (geom.type !== "Point") return;
        map.easeTo({ center: geom.coordinates as [number, number], zoom });
      });
    }

    document.getElementById("stats")!.innerHTML = `
      Showing <strong>${filtered.length}</strong> of ${meta.count}
      (${plotted.length} on map)<br/>
      Last pull: ${meta.last_pulled_at ?? "—"}<br/>
      Geocoded in archive: ${meta.geocoded_count}/${meta.count}
    `;

    const list = document.getElementById("ungeocoded")!;
    list.innerHTML = "";
    if (f.showUngeocoded) {
      for (const r of ungeocoded.slice(0, 40)) {
        const li = document.createElement("li");
        li.textContent = `${r.case_number} · ${(r.offenses || []).join(", ")} · ${r.location_raw || "no address"}`;
        list.appendChild(li);
      }
      if (ungeocoded.length > 40) {
        const li = document.createElement("li");
        li.textContent = `…and ${ungeocoded.length - 40} more`;
        list.appendChild(li);
      }
    }
  };

  map.on("load", () => {
    render();
    const form = document.getElementById("filters")!;
    form.addEventListener("input", render);
    form.addEventListener("change", render);
    document.getElementById("reset")!.addEventListener("click", () => {
      (document.getElementById("filters") as HTMLFormElement).reset();
      for (const id of ["offenses", "zips", "zones", "areas"]) {
        const sel = document.getElementById(id) as HTMLSelectElement;
        for (const o of Array.from(sel.options)) o.selected = false;
      }
      render();
    });
  });
}

main();
