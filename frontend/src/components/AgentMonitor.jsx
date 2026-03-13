import { useState, useEffect } from 'react';
import { apiGet } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import './AgentMonitor.css';

export default function AgentMonitor() {
    const [projects, setProjects] = useState([]);
    const [activeProjectId, setActiveProjectId] = useState(null);
    const [projectMessages, setProjectMessages] = useState([]);
    const [projectTasks, setProjectTasks] = useState([]);
    const [projectStatus, setProjectStatus] = useState(null);
    const { messages: globalLogs, isConnected } = useWebSocket('/api/ws/logs');

    const loadProjects = async () => {
        try {
            const data = await apiGet('/projects');
            setProjects(data);
            if (!activeProjectId && data.length > 0) {
                setActiveProjectId(data[0].id);
            }
        } catch (e) {
            console.error('Project load failed', e);
        }
    };

    const loadProjectData = async (projectId) => {
        if (!projectId) return;

        try {
            const [tasks, messages, status] = await Promise.all([
                apiGet(`/projects/${projectId}/tasks`).catch(() => []),
                apiGet(`/projects/${projectId}/messages`).catch(() => []),
                apiGet(`/projects/${projectId}/status`).catch(() => null),
            ]);
            setProjectTasks(tasks);
            setProjectMessages(messages);
            setProjectStatus(status);
        } catch (e) {
            console.error('Project detail load failed', e);
        }
    };

    useEffect(() => {
        loadProjects();
        const interval = setInterval(loadProjects, 12000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (activeProjectId) {
            loadProjectData(activeProjectId);
            const interval = setInterval(() => loadProjectData(activeProjectId), 4000);
            return () => clearInterval(interval);
        }
    }, [activeProjectId]);

    return (
        <div className="agent-monitor">
            <div className="monitor-header">
                <h1>CEO Live Monitoring</h1>
                <p>Real-time feed of project status, tasks, and agent conversation</p>
                <div className={`ws-status ${isConnected ? 'online' : 'offline'}`}>
                    {isConnected ? 'Live Connected' : 'Disconnected'}
                </div>
            </div>

            <div className="monitor-body">
                <aside className="monitor-sidebar">
                    <h3>Project Selector</h3>
                    {projects.length === 0 && <p>No projects yet</p>}
                    {projects.map(p => (
                        <button
                            key={p.id}
                            className={`project-btn ${activeProjectId === p.id ? 'active' : ''}`}
                            onClick={() => setActiveProjectId(p.id)}
                        >
                            {p.title} ({p.status})
                        </button>
                    ))}
                </aside>

                <main className="monitor-main">
                    <section className="monitor-status-card">
                        <h3>Project Status Summary</h3>
                        {projectStatus ? (
                            <ul>
                                <li><strong>Status:</strong> {projectStatus.status}</li>
                                <li><strong>Progress:</strong> {projectStatus.progress_percent || 0}%</li>
                                <li><strong>Modules:</strong> {projectStatus.completed_modules}/{projectStatus.total_modules}</li>
                                <li><strong>CEO:</strong> {projectStatus.ceo_agent_id || '-'} </li>
                                {projectStatus.required_agents && (
                                    <li><strong>Required:</strong> {JSON.stringify(projectStatus.required_agents)}</li>
                                )}
                                <li><strong>Deadline:</strong> {projectStatus.deadline || 'N/A'}</li>
                            </ul>
                        ) : (<p>Loading status…</p>)}
                    </section>

                    <section className="monitor-panel">
                        <div className="monitor-panel-col">
                            <h3>Task Execution & Log Stream</h3>
                            {projectTasks.length === 0 && <p>No tasks for this project yet.</p>}
                            {projectTasks.map(task => (
                                <div key={task.id} className="task-card">
                                    <div className="task-card-head">
                                        <span>Task #{task.id}</span>
                                        <span className={`badge badge-${task.status}`} >{task.status}</span>
                                        <span>{task.strategy}</span>
                                    </div>
                                    <p>{task.prompt}</p>
                                    <div className="task-step-list">
                                        <h5>Steps</h5>
                                        {(task.steps || []).map(step => (
                                            <div key={step.id} className="task-step-item">
                                                <div className="task-step-meta">
                                                    <span>{step.step_label || 'step'}</span>
                                                    <span>{step.agent_name || 'unknown'} / {step.agent_role || 'unknown'}</span>
                                                    <span>{step.status}</span>
                                                </div>
                                                <p>{step.response || '...'}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="monitor-panel-col">
                            <h3>Agent Chat (Live Conversation)</h3>
                            {projectMessages.length === 0 && <p>No agent chat messages for project yet.</p>}
                            {projectMessages.map(msg => {
                                const payload = msg.payload;
                                const notice = payload && typeof payload === 'object' && payload.notification_type ? payload : null;
                                const text = notice
                                    ? notice.message || JSON.stringify(notice)
                                    : (typeof payload === 'string' ? payload : JSON.stringify(payload));

                                return (
                                    <div key={msg.id} className={`chat-entry ${notice ? 'chat-notice' : ''}`}>
                                        <div className="chat-meta">
                                            <span className="chat-source">{notice ? notice.notification_type : (msg.message_type || msg.source || 'agent')}</span>
                                            <span>{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '-'}</span>
                                        </div>
                                        <div className="chat-content">{text}</div>
                                    </div>
                                );
                            })}
                        </div>
                    </section>

                    <section className="monitor-global-logs">
                        <h3>Global Activity Feed</h3>
                        {globalLogs.slice(-50).map((entry, i) => {
                            let obj = {};
                            try { obj = JSON.parse(entry); } catch { obj.message = entry; }
                            return (
                                <div key={i} className="global-log-entry">
                                    <span>{obj.timestamp?.split('T')[1]?.replace('Z','') || ''}</span>
                                    <span>[{obj.source}]</span>
                                    <span>{obj.message}</span>
                                    <span className="log-task">{obj.task_id ? `Task ${obj.task_id}` : ''}</span>
                                </div>
                            );
                        })}
                    </section>
                </main>
            </div>
        </div>
    );
}
