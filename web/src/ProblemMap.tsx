import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

interface MapProps {
  problems: { title: string; lat: number; lon: number; score: number }[];
}

export default function ProblemMap({ problems }: MapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;

    map.current = new maplibregl.Map({
      container: container.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [22.9439, 40.6403], // Thessaloniki
      zoom: 11,
    });

    map.current.addControl(new maplibregl.NavigationControl(), "top-right");
  }, []);

  useEffect(() => {
    if (!map.current) return;

    // Clear old markers
    const markers = document.querySelectorAll(".maplibregl-marker");
    markers.forEach((m) => m.remove());

    problems.forEach((p) => {
      if (p.lat && p.lon) {
        new maplibregl.Marker({ color: p.score > 0.7 ? "#e74c3c" : "#f39c12" })
          .setLngLat([p.lon, p.lat])
          .setPopup(new maplibregl.Popup().setText(p.title))
          .addTo(map.current!);
      }
    });
  }, [problems]);

  return <div ref={container} style={{ width: "100%", height: "500px" }} />;
}
