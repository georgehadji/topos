import GraphExplorer from "./GraphExplorer";
import ReviewPage from "./ReviewPage";
import { Routes, Route, Link } from "react-router-dom";
import ProblemList from "./ProblemList";
import ProblemMap from "./ProblemMap";
import { searchProblems, type ProblemSummary } from "./api";
import { useState, useEffect } from "react";

function Home() {
  const [problems, setProblems] = useState<ProblemSummary[]>([]);

  useEffect(() => {
    searchProblems("").then((r) => setProblems(r.results)).catch(console.error);
  }, []);

  return (
    <div>
      <h1>Topos — Α΄ Θεσσαλονίκης</h1>
      <p style={{ color: "#666" }}>
        Constituency problem intelligence. Tracking citizen-affecting
        mentions from Greek public-sector sources.
      </p>

      <h2>Ranked mentions</h2>
      <ProblemList />

      <h2>Map</h2>
      <ProblemMap
        problems={problems
          .filter((p) => p.lat && p.lon)
          .map((p) => ({
            title: p.title,
            lat: p.lat!,
            lon: p.lon!,
            score: p.score,
          }))}
      />
    </div>
  );
}

export default function App() {
  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "1rem" }}>
      <nav style={{ marginBottom: "1rem", display: "flex", gap: "1rem" }}>
        <Link to="/">Home</Link>
        <Link to="/review">Review</Link>
        <Link to="/graph">Graph</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/graph" element={<GraphExplorer />} />
      </Routes>
    </div>
  );
}
