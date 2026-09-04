export interface LivenessEvidence {
  blinkDetected: boolean;
  headTurnLeft: boolean;
  headTurnRight: boolean;
  earSamples: number[];
  pnpEvidence: object;
}