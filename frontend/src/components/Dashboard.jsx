import { useState, useEffect } from 'react';
import { apiGet } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import './Dashboard.css';

const getRoleLabel = (role) => {
    if (!role) return 'Unknown';
    const defaults = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };
    return defaults[role] || (role.charAt(0).toUpperCase() + role.slice(1));
};

const getRoleIcon = (role) => {
    const icons = { ceo: '👑', cto: '🏗', manager: '📋', employee: '⚙' };
    return icons[role] || '🤖';
};

const getRoleGradient = (role) => {
    const gradients = {
        ceo: 'linear-gradient(135deg, #f59e0b, #d97706)',
        cto: 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
        manager: 'linear-gradient(135deg, #3b82f6, #2563eb)',
        employee: 'linear-gradient(135deg, #6b7280, #4b5563)',
    };
    return gradients[role] || 'linear-gradient(135deg, #4b5563, #374151)';
};

const STATE_LABELS = {
    idle: 'Idle', assigned: 'Assigned', planning: 'Planning', delegating: 'Delegating',
    executing: 'Executing', waiting: 'Waiting', reporting: 'Reporting',
    completed: 'Done', failed: 'Failed', stopped: 'Stopped',
};
const STATUS_COLORS = ['completed', 'in_progress', 'planning', 'intake', 'monitoring', 'failed'];

export default function Dashboard() {
    const [fleet, setFleet] = useState(null);
    const [projects, setProjects] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedRole, setExpandedRole] = useState(null);
    const { messages, isConnected } = useWebSocket('/api/ws/logs');

    useEffect(() => {
        const load = async () => {
            try {
                const [fleetData, projectsData] = await Promise.all([
                    apiGet('/agents/fleet-summary'),
                    apiGet('/projects'),
                ]);
                setFleet(fleetData);
                setProjects(projectsData);
            } catch {
                // Fallback to basic fleet status if fleet-summary not available
                try {
                    const [fleetData, projectsData] = await Promise.all([
                        apiGet('/agents/fleet-status'),
                        apiGet('/projects'),
                    ]);
                    setFleet({
                        total_agents: fleetData.total_agents,
                        ready_count: fleetData.ready_count,
                        busy_count: fleetData.under_review_count,
                        offline_count: fleetData.offline_count,
                        by_role: fleetData.by_role.map(r => ({ ...r, busy: r.under_review, agents: [] })),
                        workforce_demand: [],
                        insufficient_roles: fleetData.insufficient_roles || [],
                        unassigned_count: 0,
                    });
                    setProjects(projectsData);
                } catch {
                    // Gracefully handle total API failure — show empty state
                    setFleet({
                        total_agents: 0, ready_count: 0, busy_count: 0, offline_count: 0,
                        by_role: [],
                        workforce_demand: [], insufficient_roles: [], unassigned_count: 0,
                    });
                }
            }
            setLoading(false);
        };
        load();
        const interval = setInterval(load, 12000);
        return () => clearInterval(interval);
    }, []);

    const recentLogs = messages.slice(-20);
    const activeProjects = projects.filter(p => !['completed', 'failed', 'on_hold'].includes(p.status));
    const completedProjects = projects.filter(p => p.status === 'completed');

    if (loading || !fleet) {
        return (
            <div className="dashboard fade-in">
                <div className="loading-state"><span className="spinner"></span> Initializing CEO Command Center...</div>
            </div>
        );
    }

    // Calculate workforce demand totals
    const totalDemand = {};
    (fleet.workforce_demand || []).forEach(d => {
        Object.entries(d.required || {}).forEach(([role, count]) => {
            totalDemand[role] = (totalDemand[role] || 0) + count;
        });
    });

    return (
        <div className="dashboard fade-in">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1 className="ceo-title">CEO Command Center</h1>
                    <p className="page-subtitle">Lucy Multi-Agent Orchestrator — Fleet Intelligence</p>
                </div>
                <div className="header-status">
                    <span className={`live-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
                        <span className="live-dot"></span>
                        {isConnected ? 'LIVE' : 'OFFLINE'}
                    </span>
                </div>
            </div>

            {/* Alerts */}
            {fleet.insufficient_roles?.length > 0 && (
                <div className="ceo-alert">
                    <div className="alert-icon">⚠️</div>
                    <div className="alert-body">
                        <strong>Workforce Deficit Detected</strong>
                        <p>Insufficient agents for: <span className="alert-roles">{fleet.insufficient_roles.join(', ').toUpperCase()}</span>. CEO should assign more agents to these roles.</p>
                    </div>
                </div>
            )}

            {/* Stat Cards */}
            <div className="stats-grid">
                <div className="stat-card stat-total">
                    <div className="stat-glow"></div>
                    <div className="stat-content">
                        <span className="stat-number">{fleet.total_agents}</span>
                        <span className="stat-label">Total Fleet</span>
                    </div>
                    <div className="stat-icon-bg">⬡</div>
                </div>
                <div className="stat-card stat-ready">
                    <div className="stat-glow"></div>
                    <div className="stat-content">
                        <span className="stat-number">{fleet.ready_count}</span>
                        <span className="stat-label">Ready</span>
                    </div>
                    <div className="stat-icon-bg">✦</div>
                </div>
                <div className="stat-card stat-busy">
                    <div className="stat-glow"></div>
                    <div className="stat-content">
                        <span className="stat-number">{fleet.busy_count}</span>
                        <span className="stat-label">Executing</span>
                    </div>
                    <div className="stat-icon-bg">⚡</div>
                </div>
                <div className="stat-card stat-offline">
                    <div className="stat-glow"></div>
                    <div className="stat-content">
                        <span className="stat-number">{fleet.offline_count}</span>
                        <span className="stat-label">Offline</span>
                    </div>
                    <div className="stat-icon-bg">◯</div>
                </div>
                <div className="stat-card stat-projects">
                    <div className="stat-glow"></div>
                    <div className="stat-content">
                        <span className="stat-number">{activeProjects.length}</span>
                        <span className="stat-label">Active Projects</span>
                    </div>
                    <div className="stat-icon-bg">▶</div>
                </div>
                {fleet.unassigned_count > 0 && (
                    <div className="stat-card stat-unassigned">
                        <div className="stat-glow"></div>
                        <div className="stat-content">
                            <span className="stat-number">{fleet.unassigned_count}</span>
                            <span className="stat-label">Unassigned</span>
                        </div>
                        <div className="stat-icon-bg">?</div>
                    </div>
                )}
            </div>

            <div className="dashboard-panels">
                {/* Role Hierarchy Panel */}
                <div className="panel card role-panel">
                    <div className="panel-header">
                        <h2>Agent Hierarchy</h2>
                        <span className="panel-badge">{fleet.total_agents} agents</span>
                    </div>
                    <div className="role-hierarchy">
                        {(fleet.by_role || []).map(group => {
                            const maxBar = Math.max(fleet.total_agents, 1);
                            const readyPct = (group.ready / maxBar) * 100;
                            const busyPct = ((group.busy || group.under_review || 0) / maxBar) * 100;
                            const offlinePct = (group.offline / maxBar) * 100;
                            const isExpanded = expandedRole === group.role;
                            const demand = totalDemand[group.role] || 0;
                            const hasDeficit = demand > group.ready;

                            return (
                                <div key={group.role} className={`role-row ${isExpanded ? 'expanded' : ''}`}>
                                    <div className="role-header" onClick={() => setExpandedRole(isExpanded ? null : group.role)}>
                                        <div className="role-info">
                                            <span className="role-icon" style={{ background: getRoleGradient(group.role) }}>
                                                {getRoleIcon(group.role)}
                                            </span>
                                            <div className="role-labels">
                                                <span className="role-name">{getRoleLabel(group.role)}</span>
                                                <span className="role-count">{group.total} agent{group.total !== 1 ? 's' : ''}</span>
                                            </div>
                                        </div>
                                        <div className="role-stats">
                                            {group.ready > 0 && <span className="tag tag-ready">{group.ready} ready</span>}
                                            {(group.busy || group.under_review || 0) > 0 && <span className="tag tag-busy">{group.busy || group.under_review} busy</span>}
                                            {group.offline > 0 && <span className="tag tag-offline">{group.offline} off</span>}
                                            {hasDeficit && <span className="tag tag-deficit pulse">need {demand - group.ready} more</span>}
                                            <span className="expand-arrow">{isExpanded ? '▾' : '▸'}</span>
                                        </div>
                                    </div>
                                    <div className="role-bar-track">
                                        <div className="role-bar ready-bar" style={{ width: `${readyPct}%` }}></div>
                                        <div className="role-bar busy-bar" style={{ width: `${busyPct}%`, left: `${readyPct}%` }}></div>
                                        <div className="role-bar offline-bar" style={{ width: `${offlinePct}%`, left: `${readyPct + busyPct}%` }}></div>
                                    </div>

                                    {/* Expandable agent list */}
                                    {isExpanded && (group.agents || []).length > 0 && (
                                        <div className="role-agents-list">
                                            {group.agents.map(a => (
                                                <div key={a.id} className="agent-mini">
                                                    <span className={`mini-dot ${a.infrastructure_status === 'online' ? 'online' : 'offline'}`}></span>
                                                    <span className="mini-name">{a.name}</span>
                                                    <span className="mini-state">{STATE_LABELS[a.state] || a.state}</span>
                                                    {a.model_name && <span className="mini-model">{a.model_name}</span>}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    {isExpanded && (group.agents || []).length === 0 && (
                                        <div className="role-agents-empty">No {getRoleLabel(group.role).toLowerCase()} agents registered</div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Live Feed */}
                <div className="panel card feed-panel">
                    <div className="panel-header">
                        <h2>Live Activity Feed</h2>
                        <span className={`live-badge ${isConnected ? 'connected' : ''}`}>
                            <span className="live-pulse"></span>
                            LIVE
                        </span>
                    </div>
                    <div className="live-feed">
                        {recentLogs.length === 0 && <p className="text-muted feed-empty">Awaiting system events...</p>}
                        {recentLogs.map((log, i) => (
                            <div key={i} className={`feed-item level-${log.level}`}>
                                <span className="feed-time">{new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                <span className="feed-source">{log.source}</span>
                                <span className="feed-message">{log.message}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Workforce Demand */}
                {(fleet.workforce_demand || []).length > 0 && (
                    <div className="panel card demand-panel">
                        <div className="panel-header">
                            <h2>Workforce Demand</h2>
                            <span className="panel-badge">{fleet.workforce_demand.length} project{fleet.workforce_demand.length !== 1 ? 's' : ''}</span>
                        </div>
                        <div className="demand-list">
                            {fleet.workforce_demand.map(d => (
                                <div key={d.project_id} className="demand-item">
                                    <div className="demand-title">#{d.project_id} — {d.project_title}</div>
                                    <div className="demand-roles">
                                        {Object.entries(d.required || {}).map(([role, count]) => {
                                            const roleGroup = (fleet.by_role || []).find(r => r.role === role);
                                            const available = roleGroup ? roleGroup.ready : 0;
                                            const isShort = available < count;
                                            return (
                                                <div key={role} className={`demand-chip ${isShort ? 'deficit' : 'ok'}`}>
                                                    <span>{ROLE_LABELS[role] || role}</span>
                                                    <span className="demand-nums">{available}/{count}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Recent Projects */}
                <div className="panel card projects-panel">
                    <div className="panel-header">
                        <h2>Projects Overview</h2>
                        <span className="panel-badge">{projects.length} total</span>
                    </div>
                    <div className="project-list">
                        {projects.length === 0 && <p className="text-muted">No projects yet</p>}
                        {projects.map(project => (
                            <div key={project.id} className="project-row">
                                <div className="project-row-info">
                                    <span className="project-id">#{project.id}</span>
                                    <span className="project-title-text">{project.title}</span>
                                </div>
                                <div className="project-row-meta">
                                    <span className={`status-pill status-${project.status}`}>
                                        {project.status.replace(/_/g, ' ')}
                                    </span>
                                    {project.ceo_agent_id
                                        ? <span className="assigned-badge">CEO #{project.ceo_agent_id}</span>
                                        : <span className="awaiting-badge">Awaiting CEO</span>
                                    }
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
