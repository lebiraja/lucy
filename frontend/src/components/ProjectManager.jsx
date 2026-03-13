import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import TaskChat from './TaskChat';
import './ProjectManager.css';

const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };
const STATUS_STEPS = ['intake', 'planning', 'planning_review', 'technical_strategy', 'in_progress', 'monitoring', 'completed'];
const STEP_LABELS = { intake: 'Intake', planning: 'Plan', planning_review: 'Review', technical_strategy: 'Design', in_progress: 'Build', monitoring: 'Monitor', completed: 'Done' };

export default function ProjectManager() {
    const [projects, setProjects] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ title: '', client_requirements: '' });
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [expandedProject, setExpandedProject] = useState(null);
    const [planningData, setPlanningData] = useState({});
    const [projectTasks, setProjectTasks] = useState({});
    const [projectMessages, setProjectMessages] = useState({});
    const [projectViewMode, setProjectViewMode] = useState('logs');
    const [fleetSummary, setFleetSummary] = useState(null);
    const [chatTask, setChatTask] = useState(null); // { projectId, taskId }
    const { messages: wsMessages, isConnected: wsConnected } = useWebSocket('/api/ws/logs');

    const loadProjects = async () => {
        try {
            const [data, fleet] = await Promise.all([
                apiGet('/projects'),
                apiGet('/agents/fleet-summary').catch(() => null),
            ]);
            setProjects(data);
            setFleetSummary(fleet);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadProjects(); }, []);

    const loadPlanning = async (projectId) => {
        try {
            const sessions = await apiGet(`/projects/${projectId}/planning`);
            setPlanningData(prev => ({ ...prev, [projectId]: sessions }));
        } catch { /* ignore */ }
    };

    const loadProjectTasks = async (projectId) => {
        try {
            const tasks = await apiGet(`/projects/${projectId}/tasks`);
            setProjectTasks(prev => ({ ...prev, [projectId]: tasks }));
        } catch { /* ignore */ }
    };

    const loadProjectMessages = async (projectId) => {
        try {
            const messages = await apiGet(`/projects/${projectId}/messages`);
            setProjectMessages(prev => ({ ...prev, [projectId]: messages }));
        } catch { /* ignore */ }
    };

    const toggleExpand = (projectId) => {
        if (expandedProject === projectId) {
            setExpandedProject(null);
        } else {
            setExpandedProject(projectId);
            if (!planningData[projectId]) {
                loadPlanning(projectId);
            }
            if (!projectTasks[projectId]) {
                loadProjectTasks(projectId);
            }
            if (!projectMessages[projectId]) {
                loadProjectMessages(projectId);
            }
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSubmitting(true);
        setError(null);
        try {
            await apiPost('/projects', form);
            setShowForm(false);
            setForm({ title: '', client_requirements: '' });
            await loadProjects();
        } catch (e) {
            setError(e.message);
        } finally {
            setSubmitting(false);
        }
    };

    const handleAction = async (id, action) => {
        try {
            await apiPost(`/projects/${id}/${action}`);
            await loadProjects();
        } catch (e) {
            setError(e.message);
        }
    };

    const getAvailableCount = (role) => {
        if (!fleetSummary) return '?';
        const r = (fleetSummary.by_role || []).find(g => g.role === role);
        return r ? r.ready : 0;
    };

    if (loading) return <div className="loading-state"><span className="spinner"></span> Loading projects...</div>;

    return (
        <div className="project-manager fade-in">
            <div className="page-header">
                <div>
                    <h1>Client Projects</h1>
                    <p className="page-subtitle">Orchestrate complex projects through the hierarchical agency</p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ New Project</button>
            </div>

            {error && <div className="error-banner">{error} <button onClick={() => setError(null)}>✕</button></div>}

            {showForm && (
                <div className="form-overlay" onClick={() => setShowForm(false)}>
                    <form className="project-form card" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
                        <h2>Intake New Project</h2>
                        <div className="form-group">
                            <label>Project Title</label>
                            <input
                                value={form.title}
                                onChange={e => setForm({ ...form, title: e.target.value })}
                                placeholder="e.g. NextGen E-Commerce Platform"
                                required
                            />
                        </div>
                        <div className="form-group">
                            <label>Client Requirements (Scope)</label>
                            <textarea
                                value={form.client_requirements}
                                onChange={e => setForm({ ...form, client_requirements: e.target.value })}
                                placeholder="Describe what the system needs to do..."
                                rows={5}
                                required
                            />
                        </div>
                        <div className="form-actions">
                            <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
                            <button type="submit" className="btn btn-primary" disabled={submitting}>
                                {submitting ? <span className="spinner"></span> : 'Submit to CEO'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="projects-grid">
                {projects.map(p => {
                    const currentStep = STATUS_STEPS.indexOf(p.status);
                    const isExpanded = expandedProject === p.id;
                    const sessions = planningData[p.id] || [];

                    return (
                        <div key={p.id} className={`project-card card ${isExpanded ? 'expanded' : ''}`}>
                            <div className="project-header" onClick={() => toggleExpand(p.id)}>
                                <div className="project-header-left">
                                    <span className="project-num">#{p.id}</span>
                                    <h3>{p.title}</h3>
                                </div>
                                <span className={`status-pill status-${p.status}`}>
                                    {p.status.replace(/_/g, ' ').toUpperCase()}
                                </span>
                            </div>

                            <div className="project-body">
                                <p className="reqs-preview">{p.client_requirements.substring(0, 120)}{p.client_requirements.length > 120 ? '...' : ''}</p>
                                {p.status === 'planning' && (!projectTasks[p.id] || projectTasks[p.id].length === 0) && (
                                    <p className="project-hint">CEO is reviewing requirements and assigning agents; planning stage in progress.</p>
                                )}
                                {p.status === 'planning' && (projectTasks[p.id] || []).length > 0 && (
                                    <p className="project-hint">Active tasks have started: progress is being generated. Watch live logs/chat below.</p>
                                )}
                                {(p.status === 'intake' || p.status === 'planning') && (
                                    <p className="project-hint">Estimated start: within the next few minutes based on agent availability.</p>
                                )}

                                {/* Workflow Steps */}
                                <div className="workflow-track">
                                    {STATUS_STEPS.slice(0, -1).map((step, i) => {
                                        const isDone = i < currentStep;
                                        const isCurrent = i === currentStep;
                                        return (
                                            <div key={step} className="wf-step-container">
                                                <div className={`wf-dot ${isDone ? 'done' : isCurrent ? 'current' : ''}`}>
                                                    {isDone ? '✓' : ''}
                                                </div>
                                                <span className={`wf-label ${isDone ? 'done' : isCurrent ? 'current' : ''}`}>
                                                    {STEP_LABELS[step]}
                                                </span>
                                                {i < STATUS_STEPS.length - 2 && <div className={`wf-line ${isDone ? 'done' : ''}`}></div>}
                                            </div>
                                        );
                                    })}
                                </div>

                                {/* Required agents */}
                                {p.required_agents && (
                                    <div className="required-agents">
                                        <span className="ra-label">Workforce:</span>
                                        {Object.entries(p.required_agents).map(([role, count]) => {
                                            const avail = getAvailableCount(role);
                                            const isShort = avail < count;
                                            return (
                                                <span key={role} className={`ra-chip ${isShort ? 'deficit' : 'ok'}`}>
                                                    {ROLE_LABELS[role] || role}: {avail}/{count}
                                                </span>
                                            );
                                        })}
                                    </div>
                                )}

                                <div className="live-updates">
                                    <div className="live-filter-row">
                                        <h5>Live activity (project)</h5>
                                        <div className="log-chat-toggle">
                                            <button className={projectViewMode === 'logs' ? 'active' : ''} onClick={() => setProjectViewMode('logs')}>Logs</button>
                                            <button className={projectViewMode === 'chat' ? 'active' : ''} onClick={() => setProjectViewMode('chat')}>Chat</button>
                                        </div>
                                    </div>

                                    {projectViewMode === 'logs' ? (
                                        (() => {
                                            const taskIds = (projectTasks[p.id] || []).map(t => t.id);
                                            const filtered = wsMessages
                                                .map(msg => {
                                                    try { return JSON.parse(msg); } catch { return null; }
                                                })
                                                .filter(obj => obj !== null && (!obj.task_id || taskIds.includes(obj.task_id)));
                                            if (filtered.length === 0) {
                                                return <p className="text-muted">No live logs yet.</p>;
                                            }
                                            return filtered.slice(-10).map((obj, idx) => (
                                                <div key={idx} className="live-entry">
                                                    <span className="live-time">{obj.timestamp?.split('T')[1]?.replace('Z', '') || ''}</span>
                                                    <span className="live-source">{obj.source}</span>
                                                    <span className="live-msg">{obj.message}</span>
                                                    <span className="live-task">{obj.task_id ? `Task ${obj.task_id}` : ''}</span>
                                                </div>
                                            ));
                                        })()
                                    ) : (
                                        <div className="chat-list">
                                            {(projectMessages[p.id] || []).length === 0 && <p className="text-muted">No agent conversation yet.</p>}
                                            {(projectMessages[p.id] || []).map(msg => (
                                                <div key={msg.id} className="chat-entry">
                                                    <span className="chat-meta">{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''} • {msg.source || 'agent'}</span>
                                                    <p className="chat-text">{typeof msg.payload === 'object' ? JSON.stringify(msg.payload) : msg.payload}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Expanded: Planning Sessions */}
                            {isExpanded && (
                                <div className="project-expanded">
                                    <div className="expanded-section">
                                        <h4>Level 0.5 Planning Sessions</h4>
                                        {sessions.length === 0 && <p className="text-muted no-sessions">No planning sessions yet</p>}
                                        {sessions.map(s => (
                                            <div key={s.id} className="planning-card">
                                                <div className="planning-header">
                                                    <span className={`badge badge-${s.status === 'completed' ? 'success' : s.status === 'rejected' ? 'danger' : 'info'}`}>
                                                        {s.status.toUpperCase()}
                                                    </span>
                                                    <span className="planning-date">{new Date(s.created_at).toLocaleDateString()}</span>
                                                </div>
                                                {s.architecture && (
                                                    <div className="planning-detail">
                                                        <span className="pd-label">Architecture</span>
                                                        <p>{typeof s.architecture === 'string' ? s.architecture : JSON.stringify(s.architecture).substring(0, 200)}</p>
                                                    </div>
                                                )}
                                                {s.workforce_estimate && (
                                                    <div className="planning-detail">
                                                        <span className="pd-label">Workforce Estimate</span>
                                                        <div className="wf-estimate-chips">
                                                            {Object.entries(s.workforce_estimate).map(([role, count]) => (
                                                                <span key={role} className="wfe-chip">{ROLE_LABELS[role] || role}: {count}</span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {s.risk_analysis && (
                                                    <div className="planning-detail">
                                                        <span className="pd-label">Risks</span>
                                                        <p className="risk-text">{Array.isArray(s.risk_analysis) ? s.risk_analysis.join(' · ') : JSON.stringify(s.risk_analysis).substring(0, 150)}</p>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div className="expanded-section">
                                        <h4>Orchestration Tasks / Active Work</h4>
                                        {(projectTasks[p.id] || []).length === 0 && <p className="text-muted no-sessions">No tasks yet for this project.</p>}
                                        {(projectTasks[p.id] || []).map(task => (
                                            <div key={task.id} className="h-task-card">
                                                <div className="h-task-title">
                                                    <div className="h-task-title-left">
                                                        <strong>Task #{task.id}</strong>
                                                        <span className={`status-pill status-${task.status}`}>{task.status.toUpperCase()}</span>
                                                        <span className="h-task-strategy">{task.strategy.toUpperCase()}</span>
                                                    </div>
                                                    <button
                                                        className="btn-chat-task"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setChatTask({ projectId: p.id, taskId: task.id });
                                                        }}
                                                        title="Open task chat"
                                                    >
                                                        💬 Chat
                                                    </button>
                                                </div>
                                                <p className="task-prompt">{task.prompt}</p>
                                                {task.final_output && (
                                                    <div className="task-output">
                                                        <strong>Final output:</strong>
                                                        <pre>{task.final_output}</pre>
                                                    </div>
                                                )}
                                                <div className="task-steps">
                                                    <h5>Steps</h5>
                                                    {(task.steps || []).length === 0 && <p className="text-muted">No steps recorded yet.</p>}
                                                    {(task.steps || []).map(step => (
                                                        <div key={step.id} className="task-step-row">
                                                            <div className="task-step-meta">
                                                                <span><strong>{step.step_label || 'unnamed'}</strong></span>
                                                                <span>{step.agent_name || 'Unknown'} ({step.agent_role || 'unknown'})</span>
                                                                <span>{step.status.toUpperCase()}</span>
                                                            </div>
                                                            <p className="task-step-msg">{step.response || 'No response yet.'}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="expanded-section">
                                        <h4>Recent Agent Messages (History/Reasoning)</h4>
                                        {(projectMessages[p.id] || []).length === 0 && <p className="text-muted no-sessions">No agent messages yet.</p>}
                                        {(projectMessages[p.id] || []).map(msg => {
                                            const payload = msg.payload;
                                            const notice = payload && typeof payload === 'object' && payload.notification_type ? payload : null;
                                            const contentText = notice
                                                ? notice.message || JSON.stringify(notice)
                                                : (typeof payload === 'string' ? payload : JSON.stringify(payload));

                                            return (
                                                <div key={msg.id} className={`message-row ${notice ? 'message-notice' : ''}`}>
                                                    <span className="msg-time">{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}</span>
                                                    <span className="msg-source">[{msg.source||'system'}]</span>
                                                    <span className="msg-level">{msg.level}</span>
                                                    <p className="msg-content">{contentText}</p>
                                                    {notice && <small className="msg-notice-type">{notice.notification_type.replace('_', ' ')}</small>}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            <div className="project-footer">
                                <div className="ceo-assignment">
                                    {p.ceo_agent_id
                                        ? <span className="assigned-tag">CEO #{p.ceo_agent_id}</span>
                                        : <span className="awaiting-tag">Awaiting CEO</span>
                                    }
                                </div>
                                <div className="project-actions">
                                    {p.status === 'intake' && (
                                        <button className="btn btn-sm btn-primary" onClick={() => handleAction(p.id, 'start-planning')}>Start Planning</button>
                                    )}
                                    <button className="btn btn-sm btn-ghost" onClick={() => toggleExpand(p.id)}>
                                        {isExpanded ? 'Collapse' : 'Details'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}

                {projects.length === 0 && (
                    <div className="empty-state">
                        <p>No active projects.</p>
                        <p className="text-muted">Start by creating a new client project.</p>
                    </div>
                )}
            </div>

            {/* Task Chat Modal */}
            {chatTask && (
                <div className="chat-modal-overlay" onClick={() => setChatTask(null)}>
                    <div className="chat-modal" onClick={e => e.stopPropagation()}>
                        <TaskChat
                            projectId={chatTask.projectId}
                            taskId={chatTask.taskId}
                            onClose={() => setChatTask(null)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
