import { useEffect, useRef } from 'react';
import './LogViewer.css';

const ROLE_BADGE_COLORS = {
    ceo: '#e5a300',
    cto: '#a855f7',
    manager: '#3b82f6',
    employee: '#64748b',
};

export default function LogViewer({ messages }) {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const getLevelClass = (level) => {
        switch (level) {
            case 'error': return 'log-error';
            case 'warning': return 'log-warning';
            case 'agent': return 'log-agent';
            case 'debug': return 'log-debug';
            default: return 'log-info';
        }
    };

    const isStageMarker = (msg) => msg.message?.includes('STAGE') || msg.message?.startsWith('✓') || msg.message?.startsWith('✅');

    return (
        <div className="log-viewer">
            <div className="log-header">
                <h3>📡 Live Execution Log</h3>
                <span className="log-count">{messages.length} events</span>
            </div>
            <div className="log-container">
                {messages.length === 0 && (
                    <div className="log-empty">Waiting for task execution...</div>
                )}
                {messages.map((msg, i) => (
                    <div key={i} className={`log-entry ${getLevelClass(msg.level)} ${isStageMarker(msg) ? 'log-stage-marker' : ''}`}>
                        <span className="log-time">
                            {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '--:--:--'}
                        </span>
                        <span className="log-level">{(msg.level || 'info').toUpperCase()}</span>
                        <span className="log-source">[{msg.source || 'system'}]</span>
                        <span className="log-message">{msg.message}</span>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>
        </div>
    );
}
