export interface FlowStep {
  id: string;
  name: string;
  pythonCode: string;
  dependencies?: string;
  requirementsFile?: string;
  systemDependencies?: string;
  position: { x: number; y: number };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

export interface Flow {
  id: string;
  name: string;
  description?: string;
  steps: FlowStep[];
  edges: FlowEdge[];
  status: 'draft' | 'saved' | 'running' | 'completed' | 'failed';
  createdAt: string;
  updatedAt: string;
}

