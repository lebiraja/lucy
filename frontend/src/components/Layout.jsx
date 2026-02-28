import './Layout.css';

const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: '◈' },
    { id: 'agents', label: 'Agents', icon: '⬡' },
    { id: 'tasks', label: 'New Task', icon: '▶' },
    { id: 'progress', label: 'Progress', icon: '📊' },
];

export default function Layout({ activeTab, onTabChange, children }) {
    return (
        <div className="layout">
            <aside className="sidebar">
                <div className="sidebar-header">
                    <div className="logo">
                        <span className="logo-icon">✦</span>
                        <span className="logo-text">Lucy</span>
                    </div>
                    <p className="sidebar-subtitle">Multi-Agent Orchestrator</p>
                </div>

                <nav className="sidebar-nav">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
                            onClick={() => onTabChange(tab.id)}
                        >
                            <span className="nav-icon">{tab.icon}</span>
                            <span className="nav-label">{tab.label}</span>
                        </button>
                    ))}
                </nav>

                <div className="sidebar-footer">
                    <div className="status-indicator">
                        <span className="status-dot online"></span>
                        <span>System Online</span>
                    </div>
                </div>
            </aside>

            <main className="main-content">
                {children}
            </main>
        </div>
    );
}
