import React, { useState, useEffect } from 'react';
import { Play, RefreshCw } from 'lucide-react';

interface Task {
  id: string;
  generateName: string;
  phase: string;
  startedAt: string;
  finishedAt: string;
  createdAt: string;
  pythonCode: string;
}

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const fetchTasks = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${apiUrl}/api/v1/tasks`);
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    // Refresh every 5 seconds
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  const runTask = async () => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/tasks/submit`, { method: 'POST' });
      const data = await res.json();
      alert('Started Workflow: ' + data.id);
      // Refresh the task list
      fetchTasks();
    } catch (error) {
      console.error('Failed to submit task:', error);
      alert('Failed to submit task');
    }
  };

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case 'Succeeded': return '#10b981';
      case 'Failed': return '#ef4444';
      case 'Running': return '#3b82f6';
      case 'Pending': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Argo Workflow Manager</h1>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            onClick={fetchTasks} 
            disabled={loading}
            style={{ 
              display: 'flex', 
              gap: '8px', 
              padding: '10px 20px', 
              cursor: 'pointer',
              border: '1px solid #ccc',
              borderRadius: '4px',
              background: 'white'
            }}
          >
            <RefreshCw size={20} /> Refresh
          </button>
          <button 
            onClick={runTask} 
            style={{ 
              display: 'flex', 
              gap: '8px', 
              padding: '10px 20px', 
              cursor: 'pointer',
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '4px'
            }}
          >
            <Play size={20} /> Run Python Task
          </button>
        </div>
      </div>

      <div style={{ marginTop: '2rem' }}>
        <h2>Submitted Tasks</h2>
        {loading && tasks.length === 0 ? (
          <p>Loading tasks...</p>
        ) : tasks.length === 0 ? (
          <p>No tasks found. Submit a task to get started.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
                <th style={{ padding: '12px' }}>ID</th>
                <th style={{ padding: '12px' }}>Phase</th>
                <th style={{ padding: '12px' }}>Started</th>
                <th style={{ padding: '12px' }}>Finished</th>
                <th style={{ padding: '12px' }}>Created</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr 
                  key={task.id} 
                  style={{ 
                    borderBottom: '1px solid #e5e7eb',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s'
                  }}
                  onClick={() => setSelectedTask(task)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#f9fafb';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <td style={{ padding: '12px', fontFamily: 'monospace' }}>{task.id}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      background: getPhaseColor(task.phase),
                      color: 'white',
                      fontSize: '12px',
                      fontWeight: 'bold'
                    }}>
                      {task.phase || 'Unknown'}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {task.startedAt ? new Date(task.startedAt).toLocaleString() : '-'}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {task.finishedAt ? new Date(task.finishedAt).toLocaleString() : '-'}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {task.createdAt ? new Date(task.createdAt).toLocaleString() : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal for displaying Python code */}
      {selectedTask && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setSelectedTask(null)}
        >
          <div 
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              maxWidth: '800px',
              width: '90%',
              maxHeight: '80vh',
              overflow: 'auto',
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0 }}>Python Code - {selectedTask.id}</h2>
              <button
                onClick={() => setSelectedTask(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '24px',
                  cursor: 'pointer',
                  color: '#6b7280',
                  padding: '0',
                  width: '30px',
                  height: '30px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ×
              </button>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <span style={{
                padding: '4px 8px',
                borderRadius: '4px',
                background: getPhaseColor(selectedTask.phase),
                color: 'white',
                fontSize: '12px',
                fontWeight: 'bold'
              }}>
                {selectedTask.phase || 'Unknown'}
              </span>
            </div>
            <div style={{
              backgroundColor: '#1e1e1e',
              color: '#d4d4d4',
              padding: '1rem',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '14px',
              whiteSpace: 'pre-wrap',
              overflow: 'auto',
              border: '1px solid #3e3e3e'
            }}>
              {selectedTask.pythonCode || 'No Python code available'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
