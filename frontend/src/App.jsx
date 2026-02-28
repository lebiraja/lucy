import { useState } from 'react';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import AgentManager from './components/AgentManager';
import TaskCreator from './components/TaskCreator';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  const renderTab = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'agents': return <AgentManager />;
      case 'tasks': return <TaskCreator />;
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
