import { useState, useEffect } from 'react';
import AgentCard from './AgentCard';
import { apiGet, apiPost, apiPut, apiDelete } from '../hooks/useApi';
import './AgentManager.css';

const getRoleLabel = (role) => {
    if (!role) return 'Unknown';
    const defaults = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };
    return defaults[role] || (role.charAt(0).toUpperCase() + role.slice(1));
};

const ROLES = ['ceo', 'cto', 'manager', 'employee'];
const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Worker' };

const EMPTY_FORM = {
    name: '', endpoint: '', model_name: '', description: '', role: 'employee',
    is_active: true, is_orchestrator: false,
    temperature: 0.7, max_tokens: 2048, top_p: 0.95,
    max_iterations: 10, timeout_seconds: 300,
};

export default function AgentManager() {
    const [agents, setAgents] = useState([]);
    const [healthMap, setHealthMap] = useState({});
    const [showForm, setShowForm] = useState(false);
    const [showBulk, setShowBulk] = useState(false);
    const [showRetrain, setShowRetrain] = useState(null);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [bulkText, setBulkText] = useState('');
    const [retrainForm, setRetrainForm] = useState({ role: 'employee', parent_id: '', description: '' });
    const [loading, setLoading] = useState(false);
    const [probing, setProbing] = useState(false);
    const [probeResult, setProbeResult] = useState(null);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [error, setError] = useState(null);
    const [filterRole, setFilterRole] = useState('all');
    const [fleetSummary, setFleetSummary] = useState(null);

    const loadAgents = async () => {
        try {
            const [data, fleet] = await Promise.all([
                apiGet('/agents'),
                apiGet('/agents/fleet-summary').catch(() => apiGet('/agents/fleet-status').then(f => ({
                    ...f, busy_count: f.under_review_count, by_role: f.by_role?.map(r => ({ ...r, busy: r.under_review })) || []
                }))),
            ]);
            setAgents(data);
            setFleetSummary(fleet);
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
            submitData.parent_id = null;
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


    const handleBulkRegister = async () => {
        setLoading(true);
        setError(null);
        try {
            // Parse bulk text: each line is "name | endpoint" or just "endpoint"
            const lines = bulkText.split('\n').filter(l => l.trim());
            const agentsList = lines.map((line, i) => {
                const parts = line.split('|').map(s => s.trim());
                if (parts.length >= 2) {
                    return { name: parts[0], endpoint: parts[1] };
                }
                return { name: `Agent-${i + 1}`, endpoint: parts[0] };
            });
            const result = await apiPost('/agents/bulk-register', { agents: agentsList });
            setShowBulk(false);
            setBulkText('');
            await loadAgents();
            if (result.failed > 0) {
                setError(`Registered ${result.registered}, failed ${result.failed}`);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleRetrain = async (agentId) => {
        setLoading(true);
        setError(null);
        try {
            const data = { ...retrainForm };
            data.parent_id = data.parent_id ? parseInt(data.parent_id) : null;
            await apiPost(`/agents/${agentId}/retrain`, data);
            setShowRetrain(null);
            setRetrainForm({ role: 'employee', parent_id: '', description: '' });
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
            description: agent.description || '',
            role: agent.role || 'employee',
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

    // Filter agents
    const filteredAgents = filterRole === 'all' ? agents : agents.filter(a => a.role === filterRole);

    // Role counts for quick filter tabs
    const roleCounts = {};
    agents.forEach(a => { roleCounts[a.role] = (roleCounts[a.role] || 0) + 1; });

    return (
        <div className="agent-manager fade-in">
            <div className="page-header">
                <div>
                    <h1>Agent Fleet</h1>
                    <p className="page-subtitle">Register agents as workers — CEO assigns roles dynamically</p>
                </div>
                <div className="header-actions">
                    <button className="btn btn-ghost" onClick={handleCheckAll}>♥ Health Check</button>
                    <button className="btn btn-ghost" onClick={() => setShowBulk(true)}>⚡ Bulk Register</button>
                    <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditing(null); setForm(EMPTY_FORM); setProbeResult(null); setShowAdvanced(false); }}>
                        + Add Agent
                    </button>
                </div>
            </div>

            {error && <div className="error-banner">{error} <button onClick={() => setError(null)}>✕</button></div>}

            {/* CEO Assignment Summary */}
            {fleetSummary && (
                <div className="fleet-bar">
                    <div className="fleet-bar-item">
                        <span className="fbi-count">{fleetSummary.total_agents}</span>
                        <span className="fbi-label">Total</span>
                    </div>
                    {(fleetSummary.by_role || []).map(r => (
                        <div key={r.role} className="fleet-bar-item">
                            <span className="fbi-count">{r.total}</span>
                            <span className="fbi-label">{getRoleLabel(r.role)}</span>
                        </div>
                    ))}
                    {fleetSummary.unassigned_count > 0 && (
                        <div className="fleet-bar-item unassigned">
                            <span className="fbi-count">{fleetSummary.unassigned_count}</span>
                            <span className="fbi-label">Unassigned</span>
                        </div>
                    )}
                </div>
            )}

            {/* Role Filter Tabs */}
            <div className="role-filter-bar">
                <button className={`filter-tab ${filterRole === 'all' ? 'active' : ''}`} onClick={() => setFilterRole('all')}>
                    All <span className="filter-count">{agents.length}</span>
                </button>
                {Object.keys(roleCounts).sort().map(r => (
                    <button key={r} className={`filter-tab ${filterRole === r ? 'active' : ''}`} onClick={() => setFilterRole(r)}>
                        {getRoleLabel(r)} <span className="filter-count">{roleCounts[r]}</span>
                    </button>
                ))}
            </div>

            {/* Bulk Register Modal */}
            {showBulk && (
                <div className="agent-form-overlay" onClick={() => setShowBulk(false)}>
                    <div className="agent-form card" onClick={e => e.stopPropagation()}>
                        <h2>Bulk Register Agents</h2>
                        <p className="text-muted" style={{ marginBottom: '12px', fontSize: '0.82rem' }}>
                            Enter one agent per line: <code>name | endpoint</code> or just <code>endpoint</code>
                        </p>
                        <textarea
                            value={bulkText}
                            onChange={e => setBulkText(e.target.value)}
                            placeholder={"System-1 | http://192.168.73.41:9001\nSystem-2 | http://192.168.73.41:9002\nhttp://192.168.73.41:9003"}
                            rows={8}
                            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                        />
                        <p className="text-muted" style={{ marginTop: '8px', fontSize: '0.75rem' }}>
                            All agents will register as generic workers. CEO assigns roles later.
                        </p>
                        <div className="form-actions">
                            <button type="button" className="btn btn-ghost" onClick={() => setShowBulk(false)}>Cancel</button>
                            <button type="button" className="btn btn-primary" onClick={handleBulkRegister} disabled={loading || !bulkText.trim()}>
                                {loading ? <span className="spinner"></span> : `Register ${bulkText.split('\n').filter(l => l.trim()).length} Agents`}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Add/Edit Agent Modal — NO ROLE FIELD */}
            {showForm && (
                <div className="agent-form-overlay" onClick={() => setShowForm(false)}>
                    <form className="agent-form card" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
                        <h2>{editing ? 'Edit Agent' : 'Register New Agent'}</h2>
                        {!editing && <p className="form-hint">Agent joins as a generic worker. CEO will assign role later.</p>}

                        <div className="form-scroll">
                            <div className="form-grid">
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
                        </div>

                        <div className="form-actions">
                            <button type="button" className="btn btn-ghost" onClick={() => { setShowForm(false); setEditing(null); }}>Cancel</button>
                            <button type="submit" className="btn btn-primary" disabled={loading}>
                                {loading ? <span className="spinner"></span> : editing ? 'Update Agent' : 'Register Agent'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {/* Retrain Modal */}
            {showRetrain && (
                <div className="agent-form-overlay" onClick={() => setShowRetrain(null)}>
                    <div className="agent-form card retrain-modal" onClick={e => e.stopPropagation()}>
                        <h2>CEO: Retrain Agent</h2>
                        <p className="retrain-agent-name">Agent: <strong>{showRetrain.name}</strong></p>

                        <div className="form-grid">
                            <div className="form-group">
                                <label>Assign Role</label>
                                <select value={retrainForm.role} onChange={e => setRetrainForm(prev => ({ ...prev, role: e.target.value }))}>
                                    {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                                </select>
                            </div>
                            <div className="form-group">
                                <label>Reports To</label>
                                <select value={retrainForm.parent_id} onChange={e => setRetrainForm(prev => ({ ...prev, parent_id: e.target.value }))}>
                                    <option value="">None (Top Level)</option>
                                    {agents.filter(a => a.id !== showRetrain.id).map(a => (
                                        <option key={a.id} value={a.id}>{a.name} ({ROLE_LABELS[a.role] || a.role})</option>
                                    ))}
                                </select>
                            </div>
                            <div className="form-group full-width">
                                <label>Role Description</label>
                                <textarea
                                    value={retrainForm.description}
                                    onChange={e => setRetrainForm(prev => ({ ...prev, description: e.target.value }))}
                                    placeholder="CEO context: describe this agent's responsibilities..."
                                    rows={3}
                                />
                            </div>
                        </div>

                        <div className="form-actions">
                            <button type="button" className="btn btn-ghost" onClick={() => setShowRetrain(null)}>Cancel</button>
                            <button type="button" className="btn btn-primary" onClick={() => handleRetrain(showRetrain.id)} disabled={loading}>
                                {loading ? <span className="spinner"></span> : 'Assign & Retrain'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <div className="agent-grid">
                {filteredAgents.map(agent => (
                    <AgentCard
                        key={agent.id}
                        agent={agent}
                        agents={agents}
                        health={healthMap[agent.id]}
                        onEdit={handleEdit}
                        onDelete={handleDelete}
                        onHealthCheck={handleHealthCheck}
                        onAction={handleAction}
                        onRetrain={(agent) => { setShowRetrain(agent); setRetrainForm({ role: agent.role, parent_id: agent.parent_id || '', description: agent.description || '' }); }}
                    />
                ))}
                {filteredAgents.length === 0 && (
                    <div className="empty-state">
                        {filterRole === 'all'
                            ? <><p>No agents connected yet.</p><p className="text-muted">Click "+ Add Agent" to register your first vLLM endpoint.</p></>
                            : <><p>No {ROLE_LABELS[filterRole]} agents.</p><p className="text-muted">Use "Retrain" on any agent to assign this role via CEO.</p></>
                        }
                    </div>
                )}
            </div>
        </div>
    );
}
