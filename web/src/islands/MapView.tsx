/**
 * Karta över kommuner/regioner (MapLibre GL), laddas först när den syns (client:visible).
 * Ingen bakgrundskarta från tredje part: bara gränspolygoner ur en GeoJSON-fil.
 * Renderar ingenting om WebGL eller geodata saknas — sidan har alltid en tabell som fallback.
 */
import { useEffect, useRef, useState } from "react";
import type { MapLayerMouseEvent } from "maplibre-gl";

export interface MapValue {
  name: string;
  href: string;
  color: string;
  label: string;
}

interface Props {
  /** GeoJSON (FeatureCollection) med ett id per område i egenskapen `idProperty`. */
  geoUrl?: string | null;
  idProperty: string;
  values: Record<string, MapValue>;
  title: string;
  attribution: string;
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function MapView({ geoUrl, idProperty, values, title, attribution }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "off">(geoUrl ? "loading" : "off");

  useEffect(() => {
    if (!geoUrl || !ref.current || !hasWebGL()) {
      setState("off");
      return;
    }
    let map: { remove(): void } | null = null;
    let cancelled = false;
    (async () => {
      const [maplibregl, geo] = await Promise.all([  // MapLibre 6: namngivna exporter
        import("maplibre-gl"),
        fetch(geoUrl).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status))))),
        import("maplibre-gl/dist/maplibre-gl.css"),
      ]);
      if (cancelled || !ref.current) return;
      for (const f of geo.features ?? []) {
        const v = values[String(f.properties?.[idProperty])];
        f.properties = { ...f.properties, _color: v?.color ?? "#d0d0d0", _name: v?.name ?? "", _label: v?.label ?? "", _href: v?.href ?? "" };
      }
      const m = new maplibregl.Map({
        container: ref.current,
        style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#ffffff" } }] },
        bounds: [[10.5, 55.2], [24.2, 69.1]],
        fitBoundsOptions: { padding: 8 },
        attributionControl: { compact: true, customAttribution: attribution },
        dragRotate: false,
      });
      map = m;
      m.on("load", () => {
        m.addSource("areas", { type: "geojson", data: geo });
        m.addLayer({ id: "fill", type: "fill", source: "areas", paint: { "fill-color": ["get", "_color"], "fill-opacity": 0.85 } });
        m.addLayer({ id: "line", type: "line", source: "areas", paint: { "line-color": "#ffffff", "line-width": 0.6 } });
        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
        m.on("mousemove", "fill", (e: MapLayerMouseEvent) => {
          const p = e.features?.[0]?.properties;
          if (!p) return;
          m.getCanvas().style.cursor = p._href ? "pointer" : "";
          popup.setLngLat(e.lngLat).setText(`${p._name}: ${p._label}`).addTo(m);
        });
        m.on("mouseleave", "fill", () => { popup.remove(); m.getCanvas().style.cursor = ""; });
        m.on("click", "fill", (e: MapLayerMouseEvent) => {
          const href = e.features?.[0]?.properties?._href;
          if (href) window.location.href = href;
        });
        setState("ready");
      });
    })().catch(() => setState("off"));
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [geoUrl, idProperty, values, attribution]);

  if (state === "off") return null;
  return (
    <figure>
      <div ref={ref} role="img" aria-label={`${title}. Samma uppgifter finns i tabellen nedan.`}
        style={{ width: "100%", height: "min(70vh, 34rem)", background: "#f7f7f5", borderRadius: 6 }} />
      <figcaption className="small muted">{state === "loading" ? "Laddar karta …" : title}</figcaption>
    </figure>
  );
}
