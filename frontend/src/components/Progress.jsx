import { useState, useEffect } from 'react';
import { apiGet } from '../hooks/useApi';
import OutputPanel from './OutputPanel';
import LogViewer from './LogViewer';
import './Progress.css';

export default function Progress() {
    const [tasks, setTasks] = useState([]);
    const [selectedTaskId, setSelectedTaskId] = useState(null);
    const [selectedTaskDetails, setSelectedTaskDetails] = useState(null);
    const [taskLogs, setTaskLogs] = useState([]);
    const [loadingTasks, setLoadingTasks] = useState(true);
    const [loadingDetails, setLoadingDetails] = useState(false);

    // Fetch task list
    const fetchTasks = async () => {
        try {
            const data = await apiGet('/tasks?limit=50');
            setTasks(data);
            if (data.length > 0 && !selectedTaskId) {
                setSelectedTaskId(data[0].id);
            }
        } catch (error) {
            console.error('Failed to fetch tasks:', error);
        } finally {
            setLoadingTasks(false);
        }
    };

    useEffect(() => {
        fetchTasks();
        // Initial polling for active tasks in the list
        const interval = setInterval(fetchTasks, 5000);
        return () => clearInterval(interval);
    }, []);

    // Fetch specific task details & logs when selected
    useEffect(() => {
        if (!selectedTaskId) return;

        let pollingInterval;

        const fetchDetails = async () => {
            try {
                setLoadingDetails(true);
                const [taskData, logsData] = await Promise.all([
                    apiGet(`/tasks/${selectedTaskId}`),
                    apiGet(`/tasks/${selectedTaskId}/logs`)
                ]);
                setSelectedTaskDetails(taskData);
                setTaskLogs(logsData);

                // Stop polling if completed or failed
                if (taskData.status === 'completed' || taskData.status === 'failed') {
                    clearInterval(pollingInterval);
                }
            } catch (error) {
                console.error('Failed to fetch task details:', error);
            } finally {
                setLoadingDetails(false);
            }
        };

        fetchDetails();

        // Poll actively running tasks
        pollingInterval = setInterval(fetchDetails, 2000);

        return () => clearInterval(pollingInterval);
    }, [selectedTaskId]);

    const getStatusBadgeClass = (status) => {
        switch (status) {
            case 'completed': return 'badge-success';
            case 'failed': return 'badge-danger';
            case 'running': return 'badge-warning';
            default: return 'badge-default';
        }
    };

    return (
        <div className="progress-page fade-in">
            <div className="progress-sidebar">
                <div className="sidebar-header">
                    <h2>Task History</h2>
                    <button className="btn btn-outline btn-sm" onClick={fetchTasks}>↻ Refresh</button>
                </div>

                {loadingTasks && tasks.length === 0 ? (
                    <div className="empty-state">Loading tasks...</div>
                ) : tasks.length === 0 ? (
                    <div className="empty-state">No tasks created yet.</div>
                ) : (
                    <div className="task-list">
                        {tasks.map(task => (
                            <div
                                key={task.id}
                                className={`task-list-item ${selectedTaskId === task.id ? 'active' : ''}`}
                                onClick={() => setSelectedTaskId(task.id)}
                            >
                                <div className="task-item-header">
                                    <span className="task-id">#{task.id}</span>
                                    <span className={`badge badge-sm ${getStatusBadgeClass(task.status)}`}>{task.status}</span>
                                </div>
                                <div className="task-prompt">{task.prompt}</div>
                                <div className="task-meta">
                                    <span className="task-strategy">{task.strategy} strategy</span>
                                    <span className="task-time">
                                        {new Date(task.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="progress-main">
                {loadingDetails && !selectedTaskDetails ? (
                    <div className="detail-loading spinner"></div>
                ) : !selectedTaskDetails ? (
                    <div className="empty-selection">Select a task from the sidebar to view details</div>
                ) : (
                    <div className="task-detail-view fade-in">
                        <div className="detail-header card">
                            <div className="detail-prompt-label">Original Prompt:</div>
                            <div className="detail-prompt">{selectedTaskDetails.prompt}</div>
                        </div>

                        <div className="detail-content">
                            <div className="detail-output">
                                <OutputPanel task={selectedTaskDetails} />
                            </div>
                            <div className="detail-logs">
                                <LogViewer messages={taskLogs} />
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
