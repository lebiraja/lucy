import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../hooks/useApi';
import './AgentAssignment.css';

const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };
const STRATEGY_OPTIONS = [
    { value: 'hierarchical', label: 'Hierarchical', desc: 'CEO-led hierarchical delegation (recommended)' },
    { value: 'parallel', label: 'Parallel', desc: 'Execute tasks in parallel' },
    { value: 'sequential', label: 'Sequential', desc: 'Execute tasks one by one' },
    { value: 'dynamic', label: 'Dynamic', desc: 'Dynamically route based on complexity' },
    { value: 'council', label: 'Council', desc: 'Multiple agents vote on decisions' },
];

export default function AgentAssignment() {
    const [projects, setProjects] = useState([]);
    const [agents, setAgents] = useState([]);
    const [selectedProject, setSelectedProject] = useState(null);
    const [strategy, setStrategy] = useState({
        strategy_type: 'hierarchical',
        priority: 'normal',
        estimated_duration_days: null,
        notes: '',
    });
    const [selectedAgents, setSelectedAgents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [assigning, setAssigning] = useState(false);
    const [assignmentResult, setAssignmentResult] = useState(null);
    const [availability, setAvailability] = useState(null);
    const [notifications, setNotifications] = useState([]);
    const [viewMode, setViewMode] = useState('assign'); // 'assign' | 'auto' | 'availability'

    const loadData = async () => {
        try {
            const [projectsData, agentsData] = await Promise.all([
                apiGet('/projects'),
                apiGet('/agents'),
            ]);
            setProjects(projectsData);
            setAgents(agentsData);
        } catch (e) {
            console.error('Failed to load data:', e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    useEffect(() => {
        if (selectedProject) {
            checkAvailability(selectedProject.id);
            loadNotifications(selectedProject.id);
        }
    }, [selectedProject]);

    const checkAvailability = async (projectId) => {
        try {
            const data = await apiGet(`/projects/${projectId}/availability-check`);
            setAvailability(data);
        } catch (e) {
            console.error('Failed to check availability:', e);
        }
    };

    const loadNotifications = async (projectId) => {
        try {
            const data = await apiGet(`/projects/${projectId}/notifications`);
            setNotifications(data);
        } catch (e) {
            console.error('Failed to load notifications:', e);
        }
    };

    const handleSelectProject = (project) => {
        setSelectedProject(project);
        setAssignmentResult(null);
        setSelectedAgents([]);
        setViewMode('assign');
    };

    const handleStrategyChange = (field, value) => {
        setStrategy(prev => ({ ...prev, [field]: value }));
    };

    const handleAgentToggle = (agentId) => {
        setSelectedAgents(prev =>
            prev.includes(agentId)
                ? prev.filter(id => id !== agentId)
                : [...prev, agentId]
        );
    };

    const handleSelectStrategy = async () => {
        if (!selectedProject) return;
        setAssigning(true);
        try {
            await apiPost(`/projects/${selectedProject.id}/select-strategy`, strategy);
            setAssignmentResult({
                type: 'success',
                message: `Strategy "${strategy.strategy_type}" selected successfully`,
            });
        } catch (e) {
            setAssignmentResult({ type: 'error', message: e.message });
        } finally {
            setAssigning(false);
        }
    };

    const handleManualAssign = async () => {
        if (!selectedProject || selectedAgents.length === 0) return;
        setAssigning(true);
        try {
            const agents = selectedAgents.map(agentId => ({
                agent_id: agentId,
                role_on_project: null,
            }));
            const result = await apiPost(`/projects/${selectedProject.id}/assign-agents`, {
                project_id: selectedProject.id,
                agents,
                strategy: viewMode === 'assign' ? strategy : null,
            });
            setAssignmentResult({
                type: result.warnings?.length > 0 ? 'warning' : 'success',
                message: `Assigned ${result.assigned_agents?.length || 0} agent(s)`,
                result,
            });
            loadData();
            checkAvailability(selectedProject.id);
        } catch (e) {
            setAssignmentResult({ type: 'error', message: e.message });
        } finally {
            setAssigning(false);
        }
    };

    const handleAutoAssign = async () => {
        if (!selectedProject) return;
        setAssigning(true);
        try {
            const result = await apiPost(`/projects/${selectedProject.id}/auto-assign-agents`);
            setAssignmentResult({
                type: result.warnings?.length > 0 ? 'warning' : 'success',
                message: `Auto-assigned ${result.assigned_agents?.length || 0} agent(s)`,
                result,
            });
            loadData();
            checkAvailability(selectedProject.id);
        } catch (e) {
            setAssignmentResult({ type: 'error', message: e.message });
        } finally {
            setAssigning(false);
        }
    };

    const getAvailableAgents = () => {
        return agents.filter(a =>
            a.operational_status === 'active' &&
            a.infrastructure_status === 'online' &&
            (a.state === 'idle' || a.state === 'completed')
        );
    };

    const availableAgents = getAvailableAgents();

    if (loading) {
        return <div className="loading-state"><span className="spinner"></span> Loading...</div>;
    }

    return (
        <div className="agent-assignment fade-in">
            <div className="page-header">
                <div>
                    <h1>Agent Assignment</h1>
                    <p className="page-subtitle">CEO dashboard for strategy selection and agent assignment</p>
                </div>
            </div>

            <div className="assignment-layout">
                {/* Left Panel: Project Selection */}
                <div className="assignment-panel projects-panel">
                    <h3>Select Project</h3>
                    <div className="project-list">
                        {projects.map(p => (
                            <div
                                key={p.id}
                                className={`project-item ${selectedProject?.id === p.id ? 'selected' : ''}`}
                                onClick={() => handleSelectProject(p)}
                            >
                                <div className="project-item-header">
                                    <span className="project-num">#{p.id}</span>
                                    <span className={`status-dot status-${p.status}`}></span>
                                </div>
                                <h4>{p.title}</h4>
                                <p className="project-status">{p.status.replace(/_/g, ' ')}</p>
                                {p.ceo_agent_id && (
                                    <span className="ceo-badge">CEO: #{p.ceo_agent_id}</span>
                                )}
                            </div>
                        ))}
                        {projects.length === 0 && (
                            <p className="empty-text">No projects available</p>
                        )}
                    </div>
                </div>

                {/* Middle Panel: Strategy & Assignment */}
                <div className="assignment-panel main-panel">
                    {!selectedProject ? (
                        <div className="no-selection">
                            <h3>Select a project to configure</h3>
                            <p>Choose a project from the left panel to select strategy and assign agents</p>
                        </div>
                    ) : (
                        <div className="configuration">
                            <h3>Configure: {selectedProject.title}</h3>

                            {/* View Mode Tabs */}
                            <div className="view-mode-tabs">
                                <button
                                    className={viewMode === 'assign' ? 'active' : ''}
                                    onClick={() => setViewMode('assign')}
                                >
                                    Manual Assign
                                </button>
                                <button
                                    className={viewMode === 'auto' ? 'active' : ''}
                                    onClick={() => setViewMode('auto')}
                                >
                                    Auto Assign
                                </button>
                                <button
                                    className={viewMode === 'availability' ? 'active' : ''}
                                    onClick={() => setViewMode('availability')}
                                >
                                    Availability
                                </button>
                            </div>

                            {/* Strategy Selection */}
                            <div className="config-section">
                                <h4>1. Select Strategy</h4>
                                <div className="strategy-grid">
                                    {STRATEGY_OPTIONS.map(opt => (
                                        <div
                                            key={opt.value}
                                            className={`strategy-option ${strategy.strategy_type === opt.value ? 'selected' : ''}`}
                                            onClick={() => handleStrategyChange('strategy_type', opt.value)}
                                        >
                                            <div className="strategy-option-header">
                                                <input
                                                    type="radio"
                                                    name="strategy"
                                                    checked={strategy.strategy_type === opt.value}
                                                    readOnly
                                                />
                                                <span className="strategy-label">{opt.label}</span>
                                            </div>
                                            <p className="strategy-desc">{opt.desc}</p>
                                        </div>
                                    ))}
                                </div>

                                <div className="strategy-options">
                                    <div className="form-group">
                                        <label>Priority</label>
                                        <select
                                            value={strategy.priority}
                                            onChange={e => handleStrategyChange('priority', e.target.value)}
                                        >
                                            <option value="low">Low</option>
                                            <option value="normal">Normal</option>
                                            <option value="high">High</option>
                                            <option value="critical">Critical</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label>Estimated Duration (days)</label>
                                        <input
                                            type="number"
                                            value={strategy.estimated_duration_days || ''}
                                            onChange={e => handleStrategyChange('estimated_duration_days', e.target.value ? parseInt(e.target.value) : null)}
                                            placeholder="e.g. 7"
                                        />
                                    </div>
                                </div>

                                <button
                                    className="btn btn-primary"
                                    onClick={handleSelectStrategy}
                                    disabled={assigning}
                                >
                                    {assigning ? <span className="spinner"></span> : 'Select Strategy'}
                                </button>
                            </div>

                            {/* Agent Assignment */}
                            {viewMode === 'assign' && (
                                <div className="config-section">
                                    <h4>2. Assign Agents Manually</h4>
                                    <p className="section-hint">
                                        Select agents to assign to this project. Only active, online agents are shown.
                                    </p>

                                    <div className="agent-selection">
                                        {availableAgents.map(agent => (
                                            <div
                                                key={agent.id}
                                                className={`agent-checkbox ${selectedAgents.includes(agent.id) ? 'selected' : ''}`}
                                                onClick={() => handleAgentToggle(agent.id)}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={selectedAgents.includes(agent.id)}
                                                    readOnly
                                                />
                                                <div className="agent-info">
                                                    <span className="agent-name">{agent.name}</span>
                                                    <span className="agent-role">{ROLE_LABELS[agent.role] || agent.role}</span>
                                                    <span className="agent-model">{agent.model_name || 'Unknown model'}</span>
                                                </div>
                                            </div>
                                        ))}
                                        {availableAgents.length === 0 && (
                                            <p className="empty-text">No available agents. Add agents in the Agents tab.</p>
                                        )}
                                    </div>

                                    <button
                                        className="btn btn-primary"
                                        onClick={handleManualAssign}
                                        disabled={assigning || selectedAgents.length === 0}
                                    >
                                        {assigning ? <span className="spinner"></span> : `Assign ${selectedAgents.length} Agent(s)`}
                                    </button>
                                </div>
                            )}

                            {/* Auto Assign */}
                            {viewMode === 'auto' && (
                                <div className="config-section">
                                    <h4>Auto Assign Idle Agents</h4>
                                    <p className="section-hint">
                                        Automatically assign idle agents based on project requirements.
                                        Prioritizes warm agents that are online and in IDLE state.
                                    </p>

                                    {availability && (
                                        <div className="availability-summary">
                                            <h5>Current Availability</h5>
                                            <div className="availability-stats">
                                                <div className="stat-item">
                                                    <span className="stat-value">{availability.total_available}</span>
                                                    <span className="stat-label">Available</span>
                                                </div>
                                                <div className="stat-item">
                                                    <span className="stat-value">{availability.total_needed}</span>
                                                    <span className="stat-label">Needed</span>
                                                </div>
                                                <div className={`stat-item ${availability.all_roles_satisfied ? 'success' : 'warning'}`}>
                                                    <span className="stat-value">{availability.all_roles_satisfied ? '✓' : '⚠'}</span>
                                                    <span className="stat-label">
                                                        {availability.all_roles_satisfied ? 'All roles satisfied' : 'Roles missing'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <button
                                        className="btn btn-primary"
                                        onClick={handleAutoAssign}
                                        disabled={assigning}
                                    >
                                        {assigning ? <span className="spinner"></span> : 'Auto Assign Agents'}
                                    </button>
                                </div>
                            )}

                            {/* Availability Check */}
                            {viewMode === 'availability' && availability && (
                                <div className="config-section">
                                    <h4>Agent Availability Check</h4>
                                    
                                    <div className="availability-grid">
                                        {Object.entries(availability.availability || {}).map(([role, data]) => (
                                            <div
                                                key={role}
                                                className={`availability-card ${data.sufficient ? 'sufficient' : 'insufficient'}`}
                                            >
                                                <div className="availability-card-header">
                                                    <span className="role-label">{ROLE_LABELS[role] || role}</span>
                                                    <span className={`status-badge ${data.sufficient ? 'ok' : 'deficit'}`}>
                                                        {data.sufficient ? '✓' : '⚠'}
                                                    </span>
                                                </div>
                                                <div className="availability-numbers">
                                                    <span className="num-available">{data.available}</span>
                                                    <span className="num-separator">/</span>
                                                    <span className="num-needed">{data.needed}</span>
                                                </div>
                                                <p className="availability-status">
                                                    {data.sufficient ? 'Sufficient' : `${data.needed - data.available} more needed`}
                                                </p>
                                            </div>
                                        ))}
                                    </div>

                                    {availability.insufficient_roles?.length > 0 && (
                                        <div className="insufficient-alert">
                                            <strong>Insufficient roles:</strong> {availability.insufficient_roles.join(', ')}
                                        </div>
                                    )}

                                    <h5>Available Agents</h5>
                                    <div className="available-agents-list">
                                        {availability.available_agents?.map(agent => (
                                            <div key={agent.id} className="agent-row">
                                                <span className="agent-name">{agent.name}</span>
                                                <span className="agent-role">{ROLE_LABELS[agent.role] || agent.role}</span>
                                                <span className={`agent-state ${agent.is_warm ? 'warm' : 'cold'}`}>
                                                    {agent.is_warm ? '🔥 Warm' : '❄️ Cold'}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Result Display */}
                            {assignmentResult && (
                                <div className={`assignment-result ${assignmentResult.type}`}>
                                    <h5>{assignmentResult.type === 'success' ? '✓' : assignmentResult.type === 'warning' ? '⚠' : '✕'} {assignmentResult.message}</h5>
                                    {assignmentResult.result && (
                                        <div className="result-details">
                                            {assignmentResult.result.assigned_agents?.length > 0 && (
                                                <div className="result-section">
                                                    <strong>Assigned Agents:</strong>
                                                    <ul>
                                                        {assignmentResult.result.assigned_agents.map((a, i) => (
                                                            <li key={i}>{a.agent_name} ({a.role})</li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                            {assignmentResult.result.unassigned_agents?.length > 0 && (
                                                <div className="result-section">
                                                    <strong>Unassigned:</strong>
                                                    <ul>
                                                        {assignmentResult.result.unassigned_agents.map((a, i) => (
                                                            <li key={i}>
                                                                {a.agent_id ? `Agent #${a.agent_id}` : a.role} - {a.reason}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                            {assignmentResult.result.warnings?.length > 0 && (
                                                <div className="result-section warnings">
                                                    <strong>Warnings:</strong>
                                                    <ul>
                                                        {assignmentResult.result.warnings.map((w, i) => (
                                                            <li key={i}>{w}</li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                    <button className="btn btn-sm btn-ghost" onClick={() => setAssignmentResult(null)}>Dismiss</button>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Right Panel: Notifications */}
                <div className="assignment-panel notifications-panel">
                    <h3>Notifications</h3>
                    <div className="notifications-list">
                        {notifications.map(notif => (
                            <div key={notif.id} className={`notification-item ${notif.priority} ${notif.type}`}>
                                <div className="notification-header">
                                    <span className="notification-type">{notif.type.replace(/_/g, ' ')}</span>
                                    <span className="notification-time">
                                        {new Date(notif.timestamp).toLocaleTimeString()}
                                    </span>
                                </div>
                                <p className="notification-message">
                                    {notif.payload?.message || 'No message'}
                                </p>
                                {notif.payload?.available_agents && (
                                    <div className="notification-agents">
                                        <small>Agents: {notif.payload.available_agents.length}</small>
                                    </div>
                                )}
                            </div>
                        ))}
                        {notifications.length === 0 && (
                            <p className="empty-text">No notifications</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
