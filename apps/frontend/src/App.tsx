import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Play, RefreshCw, X, XCircle } from 'lucide-react';
import Editor from '@monaco-editor/react';

interface Task {
  id: string;
  generateName: string;
  phase: string;
  startedAt: string;
  finishedAt: string;
  createdAt: string;
  pythonCode: string;
  message?: string;
}

interface LogEntry {
  node: string;
  pod: string;
  phase: string;
  logs: string;
}

// Memoized TaskRow component to prevent unnecessary re-renders
const TaskRow = React.memo(({ task, getPhaseColor, onTaskClick, onCancel }: {
  task: Task;
  getPhaseColor: (phase: string) => string;
  onTaskClick: (task: Task) => void;
  onCancel: (taskId: string) => void;
}) => {
  const canCancel = task.phase === 'Running' || task.phase === 'Pending';
  
  const handleMouseEnter = (e: React.MouseEvent<HTMLTableRowElement>) => {
    e.currentTarget.style.backgroundColor = '#f9fafb';
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLTableRowElement>) => {
    e.currentTarget.style.backgroundColor = 'transparent';
  };

  const handleCancelClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click
    onCancel(task.id);
  };

  return (
    <tr 
      style={{ 
        borderBottom: '1px solid #e5e7eb',
        cursor: 'pointer',
        transition: 'background-color 0.2s'
      }}
      onClick={() => onTaskClick(task)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
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
      <td style={{ padding: '12px' }}>
        {canCancel && (
          <button
            onClick={handleCancelClick}
            style={{
              display: 'flex',
              gap: '4px',
              alignItems: 'center',
              padding: '4px 8px',
              border: 'none',
              borderRadius: '4px',
              background: '#ef4444',
              color: 'white',
              fontSize: '12px',
              cursor: 'pointer',
              fontWeight: '500'
            }}
            title="Cancel task"
          >
            <XCircle size={14} /> Cancel
          </button>
        )}
      </td>
    </tr>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function - only re-render if task data actually changed
  return (
    prevProps.task.id === nextProps.task.id &&
    prevProps.task.phase === nextProps.task.phase &&
    prevProps.task.startedAt === nextProps.task.startedAt &&
    prevProps.task.finishedAt === nextProps.task.finishedAt &&
    prevProps.task.createdAt === nextProps.task.createdAt &&
    prevProps.onCancel === nextProps.onCancel
  );
});

TaskRow.displayName = 'TaskRow';

// Memoized TaskTable component
const TaskTable = React.memo(({ tasks, getPhaseColor, onTaskClick, onCancel }: {
  tasks: Task[];
  getPhaseColor: (phase: string) => string;
  onTaskClick: (task: Task) => void;
  onCancel: (taskId: string) => void;
}) => {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
      <thead>
        <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
          <th style={{ padding: '12px' }}>ID</th>
          <th style={{ padding: '12px' }}>Phase</th>
          <th style={{ padding: '12px' }}>Started</th>
          <th style={{ padding: '12px' }}>Finished</th>
          <th style={{ padding: '12px' }}>Created</th>
          <th style={{ padding: '12px' }}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            getPhaseColor={getPhaseColor}
            onTaskClick={onTaskClick}
            onCancel={onCancel}
          />
        ))}
      </tbody>
    </table>
  );
});

TaskTable.displayName = 'TaskTable';

// Stable function outside component to prevent re-renders
const getPhaseColor = (phase: string) => {
  switch (phase) {
    case 'Succeeded': return '#10b981';
    case 'Failed': return '#ef4444';
    case 'Running': return '#3b82f6';
    case 'Pending': return '#f59e0b';
    default: return '#6b7280';
  }
};

// Memoized TaskDialog component to prevent flickering
const TaskDialog = React.memo(({ 
  task, 
  activeTab, 
  setActiveTab, 
  taskLogs, 
  loadingLogs,
  onClose,
  onCancel
}: {
  task: Task;
  activeTab: 'code' | 'logs';
  setActiveTab: (tab: 'code' | 'logs') => void;
  taskLogs: LogEntry[];
  loadingLogs: boolean;
  onClose: () => void;
  onCancel: (taskId: string) => void;
}) => {
  const canCancel = task.phase === 'Running' || task.phase === 'Pending';
  
  return (
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
      onClick={onClose}
    >
      <div 
        style={{
          backgroundColor: 'white',
          borderRadius: '8px',
          padding: '2rem',
          maxWidth: '900px',
          width: '90%',
          height: '85vh',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Task Details - {task.id}</h2>
          <button
            onClick={onClose}
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
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '10px', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
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
            {task.message && (
              <span style={{
                padding: '4px 8px',
                borderRadius: '4px',
                background: '#fef3c7',
                color: '#92400e',
                fontSize: '12px',
                fontStyle: 'italic',
                maxWidth: '400px'
              }}>
                {task.message}
              </span>
            )}
          </div>
          {canCancel && (
            <button
              onClick={() => onCancel(task.id)}
              style={{
                display: 'flex',
                gap: '6px',
                alignItems: 'center',
                padding: '6px 12px',
                border: 'none',
                borderRadius: '4px',
                background: '#ef4444',
                color: 'white',
                fontSize: '14px',
                cursor: 'pointer',
                fontWeight: '500'
              }}
            >
              <XCircle size={16} /> Cancel Task
            </button>
          )}
        </div>
        
        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: '1rem' }}>
          <button
            onClick={() => setActiveTab('code')}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              borderBottom: activeTab === 'code' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'code' ? '#3b82f6' : '#6b7280',
              fontWeight: activeTab === 'code' ? 'bold' : 'normal'
            }}
          >
            Code
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            style={{
              padding: '10px 20px',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              borderBottom: activeTab === 'logs' ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === 'logs' ? '#3b82f6' : '#6b7280',
              fontWeight: activeTab === 'logs' ? 'bold' : 'normal'
            }}
          >
            Logs {loadingLogs && '...'}
          </button>
        </div>

        {/* Tab Content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          {activeTab === 'code' ? (
            <div style={{
              backgroundColor: '#1e1e1e',
              color: '#d4d4d4',
              padding: '1rem',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '14px',
              whiteSpace: 'pre-wrap',
              overflow: 'auto',
              border: '1px solid #3e3e3e',
              flex: 1,
              minHeight: 0
            }}>
              {task.pythonCode || 'No Python code available'}
            </div>
          ) : (
            <div style={{
              backgroundColor: '#1e1e1e',
              color: '#d4d4d4',
              padding: '1rem',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '14px',
              whiteSpace: 'pre-wrap',
              overflow: 'auto',
              border: '1px solid #3e3e3e',
              flex: 1,
              minHeight: 0
            }}>
              {loadingLogs ? (
                <div style={{ color: '#9ca3af' }}>Loading logs...</div>
              ) : taskLogs.length === 0 ? (
                <div style={{ color: '#9ca3af' }}>No logs available yet. The task may still be starting.</div>
              ) : (
                taskLogs.map((logEntry, index) => (
                  <div key={index} style={{ marginBottom: '1.5rem' }}>
                    <div style={{ 
                      color: '#60a5fa', 
                      marginBottom: '0.5rem',
                      paddingBottom: '0.5rem',
                      borderBottom: '1px solid #374151'
                    }}>
                      <strong>Pod:</strong> {logEntry.pod} | <strong>Node:</strong> {logEntry.node} | <strong>Phase:</strong> {logEntry.phase}
                    </div>
                    <div style={{ 
                      color: '#d4d4d4',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word'
                    }}>
                      {logEntry.logs}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render if task ID changed, phase changed, activeTab changed, or logs actually changed
  // Quick check: if lengths differ, logs changed
  if (prevProps.taskLogs.length !== nextProps.taskLogs.length) {
    return false; // Re-render needed
  }
  
  // Deep comparison only if on logs tab
  if (prevProps.activeTab === 'logs' && nextProps.activeTab === 'logs') {
    // Check if any log entry actually changed
    const logsChanged = prevProps.taskLogs.some((prevLog, i) => {
      const nextLog = nextProps.taskLogs[i];
      return !nextLog || 
             prevLog.logs !== nextLog.logs || 
             prevLog.phase !== nextLog.phase ||
             prevLog.node !== nextLog.node ||
             prevLog.pod !== nextLog.pod;
    });
    
    if (logsChanged) {
      return false; // Re-render needed
    }
  }
  
  // For other changes, use standard comparison
  return (
    prevProps.task.id === nextProps.task.id &&
    prevProps.task.phase === nextProps.task.phase &&
    prevProps.task.pythonCode === nextProps.task.pythonCode &&
    prevProps.activeTab === nextProps.activeTab &&
    prevProps.loadingLogs === nextProps.loadingLogs &&
    prevProps.onCancel === nextProps.onCancel
  );
});

TaskDialog.displayName = 'TaskDialog';

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'code' | 'logs'>('code');
  const [taskLogs, setTaskLogs] = useState<LogEntry[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [pythonCode, setPythonCode] = useState("print('Processing task in Kind...')");
  const [submitting, setSubmitting] = useState(false);
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // Get selected task from tasks array by ID (stable reference)
  const selectedTask = useMemo(() => {
    if (!selectedTaskId) return null;
    return tasks.find(t => t.id === selectedTaskId) || null;
  }, [selectedTaskId, tasks]);

  // Helper function to check if tasks have changed
  const tasksChanged = (oldTasks: Task[], newTasks: Task[]): boolean => {
    if (oldTasks.length !== newTasks.length) return true;
    
    // Create maps for quick comparison
    const oldMap = new Map(oldTasks.map(t => [t.id, t]));
    
    for (const newTask of newTasks) {
      const oldTask = oldMap.get(newTask.id);
      if (!oldTask) return true;
      
      // Compare relevant fields that might change
      if (
        oldTask.phase !== newTask.phase ||
        oldTask.startedAt !== newTask.startedAt ||
        oldTask.finishedAt !== newTask.finishedAt
      ) {
        return true;
      }
    }
    
    return false;
  };

  const fetchTasks = useCallback(async (isInitial = false) => {
    try {
      if (isInitial) {
        setInitialLoading(true);
      }
      const res = await fetch(`${apiUrl}/api/v1/tasks`);
      const data = await res.json();
      const newTasks = data.tasks || [];
      
      // Only update state if tasks actually changed
      setTasks(prevTasks => {
        if (tasksChanged(prevTasks, newTasks)) {
          return newTasks;
        }
        return prevTasks; // Return previous to prevent re-render
      });
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      if (isInitial) {
        setInitialLoading(false);
      }
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchTasks(true);
    // No automatic refresh - user can manually refresh using the Refresh button
  }, [fetchTasks]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const lastLogsHashRef = useRef<string>('');

  // Helper to create a hash of logs for comparison
  const logsHash = useCallback((logs: LogEntry[]): string => {
    return logs.map(l => `${l.node}:${l.pod}:${l.phase}:${l.logs.length}:${l.logs.slice(-100)}`).join('|');
  }, []);

  // Helper to check if logs actually changed
  const logsChanged = useCallback((oldLogs: LogEntry[], newLogs: LogEntry[]): boolean => {
    if (oldLogs.length !== newLogs.length) return true;
    return oldLogs.some((oldLog, i) => {
      const newLog = newLogs[i];
      return !newLog || oldLog.logs !== newLog.logs || oldLog.phase !== newLog.phase;
    });
  }, []);

  // WebSocket connection for real-time logs
  const connectWebSocket = useCallback((taskId: string) => {
    // Reset hash when connecting
    lastLogsHashRef.current = '';
    // Close existing connection if any
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clear any pending reconnection
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Convert http:// to ws:// or https:// to wss://
    const wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws/tasks/${taskId}/logs`;
    
    setLoadingLogs(true);
    reconnectAttempts.current = 0;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected for task:', taskId);
        setLoadingLogs(false);
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          if (message.type === 'logs') {
            const newLogs = message.data || [];
            const newHash = logsHash(newLogs);
            
            // Only update if logs actually changed
            setTaskLogs(prevLogs => {
              if (newHash !== lastLogsHashRef.current && logsChanged(prevLogs, newLogs)) {
                lastLogsHashRef.current = newHash;
                return newLogs;
              }
              return prevLogs; // No change, return previous to prevent re-render
            });
            setLoadingLogs(false);
          } else if (message.type === 'complete') {
            // Don't update logs on complete, just stop loading
            setLoadingLogs(false);
            // Optionally close connection when complete
            // ws.close();
          } else if (message.type === 'error') {
            console.error('WebSocket error:', message.message);
            setTaskLogs(prevLogs => {
              if (prevLogs.length === 0) {
                return [{
                  node: 'error',
                  pod: 'N/A',
                  phase: 'Error',
                  logs: `Error: ${message.message}`
                }];
              }
              return prevLogs;
            });
            setLoadingLogs(false);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setLoadingLogs(false);
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        wsRef.current = null;
        
        // Only attempt reconnection if not a normal closure and we have a selected task
        if (event.code !== 1000 && selectedTaskId === taskId && reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000); // Exponential backoff, max 10s
          
          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})...`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket(taskId);
          }, delay);
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          setTaskLogs(prevLogs => {
            if (prevLogs.length === 0) {
              return [{
                node: 'error',
                pod: 'N/A',
                phase: 'Error',
                logs: 'Connection lost. Maximum reconnection attempts reached.'
              }];
            }
            return prevLogs;
          });
          setLoadingLogs(false);
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      setLoadingLogs(false);
      setTaskLogs([{
        node: 'error',
        pod: 'N/A',
        phase: 'Error',
        logs: `Failed to connect: ${error instanceof Error ? error.message : 'Unknown error'}`
      }]);
    }
  }, [apiUrl, selectedTaskId, logsHash, logsChanged]);

  const disconnectWebSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    reconnectAttempts.current = 0;
  }, []);

  useEffect(() => {
    if (selectedTask && activeTab === 'logs') {
      // Reset logs hash when switching to logs tab
      lastLogsHashRef.current = '';
      // Connect WebSocket for real-time logs
      connectWebSocket(selectedTask.id);
      
      return () => {
        // Cleanup: disconnect WebSocket when switching tabs or closing dialog
        disconnectWebSocket();
      };
    } else {
      // Disconnect when switching away from logs tab
      disconnectWebSocket();
      setTaskLogs([]);
      lastLogsHashRef.current = '';
    }
  }, [selectedTaskId, activeTab, selectedTask, connectWebSocket, disconnectWebSocket, logsHash, logsChanged]);

  const runTask = async () => {
    try {
      setSubmitting(true);
      const res = await fetch(`${apiUrl}/api/v1/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ pythonCode }),
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to submit task');
      }
      
      const data = await res.json();
      alert('Started Workflow: ' + data.id);
      setShowSubmitModal(false);
      // Refresh the task list
      fetchTasks();
    } catch (error) {
      console.error('Failed to submit task:', error);
      alert('Failed to submit task: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      setSubmitting(false);
    }
  };

  const cancelTask = useCallback(async (taskId: string) => {
    if (!confirm('Are you sure you want to cancel this task?')) {
      return;
    }

    try {
      const res = await fetch(`${apiUrl}/api/v1/tasks/${taskId}`, {
        method: 'DELETE',
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to cancel task');
      }
      
      // If the cancelled task is the selected one, close the dialog
      if (selectedTaskId === taskId) {
        setSelectedTaskId(null);
        setActiveTab('code');
        setTaskLogs([]);
        disconnectWebSocket();
      }
      
      // Refresh the task list
      fetchTasks();
      alert('Task cancelled successfully');
    } catch (error) {
      console.error('Failed to cancel task:', error);
      alert('Failed to cancel task: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }, [apiUrl, selectedTaskId, fetchTasks, disconnectWebSocket]);

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Argo Workflow Manager</h1>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            onClick={() => fetchTasks(true)} 
            disabled={initialLoading}
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
            onClick={() => setShowSubmitModal(true)} 
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
        {initialLoading && tasks.length === 0 ? (
          <p>Loading tasks...</p>
        ) : tasks.length === 0 ? (
          <p>No tasks found. Submit a task to get started.</p>
        ) : (
          <TaskTable 
            tasks={tasks} 
            getPhaseColor={getPhaseColor}
            onTaskClick={(task) => setSelectedTaskId(task.id)}
            onCancel={cancelTask}
          />
        )}
      </div>

      {/* Modal for displaying task details */}
      {selectedTask && (
        <TaskDialog
          task={selectedTask}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          taskLogs={taskLogs}
          loadingLogs={loadingLogs}
          onClose={() => {
            setSelectedTaskId(null);
            setActiveTab('code');
            setTaskLogs([]);
          }}
          onCancel={cancelTask}
        />
      )}

      {/* Modal for submitting new task with code editor */}
      {showSubmitModal && (
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
            zIndex: 1001
          }}
          onClick={() => !submitting && setShowSubmitModal(false)}
        >
          <div 
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '2rem',
              maxWidth: '900px',
              width: '90%',
              maxHeight: '85vh',
              overflow: 'auto',
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
              display: 'flex',
              flexDirection: 'column'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h2 style={{ margin: 0 }}>Write Python Code to Execute</h2>
              <button
                onClick={() => !submitting && setShowSubmitModal(false)}
                disabled={submitting}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  color: '#6b7280',
                  padding: '0',
                  width: '30px',
                  height: '30px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  opacity: submitting ? 0.5 : 1
                }}
              >
                <X size={24} />
              </button>
            </div>
            
            <div style={{ marginBottom: '1rem', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                onClick={() => setPythonCode(`import json
import os
from datetime import datetime

# Create results directory if it doesn't exist
results_dir = "/mnt/results"
os.makedirs(results_dir, exist_ok=True)

# Generate some data to save
task_id = os.getenv("ARGO_WORKFLOW_NAME", "unknown-task")
result_data = {
    "task_id": task_id,
    "timestamp": datetime.now().isoformat(),
    "status": "completed",
    "result": "Task executed successfully!",
    "data": {
        "processed_items": 42,
        "computation_time": 1.23,
        "output": "Sample output data"
    }
}

# Write to file
output_file = os.path.join(results_dir, f"{task_id}_result.json")
with open(output_file, "w") as f:
    json.dump(result_data, f, indent=2)

print(f"Results saved to {output_file}")
print(f"Data: {json.dumps(result_data, indent=2)}")`)}
                disabled={submitting}
                style={{
                  padding: '8px 16px',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  border: '1px solid #3b82f6',
                  borderRadius: '4px',
                  background: 'white',
                  color: '#3b82f6',
                  fontSize: '14px',
                  opacity: submitting ? 0.5 : 1
                }}
              >
                📝 Load: Write to PV
              </button>
              <button
                onClick={() => setPythonCode(`import json
import os
from datetime import datetime

# Read from results directory
results_dir = "/mnt/results"

if not os.path.exists(results_dir):
    print(f"Error: Results directory {results_dir} does not exist")
    exit(1)

# List all result files
result_files = [f for f in os.listdir(results_dir) if f.endswith("_result.json")]

if not result_files:
    print("No result files found in /mnt/results")
    print(f"Directory contents: {os.listdir(results_dir)}")
    exit(0)

print(f"Found {len(result_files)} result file(s):")
print("-" * 50)

# Read and display each result file
for result_file in sorted(result_files):
    file_path = os.path.join(results_dir, result_file)
    print(f"\\nReading: {result_file}")
    print("-" * 50)
    
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error reading {result_file}: {e}")

print("\\n" + "=" * 50)
print(f"Successfully read {len(result_files)} result file(s)")`)}
                disabled={submitting}
                style={{
                  padding: '8px 16px',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  border: '1px solid #10b981',
                  borderRadius: '4px',
                  background: 'white',
                  color: '#10b981',
                  fontSize: '14px',
                  opacity: submitting ? 0.5 : 1
                }}
              >
                📖 Load: Read from PV
              </button>
            </div>
            
            <div style={{ 
              flex: 1,
              minHeight: '400px',
              border: '1px solid #e5e7eb',
              borderRadius: '4px',
              overflow: 'hidden',
              marginBottom: '1.5rem'
            }}>
              <Editor
                height="400px"
                defaultLanguage="python"
                value={pythonCode}
                onChange={(value) => setPythonCode(value || '')}
                theme="vs-dark"
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setShowSubmitModal(false)}
                disabled={submitting}
                style={{
                  padding: '10px 20px',
                  cursor: submitting ? 'not-allowed' : 'pointer',
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                  background: 'white',
                  opacity: submitting ? 0.5 : 1
                }}
              >
                Cancel
              </button>
              <button
                onClick={runTask}
                disabled={submitting || !pythonCode.trim()}
                style={{
                  padding: '10px 20px',
                  cursor: (submitting || !pythonCode.trim()) ? 'not-allowed' : 'pointer',
                  border: 'none',
                  borderRadius: '4px',
                  background: '#3b82f6',
                  color: 'white',
                  opacity: (submitting || !pythonCode.trim()) ? 0.5 : 1,
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'center'
                }}
              >
                {submitting ? 'Submitting...' : (
                  <>
                    <Play size={18} /> Submit Task
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
