import { useState, useEffect } from 'react';
import AgentCard from './AgentCard';
import { apiGet, apiPost, apiPut, apiDelete } from '../hooks/useApi';
import './AgentManager.css';

const EMPTY_FORM = {
    name: '', endpoint: '', model_name: '', role: 'general',
    description: '', is_active: true, is_orchestrator: false,
    temperature: 0.7, max_tokens: 2048, top_p: 0.95,
};

export default function AgentManager() {
    const [agents, setAgents] = useState([]);
    const [healthMap, setHealthMap] = useState({});
    const [showForm, setShowForm] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const loadAgents = async () => {
        try {
            const data = await apiGet('/agents');
            setAgents(data);
        } catch (e) {
            setError(e.message);
        }
    };

    useEffect(() => { loadAgents(); }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            if (editing) {
                await apiPut(`/agents/${editing.id}`, form);
            } else {
                await apiPost('/agents', form);
            }
            setShowForm(false);
            setEditing(null);
            setForm(EMPTY_FORM);
            await loadAgents();
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (agent) => {
        setEditing(agent);
        setForm({
            name: agent.name,
            endpoint: agent.endpoint,
            model_name: agent.model_name,
            role: agent.role,
            description: agent.description || '',
            is_active: agent.is_active,
            is_orchestrator: agent.is_orchestrator,
            temperature: agent.temperature,
            max_tokens: agent.max_tokens,
            top_p: agent.top_p,
        });
        setShowForm(true);
    };

    const handleDelete = async (id) => {
        if (!confirm('Remove this agent?')) return;
        try {
            await apiDelete(`/agents/${id}`);
            await loadAgents();
        } catch (e) {
            setError(e.message);
        }
    };

    const handleHealthCheck = async (id) => {
        try {
            const health = await apiGet(`/agents/${id}/health`);
            setHealthMap(prev => ({ ...prev, [id]: health }));
        } catch (e) {
            setHealthMap(prev => ({
                ...prev,
                [id]: { id, is_online: false, error: e.message },
            }));
        }
    };

    const handleCheckAll = async () => {
        try {
            const results = await apiGet('/agents/health');
            const map = {};
            results.forEach(h => { map[h.id] = h; });
            setHealthMap(map);
        } catch (e) {
            setError(e.message);
        }
    };

    const updateField = (field, value) => {
        setForm(prev => ({ ...prev, [field]: value }));
    };

    return (
        <div className="agent-manager fade-in">
            <div className="page-header">
                <div>
                    <h1>Agent Manager</h1>
                    <p className="page-subtitle">Connect and configure your LLM agents</p>
                </div>
                <div className="header-actions">
                    <button className="btn btn-ghost" onClick={handleCheckAll}>♥ Check All Health</button>
                    <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditing(null); setForm(EMPTY_FORM); }}>
                        + Add Agent
                    </button>
                </div>
            </div>

            {error && <div className="error-banner">{error} <button onClick={() => setError(null)}>✕</button></div>}

            {showForm && (
                <div className="agent-form-overlay" onClick={() => setShowForm(false)}>
                    <form className="agent-form card" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
                        <h2>{editing ? 'Edit Agent' : 'Add New Agent'}</h2>

                        <div className="form-grid">
                            <div className="form-group">
                                <label>Name</label>
                                <input value={form.name} onChange={e => updateField('name', e.target.value)} placeholder="e.g. Qwen-72B-Coder" required />
                            </div>
                            <div className="form-group">
                                <label>Endpoint URL</label>
                                <input value={form.endpoint} onChange={e => updateField('endpoint', e.target.value)} placeholder="http://192.168.73.41:9002" required />
                            </div>
                            <div className="form-group">
                                <label>Model Name</label>
                                <input value={form.model_name} onChange={e => updateField('model_name', e.target.value)} placeholder="Qwen/Qwen2.5-72B-Instruct" required />
                            </div>
                            <div className="form-group">
                                <label>Role</label>
                                <input value={form.role} onChange={e => updateField('role', e.target.value)} placeholder="e.g. coder, reviewer, researcher" />
                            </div>
                            <div className="form-group full-width">
                                <label>Description</label>
                                <textarea value={form.description} onChange={e => updateField('description', e.target.value)} placeholder="What this agent is best at..." rows={2} />
                            </div>
                            <div className="form-group">
                                <label>Temperature</label>
                                <input type="number" step="0.05" min="0" max="2" value={form.temperature} onChange={e => updateField('temperature', parseFloat(e.target.value))} />
                            </div>
                            <div className="form-group">
                                <label>Max Tokens</label>
                                <input type="number" min="1" max="128000" value={form.max_tokens} onChange={e => updateField('max_tokens', parseInt(e.target.value))} />
                            </div>
                            <div className="form-group">
                                <label>Top P</label>
                                <input type="number" step="0.05" min="0" max="1" value={form.top_p} onChange={e => updateField('top_p', parseFloat(e.target.value))} />
                            </div>
                            <div className="form-group">
                                <div className="checkbox-group">
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={form.is_active} onChange={e => updateField('is_active', e.target.checked)} />
                                        <span>Active</span>
                                    </label>
                                    <label className="checkbox-label">
                                        <input type="checkbox" checked={form.is_orchestrator} onChange={e => updateField('is_orchestrator', e.target.checked)} />
                                        <span>Orchestrator Brain</span>
                                    </label>
                                </div>
                            </div>
                        </div>

                        <div className="form-actions">
                            <button type="button" className="btn btn-ghost" onClick={() => { setShowForm(false); setEditing(null); }}>Cancel</button>
                            <button type="submit" className="btn btn-primary" disabled={loading}>
                                {loading ? <span className="spinner"></span> : editing ? 'Update Agent' : 'Add Agent'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="agent-grid">
                {agents.map(agent => (
                    <AgentCard
                        key={agent.id}
                        agent={agent}
                        health={healthMap[agent.id]}
                        onEdit={handleEdit}
                        onDelete={handleDelete}
                        onHealthCheck={handleHealthCheck}
                    />
                ))}
                {agents.length === 0 && (
                    <div className="empty-state">
                        <p>No agents connected yet.</p>
                        <p className="text-muted">Click "Add Agent" to connect your first vLLM endpoint.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
