import './OutputPanel.css';

export default function OutputPanel({ task }) {
    if (!task) return null;

    const statusClass = task.status === 'completed' ? 'success' : task.status === 'failed' ? 'danger' : 'running';

    return (
        <div className="output-panel">
            <div className="output-header">
                <h3>Result — Task #{task.id}</h3>
                <span className={`badge badge-${statusClass === 'running' ? 'warning' : statusClass}`}>
                    {task.status}
                </span>
            </div>

            {/* Final Output */}
            {task.final_output && (
                <div className="final-output">
                    <h4>Final Output</h4>
                    <div className="output-content">
                        {task.final_output}
                    </div>
                </div>
            )}

            {/* Individual Steps */}
            {task.steps && task.steps.length > 0 && (
                <div className="steps-section">
                    <h4>Agent Responses ({task.steps.length} steps)</h4>
                    <div className="steps-list">
                        {task.steps.map((step, i) => (
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
