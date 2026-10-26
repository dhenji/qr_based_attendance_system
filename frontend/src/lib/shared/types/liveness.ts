// liveness.ts
// Evidence collected during the anti-spoof liveness pass: stored per attendance
// record (backend: attendance.liveness_evidence JSONB).
export interface LivenessEvidence {
  blinkDetected: boolean;
  headTurnLeft: boolean;
  headTurnRight: boolean;
  earSamples: number[];
  pnpEvidence: object;
  faceLandmarks?: any[];
  faceCount?: number;
  faceImage?: string;
}