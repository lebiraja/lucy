import { useState } from 'react';
import './OutputPanel.css';

const ROLE_COLORS = { ceo: 'badge-gold', cto: 'badge-purple', manager: 'badge-info', employee: 'badge-default' };
const ROLE_LABELS = { ceo: 'CEO', cto: 'CTO', manager: 'Manager', employee: 'Employee' };

const STAGE_META = {
    opinion: { label: '📋 Opinions', title: 'Stage 1 — Individual Opinions', desc: 'Each agent analyzed the prompt from their role perspective.' },
    review: { label: '🔍 Reviews', title: 'Stage 2 — Cross-Review & Debate', desc: 'Agents evaluated each other\'s responses and debated.' },
    synthesis: { label: '🧠 Synthesis', title: 'Stage 3 — CEO Synthesis', desc: 'The CEO synthesized all inputs into the final plan.' },
};

export default function OutputPanel({ task }) {
    const [activeStage, setActiveStage] = useState('opinion');
    const [expandedSteps, setExpandedSteps] = useState(new Set());

    if (!task) return null;

    const statusClass = task.status === 'completed' ? 'success' : task.status === 'failed' ? 'danger' : 'running';
    const isCouncil = task.strategy === 'council';
    const steps = task.steps || [];

    // Group steps by label for council view
    const stageGroups = {
        opinion: steps.filter(s => s.step_label === 'opinion'),
        review: steps.filter(s => s.step_label === 'review'),
        synthesis: steps.filter(s => s.step_label === 'synthesis'),
    };

    const toggleStep = (id) => {
        setExpandedSteps(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    // Council-style output (stage tabs)
    if (isCouncil && steps.some(s => s.step_label)) {
        const activeSteps = stageGroups[activeStage] || [];
        const meta = STAGE_META[activeStage] || {};

        return (
            <div className="output-panel council-panel">
                <div className="output-header">
                    <h3>Council Discussion — Task #{task.id}</h3>
                    <span className={`badge badge-${statusClass === 'running' ? 'warning' : statusClass}`}>
                        {task.status}
                    </span>
                </div>

                {/* Stage tabs */}
                <div className="stage-tabs">
                    {Object.entries(STAGE_META).map(([key, { label }]) => (
                        <button
                            key={key}
                            className={`stage-tab ${activeStage === key ? 'active' : ''} ${stageGroups[key]?.length ? '' : 'disabled'}`}
                            onClick={() => stageGroups[key]?.length && setActiveStage(key)}
                        >
                            {label}
                            <span className="stage-count">{stageGroups[key]?.length || 0}</span>
                        </button>
                    ))}
                    <button
                        className={`stage-tab final-tab ${activeStage === 'final' ? 'active' : ''} ${task.final_output ? '' : 'disabled'}`}
                        onClick={() => task.final_output && setActiveStage('final')}
                    >
                        ✅ Final Plan
                    </button>
                </div>

                {/* Stage content */}
                {activeStage === 'final' ? (
                    <div className="final-plan-section">
                        <h4>Final Plan — CEO Decision</h4>
                        <div className="final-plan-content">
                            {task.final_output || 'Waiting for CEO synthesis...'}
                        </div>
                    </div>
                ) : (
                    <div className="stage-content">
                        <div className="stage-info">
                            <h4>{meta.title}</h4>
                            <p>{meta.desc}</p>
                        </div>
                        <div className="discussion-cards">
                            {activeSteps.map((step, i) => (
                                <div key={step.id || i} className={`discussion-card ${expandedSteps.has(step.id) ? 'expanded' : ''}`}>
                                    <div className="discussion-card-header" onClick={() => toggleStep(step.id)}>
                                        <div className="card-agent-info">
                                            <span className={`badge ${ROLE_COLORS[step.agent_role] || 'badge-default'} badge-sm`}>
                                                {ROLE_LABELS[step.agent_role] || step.agent_role || '?'}
                                            </span>
                                            <span className="card-agent-name">{step.agent_name || `Agent #${step.agent_id}`}</span>
                                        </div>
                                        <div className="card-meta">
                                            {step.duration_ms && <span className="step-duration">{step.duration_ms}ms</span>}
                                            <span className={`badge badge-${step.status === 'completed' ? 'success' : step.status === 'failed' ? 'danger' : 'warning'} badge-sm`}>
                                                {step.status}
                                            </span>
                                            <span className="expand-icon">{expandedSteps.has(step.id) ? '▾' : '▸'}</span>
                                        </div>
                                    </div>
                                    {expandedSteps.has(step.id) && (
                                        <div className="discussion-card-body">
                                            {step.response || 'No response'}
                                        </div>
                                    )}
                                </div>
                            ))}
                            {activeSteps.length === 0 && (
                                <div className="stage-empty">Waiting for this stage to begin...</div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // Default output (non-council)
    return (
        <div className="output-panel">
            <div className="output-header">
                <h3>Result — Task #{task.id}</h3>
                <span className={`badge badge-${statusClass === 'running' ? 'warning' : statusClass}`}>
                    {task.status}
                </span>
            </div>

            {task.final_output && (
                <div className="final-output">
                    <h4>Final Output</h4>
                    <div className="output-content">
                        {task.final_output}
                    </div>
                </div>
            )}

            {steps.length > 0 && (
                <div className="steps-section">
                    <h4>Agent Responses ({steps.length} steps)</h4>
                    <div className="steps-list">
                        {steps.map((step, i) => (
                            <details key={step.id || i} className="step-item">
                                <summary className="step-summary">
                                    <span className="step-order">Step {step.step_order + 1}</span>
                                    <span className="step-agent">{step.agent_name || `Agent #${step.agent_id}`}</span>
                                    {step.duration_ms && (
                                        <span className="step-duration">{step.duration_ms}ms</span>
                                    )}
                                    <span className={`badge badge-${step.status === 'completed' ? 'success' : step.status === 'failed' ? 'danger' : 'warning'} badge-sm`}>
                                        {step.status}
                                    </span>
                                </summary>
                                <div className="step-content">
                                    {step.response || 'No response'}
                                </div>
                            </details>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
