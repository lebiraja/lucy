import { useState, useEffect } from 'react';
import { apiGet } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import './Dashboard.css';

const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Employee' };
const ROLE_COLORS = { ceo: 'badge-gold', cto: 'badge-purple', manager: 'badge-info', employee: 'badge-default' };

export default function Dashboard() {
    const [agents, setAgents] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [healthMap, setHealthMap] = useState({});
    const [loading, setLoading] = useState(true);
    const { messages, isConnected } = useWebSocket('/api/ws/logs');

    useEffect(() => {
        const load = async () => {
            try {
                const [agentsData, tasksData] = await Promise.all([
                    apiGet('/agents'),
                    apiGet('/tasks?limit=10'),
                ]);
                setAgents(agentsData);
                setTasks(tasksData);

                try {
                    const healthData = await apiGet('/agents/health');
                    const map = {};
                    healthData.forEach(h => { map[h.id] = h; });
                    setHealthMap(map);
                } catch { /* health check optional */ }
            } catch { /* ignore on dashboard */ }
            setLoading(false);
        };
        load();
        const interval = setInterval(load, 30000);
        return () => clearInterval(interval);
    }, []);

    const onlineCount = Object.values(healthMap).filter(h => h.is_online).length;
    const totalAgents = agents.length;
    const warmCount = agents.filter(a => a.is_warm).length;
    const activeCount = agents.filter(a => a.operational_status === 'active').length;
    const completedTasks = tasks.filter(t => t.status === 'completed').length;
    const runningTasks = tasks.filter(t => t.status === 'running').length;
    const recentLogs = messages.slice(-15);

    // Group agents by role
    const ceos = agents.filter(a => a.role === 'ceo');
    const ctos = agents.filter(a => a.role === 'cto');
    const managers = agents.filter(a => a.role === 'manager');
    const employees = agents.filter(a => a.role === 'employee');

    if (loading) {
        return (
            <div className="dashboard fade-in">
                <div className="loading-state"><span className="spinner"></span> Loading dashboard...</div>
            </div>
        );
    }

    return (
        <div className="dashboard fade-in">
            <div className="page-header">
                <div>
                    <h1>Dashboard</h1>
                    <p className="page-subtitle">Lucy Multi-Agent Orchestrator — Overview</p>
                </div>
                <div className="ws-status">
                    <span className={`status-dot ${isConnected ? 'online' : 'offline'}`}></span>
                    <span>{isConnected ? 'Live' : 'Disconnected'}</span>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="stats-grid">
                <div className="stat-card card">
                    <div className="stat-icon agents-icon">⬡</div>
                    <div className="stat-info">
                        <span className="stat-value">{totalAgents}</span>
                        <span className="stat-label">Total Agents</span>
                    </div>
                </div>
                <div className="stat-card card">
                    <div className="stat-icon online-icon">✦</div>
                    <div className="stat-info">
                        <span className="stat-value">{onlineCount}</span>
                        <span className="stat-label">Online</span>
                    </div>
                </div>
                <div className="stat-card card">
                    <div className="stat-icon warm-icon">🔥</div>
                    <div className="stat-info">
                        <span className="stat-value">{warmCount}</span>
                        <span className="stat-label">Warm</span>
                    </div>
                </div>
                <div className="stat-card card">
                    <div className="stat-icon running-icon">▶</div>
                    <div className="stat-info">
                        <span className="stat-value">{runningTasks}</span>
                        <span className="stat-label">Running</span>
                    </div>
                </div>
            </div>

            <div className="dashboard-grid">
                {/* Agent Hierarchy */}
                <div className="dashboard-section card">
                    <h2>Agent Hierarchy</h2>
                    <div className="hierarchy-list">
                        {[
                            { label: 'CEO', agents: ceos, color: 'gold' },
                            { label: 'CTO', agents: ctos, color: 'purple' },
                            { label: 'Managers', agents: managers, color: 'blue' },
                            { label: 'Employees', agents: employees, color: 'gray' },
                        ].map(group => (
                            <div key={group.label} className="hierarchy-group">
                                <div className="hierarchy-label">
                                    <span className={`hierarchy-dot dot-${group.color}`}></span>
                                    {group.label} <span className="hierarchy-count">({group.agents.length})</span>
                                </div>
                                {group.agents.map(agent => {
                                    const health = healthMap[agent.id];
                                    return (
                                        <div key={agent.id} className="agent-status-row">
                                            <div className="agent-status-info">
                                                <span className={`status-dot ${health?.is_online ? 'online' : 'offline'}`}></span>
                                                <span className="agent-status-name">{agent.name}</span>
                                                {agent.is_orchestrator && <span className="badge badge-purple" style={{ fontSize: '0.6rem', padding: '1px 5px' }}>Brain</span>}
                                            </div>
                                            <div className="agent-status-meta">
                                                <span className="text-muted">{agent.state}</span>
                                                {health?.is_online && <span className="badge badge-success">{health.latency_ms}ms</span>}
                                            </div>
                                        </div>
                                    );
                                })}
                                {group.agents.length === 0 && <div className="no-agents-hint">No {group.label.toLowerCase()} assigned</div>}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Live Feed */}
                <div className="dashboard-section card">
                    <h2>Live Feed</h2>
                    <div className="live-feed">
                        {recentLogs.length === 0 && <p className="text-muted">Waiting for events...</p>}
                        {recentLogs.map((log, i) => (
                            <div key={i} className={`feed-item level-${log.level}`}>
                                <span className="feed-source">{log.source}</span>
                                <span className="feed-message">{log.message}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent Tasks */}
                <div className="dashboard-section card full-width">
                    <h2>Recent Tasks</h2>
                    <div className="tasks-table">
                        {tasks.length === 0 && <p className="text-muted">No tasks yet</p>}
                        {tasks.map(task => (
                            <div key={task.id} className="task-row">
                                <div className="task-id">#{task.id}</div>
                                <div className="task-prompt">{task.prompt.substring(0, 80)}{task.prompt.length > 80 ? '...' : ''}</div>
                                <span className="badge badge-info">{task.strategy}</span>
                                <span className={`badge ${task.status === 'completed' ? 'badge-success' : task.status === 'running' ? 'badge-warning' : task.status === 'failed' ? 'badge-danger' : 'badge-info'}`}>
                                    {task.status}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
