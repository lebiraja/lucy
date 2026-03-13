import { useState, useEffect, useRef } from 'react';
import { apiGet } from '../hooks/useApi';
import './TaskChat.css';

export default function TaskChat({ projectId, taskId, onClose }) {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const messagesEndRef = useRef(null);

    const loadMessages = async () => {
        try {
            const data = await apiGet(`/projects/${projectId}/tasks/${taskId}/chat`);
            setMessages(data);
        } catch (e) {
            console.error('Failed to load messages:', e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (projectId && taskId) {
            loadMessages();
        }
    }, [projectId, taskId]);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // Auto-refresh messages every 3 seconds if autoRefresh is enabled
    useEffect(() => {
        if (!autoRefresh) return;
        
        const interval = setInterval(() => {
            loadMessages();
        }, 3000);

        return () => clearInterval(interval);
    }, [autoRefresh, projectId, taskId]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const formatTime = (timestamp) => {
        if (!timestamp) return '';
        return new Date(timestamp).toLocaleTimeString();
    };

    const getMessageTypeClass = (type) => {
        switch (type) {
            case 'system': return 'system';
            case 'notification': return 'notification';
            case 'agent_message': return 'agent-message';
            default: return 'chat';
        }
    };

    if (loading) {
        return (
            <div className="task-chat loading">
                <span className="spinner"></span> Loading agent conversation...
            </div>
        );
    }

    return (
        <div className="task-chat">
            <div className="task-chat-header">
                <div className="chat-header-left">
                    <h3>Task #{taskId} - Agent Conversation</h3>
                    <span className="chat-subtitle">
                        Inter-agent communication during task execution
                    </span>
                </div>
                <div className="chat-header-right">
                    <label className="auto-refresh-toggle">
                        <input
                            type="checkbox"
                            checked={autoRefresh}
                            onChange={e => setAutoRefresh(e.target.checked)}
                        />
                        Auto-refresh
                    </label>
                    {onClose && (
                        <button className="btn-close" onClick={onClose}>×</button>
                    )}
                </div>
            </div>

            <div className="task-chat-messages">
                {messages.length === 0 ? (
                    <div className="no-messages">
                        <p className="no-messages-icon">💬</p>
                        <p>No agent messages yet</p>
                        <p className="hint">
                            Agent conversation will appear here during task execution.
                            Messages are automatically logged when agents communicate.
                        </p>
                    </div>
                ) : (
                    messages.map((msg, index) => (
                        <div
                            key={msg.id || index}
                            className={`chat-message ${getMessageTypeClass(msg.message_type)}`}
                        >
                            <div className="message-header">
                                <div className="message-sender-info">
                                    <span className="message-sender">
                                        {msg.sender_name || 'System'}
                                    </span>
                                    {msg.sender_role && (
                                        <span className="sender-role">{msg.sender_role.toUpperCase()}</span>
                                    )}
                                </div>
                                <span className="message-time">{formatTime(msg.timestamp)}</span>
                            </div>
                            <div className="message-content">
                                {msg.message_type === 'notification' && (
                                    <span className="notification-icon">📢</span>
                                )}
                                {msg.message_type === 'system' && (
                                    <span className="notification-icon">⚙️</span>
                                )}
                                {msg.message_type === 'agent_message' && (
                                    <span className="notification-icon">🤖</span>
                                )}
                                <p>{msg.message}</p>
                            </div>
                        </div>
                    ))
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="task-chat-footer">
                <p className="footer-note">
                    This is a read-only view of agent-to-agent communication. 
                    Messages are automatically generated during task execution.
                </p>
            </div>
        </div>
    );
}
