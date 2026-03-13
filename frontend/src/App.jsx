import { useState } from 'react';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import ProjectManager from './components/ProjectManager';
import AgentManager from './components/AgentManager';
import TaskCreator from './components/TaskCreator';
import Progress from './components/Progress';
import AgentMonitor from './components/AgentMonitor';
import AgentAssignment from './components/AgentAssignment';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'projects': return <ProjectManager />;
      case 'agents': return <AgentManager />;
      case 'tasks': return <TaskCreator />;
      case 'progress': return <Progress />;
      case 'monitoring': return <AgentMonitor />;
      case 'assignment': return <AgentAssignment />;
      default: return <Dashboard />;
    }
  };

  return (
    <Layout activeTab={activeTab} onTabChange={setActiveTab}>
      {renderTab()}
    </Layout>
  );
}

export default App;
