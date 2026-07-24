import { useState, useEffect } from "react";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface ReviewTask {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  priority: number;
  claimed_by: string | null;
  claimed_until: string | null;
}

export default function ReviewPage() {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/review/tasks`)
      .then((r) => r.json())
      .then((data) => {
        setTasks(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const handleClaim = async (taskId: string) => {
    await fetch(`${API}/api/review/tasks/${taskId}/claim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: "reviewer" }),
    });
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId ? { ...t, claimed_by: "reviewer" } : t
      )
    );
  };

  const handleResolve = async (taskId: string, approve: boolean) => {
    await fetch(`${API}/api/review/tasks/${taskId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution: { approved: approve } }),
    });
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  };

  if (loading) return <p>Loading review queue...</p>;

  return (
    <div>
      <h1>Review Queue</h1>
      <p style={{ color: "#666" }}>
        {tasks.length} pending task{tasks.length !== 1 ? "s" : ""}
      </p>

      {tasks.length === 0 && <p>No pending reviews. All clear!</p>}

      {tasks.map((task) => (
        <div
          key={task.id}
          style={{
            padding: "1rem",
            marginBottom: "0.75rem",
            border: "1px solid #ddd",
            borderRadius: "4px",
          }}
        >
          <div style={{ fontWeight: 600 }}>{task.kind}</div>
          <pre style={{ fontSize: "0.85rem", color: "#555", whiteSpace: "pre-wrap" }}>
            {JSON.stringify(task.payload, null, 2)}
          </pre>
          <div style={{ fontSize: "0.85rem", color: "#888" }}>
            Priority: {task.priority}
            {task.claimed_by && ` · Claimed by: ${task.claimed_by}`}
          </div>
          <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem" }}>
            {!task.claimed_by && (
              <button onClick={() => handleClaim(task.id)} style={btnStyle}>
                Claim
              </button>
            )}
            {task.claimed_by && (
              <>
                <button
                  onClick={() => handleResolve(task.id, true)}
                  style={{ ...btnStyle, background: "#27ae60", color: "#fff" }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handleResolve(task.id, false)}
                  style={{ ...btnStyle, background: "#e74c3c", color: "#fff" }}
                >
                  Reject
                </button>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "0.4rem 0.8rem",
  border: "none",
  borderRadius: "3px",
  cursor: "pointer",
  fontSize: "0.85rem",
};
