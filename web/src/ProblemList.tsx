import { useState, useEffect } from "react";
import { searchProblems, type ProblemSummary } from "./api";

export default function ProblemList() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ProblemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchProblems = async () => {
      setLoading(true);
      try {
        const resp = await searchProblems(query);
        setResults(resp.results);
        setTotal(resp.total);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchProblems();
  }, [query]);

  return (
    <div>
      <div style={{ marginBottom: "1rem" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search problems..."
          style={{
            width: "100%",
            padding: "0.5rem",
            fontSize: "1rem",
            boxSizing: "border-box",
          }}
        />
      </div>

      {loading && <p>Loading...</p>}

      <p style={{ color: "#666", marginBottom: "1rem" }}>
        {total} mention{total !== 1 ? "s" : ""} found
        <span style={{ marginLeft: "1rem", fontSize: "0.8rem", fontStyle: "italic" }}>
          labelled "mentions" until entity resolution ships (Phase 2)
        </span>
      </p>

      <ul style={{ listStyle: "none", padding: 0 }}>
        {results.map((p) => (
          <li
            key={p.problem_id}
            style={{
              padding: "0.75rem",
              marginBottom: "0.5rem",
              border: "1px solid #ddd",
              borderRadius: "4px",
            }}
          >
            <strong>{p.title}</strong>
            <span style={{ marginLeft: "0.5rem", color: "#888" }}>
              ({p.category})
            </span>
            <div style={{ fontSize: "0.9rem", color: "#555", marginTop: "0.25rem" }}>
              Score: {(p.score * 100).toFixed(0)}%
              {p.lat && p.lon ? " · Geocoded" : " · No location"}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
