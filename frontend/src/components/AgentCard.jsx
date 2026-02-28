import './AgentCard.css';

export default function AgentCard({ agent, health, onEdit, onDelete, onHealthCheck }) {
    const isOnline = health?.is_online;
    const statusClass = isOnline === true ? 'online' : isOnline === false ? 'offline' : 'unknown';

    return (
        <div className={`agent-card card fade-in ${statusClass}`}>
            <div className="agent-card-header">
                <div className="agent-card-title">
                    <span className={`status-dot ${statusClass}`}></span>
                    <h3>{agent.name}</h3>
                    {agent.is_orchestrator && <span className="badge badge-purple">Orchestrator</span>}
                </div>
                <div className="agent-card-actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => onHealthCheck(agent.id)} title="Health Check">
                        ♥
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => onEdit(agent)} title="Edit">
                        ✎
                    </button>
                    <button className="btn btn-ghost btn-sm danger-hover" onClick={() => onDelete(agent.id)} title="Delete">
                        ✕
                    </button>
                </div>
            </div>

            <div className="agent-card-body">
                <div className="agent-meta">
                    <div className="meta-item">
                        <span className="meta-label">Endpoint</span>
                        <span className="meta-value mono">{agent.endpoint}</span>
                    </div>
                    <div className="meta-item">
                        <span className="meta-label">Model</span>
                        <span className="meta-value">{agent.model_name}</span>
                    </div>
                    <div className="meta-item">
                        <span className="meta-label">Role</span>
                        <span className="meta-value">{agent.role}</span>
                    </div>
                </div>

                <div className="agent-params">
                    <span className="param-chip">T: {agent.temperature}</span>
                    <span className="param-chip">Tokens: {agent.max_tokens}</span>
                    <span className="param-chip">Top-P: {agent.top_p}</span>
                </div>

                {health && (
                    <div className="agent-health-info">
                        {isOnline ? (
                            <span className="badge badge-success">Online · {health.latency_ms}ms</span>
                        ) : (
                            <span className="badge badge-danger">{health.error || 'Offline'}</span>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
