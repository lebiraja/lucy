import { useState, useEffect } from 'react';
import { apiGet } from '../hooks/useApi';
import './Layout.css';

const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: '◈' },
    { id: 'projects', label: 'Projects', icon: '📋' },
    { id: 'assignment', label: 'Assignment', icon: '🎯' },
    { id: 'agents', label: 'Agents', icon: '⬡' },
    { id: 'tasks', label: 'New Task', icon: '▶' },
    { id: 'progress', label: 'Progress', icon: '📊' },
    { id: 'monitoring', label: 'Live Monitor', icon: '📡' },
];

export default function Layout({ activeTab, onTabChange, children }) {
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [fleetMini, setFleetMini] = useState(null);

    useEffect(() => {
        const load = async () => {
            try {
                const data = await apiGet('/agents/fleet-status');
                setFleetMini(data);
            } catch { /* ignore */ }
        };
        load();
        const interval = setInterval(load, 30000);
        return () => clearInterval(interval);
    }, []);

    const handleTabClick = (id) => {
        onTabChange(id);
        setSidebarOpen(false);
    };

    return (
        <div className="layout">
            {/* Mobile hamburger */}
            <button className="hamburger" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle menu">
                <span className={`hamburger-line ${sidebarOpen ? 'open' : ''}`}></span>
                <span className={`hamburger-line ${sidebarOpen ? 'open' : ''}`}></span>
                <span className={`hamburger-line ${sidebarOpen ? 'open' : ''}`}></span>
            </button>

            {/* Overlay for mobile */}
            {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)}></div>}

            <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
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
                            onClick={() => handleTabClick(tab.id)}
                        >
                            <span className="nav-icon">{tab.icon}</span>
                            <span className="nav-label">{tab.label}</span>
                        </button>
                    ))}
                </nav>

                <div className="sidebar-footer">
                    {fleetMini && (
                        <div className="fleet-mini">
                            <div className="fleet-mini-stat">
                                <span className="fms-value">{fleetMini.total_agents}</span>
                                <span className="fms-label">Fleet</span>
                            </div>
                            <div className="fleet-mini-stat">
                                <span className="fms-value online-text">{fleetMini.ready_count}</span>
                                <span className="fms-label">Ready</span>
                            </div>
                            <div className="fleet-mini-stat">
                                <span className="fms-value">{fleetMini.offline_count}</span>
                                <span className="fms-label">Off</span>
                            </div>
                        </div>
                    )}
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
