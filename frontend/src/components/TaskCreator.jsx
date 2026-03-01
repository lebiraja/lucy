import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import { useSSE } from '../hooks/useSSE';
import LogViewer from './LogViewer';
import OutputPanel from './OutputPanel';
import './TaskCreator.css';

export default function TaskCreator() {
    const [agents, setAgents] = useState([]);
    const [prompt, setPrompt] = useState('');
    const [strategy, setStrategy] = useState('council');
    const [selectedAgentIds, setSelectedAgentIds] = useState([]);
    const [useAll, setUseAll] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [activeTask, setActiveTask] = useState(null);
    const [sseUrl, setSseUrl] = useState(null);
    const [error, setError] = useState(null);

    const { messages, isConnected, clearMessages } = useWebSocket('/api/ws/logs');
    const { isDone: sseDone } = useSSE(sseUrl);

    useEffect(() => {
        apiGet('/agents').then(setAgents).catch(() => { });
    }, []);

    // When SSE signals done, fetch final task state once
    useEffect(() => {
        if (!sseDone || !activeTask) return;
        apiGet(`/tasks/${activeTask.id}`)
            .then(updated => setActiveTask(updated))
            .catch(() => { });
        setSseUrl(null);
    }, [sseDone, activeTask?.id]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!prompt.trim()) return;

        setSubmitting(true);
        setError(null);
        clearMessages();
        setActiveTask(null);
        setSseUrl(null);

        try {
            const body = {
                prompt: prompt.trim(),
                strategy,
                agent_ids: useAll ? null : selectedAgentIds,
            };
            const task = await apiPost('/tasks', body);
            setActiveTask(task);
            // Start SSE stream for this task
            setSseUrl(`/api/tasks/${task.id}/events`);
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
                            <option value="council">Council — CEO-led discussion</option>
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
                    {activeTask && activeTask.status !== 'completed' && activeTask.status !== 'failed' && !sseDone && (
                        <div className="running-indicator card">
                            <span className="spinner"></span>
                            <div className="running-details">
                                <span>Task #{activeTask.id} is running...</span>
                                {strategy === 'council' && messages.length > 0 && (
                                    <span className="current-stage">
                                        {messages.slice().reverse().find(m => m.message?.includes('STAGE'))?.message?.split('\n')[0] || 'Starting...'}
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
