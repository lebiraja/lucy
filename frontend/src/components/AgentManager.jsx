import { useState, useEffect } from 'react';
import AgentCard from './AgentCard';
import { apiGet, apiPost, apiPut, apiDelete } from '../hooks/useApi';
import './AgentManager.css';

const ROLES = ['ceo', 'cto', 'manager', 'employee'];
const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Employee' };

const EMPTY_FORM = {
    name: '', endpoint: '', model_name: '', role: 'employee',
    parent_id: '', description: '', is_active: true, is_orchestrator: false,
    temperature: 0.7, max_tokens: 2048, top_p: 0.95,
    max_iterations: 10, timeout_seconds: 300,
};

export default function AgentManager() {
    const [agents, setAgents] = useState([]);
    const [healthMap, setHealthMap] = useState({});
    const [showForm, setShowForm] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [loading, setLoading] = useState(false);
    const [probing, setProbing] = useState(false);
    const [probeResult, setProbeResult] = useState(null);
    const [showAdvanced, setShowAdvanced] = useState(false);
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

    const handleProbe = async () => {
        if (!form.endpoint.trim()) return;
        setProbing(true);
        setProbeResult(null);
        try {
            const result = await apiPost('/agents/probe', { endpoint: form.endpoint.trim() });
            if (result.success) {
                setForm(prev => ({ ...prev, model_name: result.model_name }));
                setProbeResult({ success: true, models: result.models });
            } else {
                setProbeResult({ success: false, error: result.error });
            }
        } catch (e) {
            setProbeResult({ success: false, error: e.message });
        } finally {
            setProbing(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            const submitData = { ...form };
            if (!submitData.model_name) delete submitData.model_name;
            submitData.parent_id = submitData.parent_id ? parseInt(submitData.parent_id) : null;
            if (editing) {
                await apiPut(`/agents/${editing.id}`, submitData);
            } else {
                await apiPost('/agents', submitData);
            }
            setShowForm(false);
            setEditing(null);
            setForm(EMPTY_FORM);
            setProbeResult(null);
            setShowAdvanced(false);
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
            model_name: agent.model_name || '',
            role: agent.role,
            parent_id: agent.parent_id || '',
            description: agent.description || '',
            is_active: agent.is_active,
            is_orchestrator: agent.is_orchestrator,
            temperature: agent.temperature,
            max_tokens: agent.max_tokens,
            top_p: agent.top_p,
            max_iterations: agent.max_iterations,
            timeout_seconds: agent.timeout_seconds,
        });
        setProbeResult(null);
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
            setHealthMap(prev => ({ ...prev, [id]: { id, is_online: false, error: e.message } }));
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

    const handleAction = async (id, action) => {
        try {
            await apiPost(`/agents/${id}/${action}`);
            await loadAgents();
        } catch (e) {
            setError(e.message);
        }
    };

    const updateField = (field, value) => {
        if (field === 'endpoint') {
            setForm(prev => ({ ...prev, endpoint: value, model_name: '' }));
            setProbeResult(null);
        } else {
            setForm(prev => ({ ...prev, [field]: value }));
        }
    };

    // Get potential parent agents (can't be self)
    const parentOptions = agents.filter(a => !editing || a.id !== editing.id);

    return (
        <div className="agent-manager fade-in">
            <div className="page-header">
                <div>
                    <h1>Agent Manager</h1>
                    <p className="page-subtitle">Connect and configure your LLM agents</p>
                </div>
                <div className="header-actions">
                    <button className="btn btn-ghost" onClick={handleCheckAll}>♥ Check All</button>
                    <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditing(null); setForm(EMPTY_FORM); setProbeResult(null); setShowAdvanced(false); }}>
                        + Add Agent
                    </button>
                </div>
            </div>

            {error && <div className="error-banner">{error} <button onClick={() => setError(null)}>✕</button></div>}

            {showForm && (
                <div className="agent-form-overlay" onClick={() => setShowForm(false)}>
                    <form className="agent-form card" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
                        <h2>{editing ? 'Edit Agent' : 'Add New Agent'}</h2>

                        <div className="form-scroll">
                            <div className="form-grid">
                                {/* Endpoint + Detect — the primary input */}
                                <div className="form-group full-width">
                                    <label>Endpoint URL</label>
                                    <div className="endpoint-row">
                                        <input
                                            value={form.endpoint}
                                            onChange={e => updateField('endpoint', e.target.value)}
                                            placeholder="http://192.168.73.41:9002"
                                            required
                                            className="endpoint-input"
                                        />
                                        <button
                                            type="button"
                                            className="btn btn-success btn-sm detect-btn"
                                            onClick={handleProbe}
                                            disabled={probing || !form.endpoint.trim()}
                                        >
                                            {probing ? <span className="spinner"></span> : '⚡ Detect'}
                                        </button>
                                    </div>
                                    {probeResult && (
                                        <div className={`probe-result ${probeResult.success ? 'probe-success' : 'probe-error'}`}>
                                            {probeResult.success
                                                ? <>✓ <strong>{form.model_name}</strong></>
                                                : <>✕ {probeResult.error}</>
                                            }
                                        </div>
                                    )}
                                </div>

                                <div className="form-group">
                                    <label>Name</label>
                                    <input value={form.name} onChange={e => updateField('name', e.target.value)} placeholder="e.g. System-1" required />
                                </div>

                                <div className="form-group">
                                    <label>Role</label>
                                    <select value={form.role} onChange={e => updateField('role', e.target.value)}>
                                        {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                                    </select>
                                </div>

                                <div className="form-group">
                                    <label>Reports To</label>
                                    <select value={form.parent_id} onChange={e => updateField('parent_id', e.target.value)}>
                                        <option value="">None (Top Level)</option>
                                        {parentOptions.map(a => (
                                            <option key={a.id} value={a.id}>{a.name} ({ROLE_LABELS[a.role] || a.role})</option>
                                        ))}
                                    </select>
                                </div>

                                <div className="form-group">
                                    <label>Model <span className="label-hint">(auto-detected)</span></label>
                                    <input value={form.model_name} onChange={e => updateField('model_name', e.target.value)} placeholder="Auto-detected" className={form.model_name ? 'detected' : ''} />
                                </div>

                                <div className="form-group full-width">
                                    <label>Description</label>
                                    <textarea value={form.description} onChange={e => updateField('description', e.target.value)} placeholder="What this agent is best at..." rows={2} />
                                </div>

                                <div className="form-group full-width">
                                    <div className="checkbox-group-row">
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

                            {/* Collapsible Advanced Settings */}
                            <details className="advanced-section" open={showAdvanced}>
                                <summary className="advanced-toggle" onClick={e => { e.preventDefault(); setShowAdvanced(!showAdvanced); }}>
                                    ⚙ Advanced Settings
                                </summary>
                                <div className="form-grid advanced-grid">
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
                                        <label>Max Iterations</label>
                                        <input type="number" min="1" max="1000" value={form.max_iterations} onChange={e => updateField('max_iterations', parseInt(e.target.value))} />
                                    </div>
                                    <div className="form-group">
                                        <label>Timeout (seconds)</label>
                                        <input type="number" min="10" max="86400" value={form.timeout_seconds} onChange={e => updateField('timeout_seconds', parseInt(e.target.value))} />
                                    </div>
                                </div>
                            </details>
                        </div>{/* end form-scroll */}

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
                        agents={agents}
                        health={healthMap[agent.id]}
                        onEdit={handleEdit}
                        onDelete={handleDelete}
                        onHealthCheck={handleHealthCheck}
                        onAction={handleAction}
                    />
                ))}
                {agents.length === 0 && (
                    <div className="empty-state">
                        <p>No agents connected yet.</p>
                        <p className="text-muted">Click "+ Add Agent" to connect your first vLLM endpoint.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
