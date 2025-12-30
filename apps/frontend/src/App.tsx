import React from 'react';
import { Play } from 'lucide-react';

function App() {
  const runTask = async () => {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const res = await fetch(`${apiUrl}/api/v1/tasks/submit`, { method: 'POST' });
    const data = await res.json();
    alert('Started Workflow: ' + data.id);
  };

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
      <h1>Argo Workflow Manager</h1>
      <button onClick={runTask} style={{ display: 'flex', gap: '8px', padding: '10px 20px', cursor: 'pointer' }}>
        <Play size={20} /> Run Python Task
      </button>
    </div>
  );
}

export default App;
