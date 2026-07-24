import { useRef, useEffect, useState } from "react";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface GraphNode {
  id: string;
  type: string;
  label: string;
  score: number | null;
}

interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface Position {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

function forceSimulation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number
): (Position & { color: string; radius: number })[] {
  const positions: (Position & { color: string; radius: number })[] = nodes.map((n) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: 0,
    vy: 0,
    color: n.type === "problem" ? "#e74c3c" : n.type === "authority" ? "#3498db" : "#95a5a6",
    radius: n.type === "problem" ? 10 : 6,
  }));

  const nodeIndex = new Map(nodes.map((n, i) => [n.id, i]));
  const edgeList = edges
    .map((e) => ({
      source: nodeIndex.get(e.source),
      target: nodeIndex.get(e.target),
    }))
    .filter((e) => e.source !== undefined && e.target !== undefined) as {
    source: number;
    target: number;
  }[];

  for (let iter = 0; iter < 200; iter++) {
    // Repulsion between all nodes
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[j].x - positions[i].x || 0.1;
        const dy = positions[j].y - positions[i].y || 0.1;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const force = 300 / (dist * dist + 1);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        positions[i].vx -= fx;
        positions[i].vy -= fy;
        positions[j].vx += fx;
        positions[j].vy += fy;
      }
    }

    // Attraction along edges
    for (const e of edgeList) {
      const dx = positions[e.target].x - positions[e.source].x;
      const dy = positions[e.target].y - positions[e.source].y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist - 80) * 0.01;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      positions[e.source].vx += fx;
      positions[e.source].vy += fy;
      positions[e.target].vx -= fx;
      positions[e.target].vy -= fy;
    }

    // Center gravity
    for (const p of positions) {
      p.vx += (width / 2 - p.x) * 0.001;
      p.vy += (height / 2 - p.y) * 0.001;
    }

    // Apply velocity + damping
    for (const p of positions) {
      p.vx *= 0.9;
      p.vy *= 0.9;
      p.x += p.vx;
      p.y += p.vy;
      p.x = Math.max(10, Math.min(width - 10, p.x));
      p.y = Math.max(10, Math.min(height - 10, p.y));
    }
  }

  return positions;
}

export default function GraphExplorer() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/graph/problems?depth=1`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    const svg = svgRef.current;
    svg.innerHTML = "";

    const width = 800;
    const height = 500;
    const positions = forceSimulation(data.nodes, data.edges, width, height);

    const nodeIndex = new Map(data.nodes.map((n, i) => [n.id, i]));

    // Draw edges
    for (const edge of data.edges) {
      const si = nodeIndex.get(edge.source);
      const ti = nodeIndex.get(edge.target);
      if (si === undefined || ti === undefined) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(positions[si].x));
      line.setAttribute("y1", String(positions[si].y));
      line.setAttribute("x2", String(positions[ti].x));
      line.setAttribute("y2", String(positions[ti].y));
      line.setAttribute("stroke", "#ccc");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);
    }

    // Draw nodes
    for (let i = 0; i < data.nodes.length; i++) {
      const p = positions[i];
      const node = data.nodes[i];
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("transform", `translate(${p.x},${p.y})`);
      g.setAttribute("cursor", "pointer");

      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", String(p.radius));
      circle.setAttribute("fill", p.color);
      g.appendChild(circle);

      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = node.label;
      g.appendChild(title);

      svg.appendChild(g);
    }
  }, [data]);

  if (loading) return <p>Loading graph...</p>;
  if (!data || data.nodes.length === 0) return <p>No graph data available.</p>;

  return (
    <div>
      <h1>Knowledge Graph</h1>
      <p style={{ color: "#666" }}>
        {data.nodes.length} nodes · {data.edges.length} edges
      </p>
      <svg
        ref={svgRef}
        viewBox={`0 0 800 500`}
        style={{ width: "100%", maxWidth: "800px", border: "1px solid #ddd" }}
      />
      <div style={{ marginTop: "0.5rem", display: "flex", gap: "1rem", fontSize: "0.85rem" }}>
        <span><span style={{ color: "#e74c3c" }}>●</span> Problem</span>
        <span><span style={{ color: "#3498db" }}>●</span> Authority</span>
        <span><span style={{ color: "#95a5a6" }}>●</span> Other</span>
      </div>
    </div>
  );
}
