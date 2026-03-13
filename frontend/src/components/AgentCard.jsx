import './AgentCard.css';

const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };
const ROLE_COLORS = { ceo: 'badge-gold', cto: 'badge-purple', manager: 'badge-info', employee: 'badge-default' };
const STATE_ICONS = {
    idle: '⏸', assigned: '📋', planning: '🧠', delegating: '📤',
    executing: '⚡', waiting: '⏳', reporting: '📊',
    completed: '✓', failed: '✕', stopped: '⬛',
};

export default function AgentCard({ agent, agents, health, onEdit, onDelete, onHealthCheck, onAction, onRetrain }) {
    const infraOnline = agent.infrastructure_status === 'online';
    const statusClass = infraOnline ? 'online' : 'offline';
    const parentAgent = agent.parent_id ? agents.find(a => a.id === agent.parent_id) : null;

    return (
        <div className={`agent-card card fade-in ${statusClass}`}>
            <div className="agent-card-header">
                <div className="agent-card-title">
                    <span className={`status-dot ${statusClass}`}></span>
                    <h3>{agent.name}</h3>
                </div>
                <div className="agent-card-badges">
                    <span className={`badge ${ROLE_COLORS[agent.role] || 'badge-default'}`}>
                        {ROLE_LABELS[agent.role] || agent.role}
                    </span>
                    {agent.is_orchestrator && <span className="badge badge-purple">Brain</span>}
                </div>
            </div>

            <div className="agent-card-body">
                {/* Status Row */}
                <div className="status-row">
                    <div className="status-chip" data-status={agent.operational_status}>
                        {agent.operational_status.toUpperCase()}
                    </div>
                    <div className="state-chip">
                        <span className="state-icon">{STATE_ICONS[agent.state] || '?'}</span>
                        {agent.state}
                    </div>
                    {agent.is_warm && <span className="warm-badge" title="Model loaded, ready">🔥</span>}
                </div>

                {/* Meta */}
                <div className="agent-meta">
                    <div className="meta-item">
                        <span className="meta-label">Endpoint</span>
                        <span className="meta-value mono">{agent.endpoint}</span>
                    </div>
                    {agent.model_name && (
                        <div className="meta-item">
                            <span className="meta-label">Model</span>
                            <span className="meta-value">{agent.model_name}</span>
                        </div>
                    )}
                    {parentAgent && (
                        <div className="meta-item">
                            <span className="meta-label">Reports To</span>
                            <span className="meta-value parent-link">
                                <span className={`mini-role-dot role-${parentAgent.role}`}></span>
                                {parentAgent.name}
                            </span>
                        </div>
                    )}
                    {agent.description && (
                        <div className="meta-item desc-row">
                            <span className="meta-label">Role</span>
                            <span className="meta-value desc-text">{agent.description}</span>
                        </div>
                    )}
                </div>

                {/* Health */}
                {health && (
                    <div className="agent-health-info">
                        {health.is_online ? (
                            <span className="badge badge-success">Online · {health.latency_ms}ms</span>
                        ) : (
                            <span className="badge badge-danger">{health.error || 'Offline'}</span>
                        )}
                    </div>
                )}
            </div>

            {/* Actions */}
            <div className="agent-card-footer">
                <button className="btn btn-ghost btn-sm" onClick={() => onHealthCheck(agent.id)} title="Health Check">♥</button>
                {onRetrain && (
                    <button className="btn btn-ghost btn-sm retrain-btn" onClick={() => onRetrain(agent)} title="CEO: Retrain & Assign Role">🔄</button>
                )}
                {agent.operational_status === 'active' && (
                    <button className="btn btn-ghost btn-sm" onClick={() => onAction(agent.id, 'pause')} title="Pause">⏸</button>
                )}
                {agent.operational_status === 'paused' && (
                    <button className="btn btn-ghost btn-sm" onClick={() => onAction(agent.id, 'resume')} title="Resume">▶</button>
                )}
                {(agent.operational_status === 'active' || agent.operational_status === 'paused') && (
                    <button className="btn btn-ghost btn-sm" onClick={() => onAction(agent.id, 'stop')} title="Stop">⬛</button>
                )}
                <div className="card-spacer"></div>
                <button className="btn btn-ghost btn-sm" onClick={() => onEdit(agent)} title="Edit">✎</button>
                <button className="btn btn-ghost btn-sm danger-hover" onClick={() => onDelete(agent.id)} title="Delete">✕</button>
            </div>
        </div>
    );
}
