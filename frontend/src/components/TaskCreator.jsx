import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import LogViewer from './LogViewer';
import OutputPanel from './OutputPanel';
import './TaskCreator.css';

export default function TaskCreator() {
    const [agents, setAgents] = useState([]);
    const [prompt, setPrompt] = useState('');
    const [strategy, setStrategy] = useState('parallel');
    const [selectedAgentIds, setSelectedAgentIds] = useState([]);
    const [useAll, setUseAll] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [activeTask, setActiveTask] = useState(null);
    const [error, setError] = useState(null);

    const { messages, isConnected, clearMessages } = useWebSocket('/api/ws/logs');

    useEffect(() => {
        apiGet('/agents').then(setAgents).catch(() => { });
    }, []);

    // Poll active task for completion
    useEffect(() => {
        if (!activeTask || activeTask.status === 'completed' || activeTask.status === 'failed') return;

        const interval = setInterval(async () => {
            try {
                const updated = await apiGet(`/tasks/${activeTask.id}`);
                setActiveTask(updated);
                if (updated.status === 'completed' || updated.status === 'failed') {
                    clearInterval(interval);
                }
            } catch { /* ignore */ }
        }, 2000);

        return () => clearInterval(interval);
    }, [activeTask?.id, activeTask?.status]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!prompt.trim()) return;

        setSubmitting(true);
        setError(null);
        clearMessages();
        setActiveTask(null);

        try {
            const body = {
                prompt: prompt.trim(),
                strategy,
                agent_ids: useAll ? null : selectedAgentIds,
            };
            const task = await apiPost('/tasks', body);
            setActiveTask(task);
        } catch (e) {
            setError(e.message);
        } finally {
            setSubmitting(false);
        }
    };

    const toggleAgent = (id) => {
        setSelectedAgentIds(prev =>
            prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
        );
    };

    return (
        <div className="task-creator fade-in">
            <div className="page-header">
                <div>
                    <h1>Task Execution</h1>
                    <p className="page-subtitle">Send prompts to your agent network</p>
                </div>
                <div className="ws-status">
                    <span className={`status-dot ${isConnected ? 'online' : 'offline'}`}></span>
                    <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
                </div>
            </div>

            {error && <div className="error-banner">{error} <button onClick={() => setError(null)}>✕</button></div>}

            <form className="task-form card" onSubmit={handleSubmit}>
                <div className="form-row">
                    <div className="form-group flex-grow">
                        <label>Prompt</label>
                        <textarea
                            value={prompt}
                            onChange={e => setPrompt(e.target.value)}
                            placeholder="Enter your prompt here... Lucy will orchestrate your agents to produce the best response."
                            rows={4}
                            required
                        />
                    </div>
                </div>

                <div className="form-row">
                    <div className="form-group">
                        <label>Strategy</label>
                        <select value={strategy} onChange={e => setStrategy(e.target.value)}>
                            <option value="sequential">Sequential — Chain agents</option>
                            <option value="parallel">Parallel — Fan-out & aggregate</option>
                            <option value="dynamic">Dynamic — Lucy decides</option>
                        </select>
                    </div>

                    <div className="form-group">
                        <label>Agents</label>
                        <div className="agent-selector">
                            <label className="checkbox-label">
                                <input type="checkbox" checked={useAll} onChange={e => setUseAll(e.target.checked)} />
                                <span>Use all active agents</span>
                            </label>
                            {!useAll && (
                                <div className="agent-checkboxes">
                                    {agents.filter(a => a.is_active).map(agent => (
                                        <label key={agent.id} className="checkbox-label">
                                            <input
                                                type="checkbox"
                                                checked={selectedAgentIds.includes(agent.id)}
                                                onChange={() => toggleAgent(agent.id)}
                                            />
                                            <span>{agent.name}</span>
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                <div className="form-actions">
                    <button
                        type="submit"
                        className="btn btn-primary btn-execute"
                        disabled={submitting || !prompt.trim()}
                    >
                        {submitting ? (
                            <><span className="spinner"></span> Sending...</>
                        ) : (
                            <>▶ Execute Task</>
                        )}
                    </button>
                </div>
            </form>

            {/* Real-time Logs */}
            {(messages.length > 0 || activeTask) && (
                <div className="execution-results">
                    <LogViewer messages={messages} />
                    {activeTask && (activeTask.status === 'completed' || activeTask.status === 'failed') && (
                        <OutputPanel task={activeTask} />
                    )}
                    {activeTask && activeTask.status === 'running' && (
                        <div className="running-indicator card">
                            <span className="spinner"></span>
                            <span>Task #{activeTask.id} is running...</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
