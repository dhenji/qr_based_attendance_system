// features/attendance/service.ts
// Attendance evidence submission, records listing

// MOCK flag
const MOCK = true;

// Submit attendance evidence (photo + GPS + liveness)
export const submitEvidence = async (evidence: {
	sessionId: number;
	studentId: string;
	studentNumber: string;
	gps: { lat: number; lng: number; accuracy: number };
	livenessEvidence: {
		blinkDetected: boolean;
		headTurnLeft: boolean;
		headTurnRight: boolean;
		earSamples: number[];
		pnpEvidence: object;
	};
	faceMatchScore: number;
	scannedAt: string;
}) => {
	if (MOCK) {
		const statuses = ['present', 'late', 'rejected'] as const;
		const via = ['qr', 'gps', 'face'] as const;
		return {
			id: Math.floor(Math.random() * 10000) + 1,
			sessionId: evidence.sessionId,
			studentId: evidence.studentId,
			status: statuses[Math.floor(Math.random() * statuses.length)],
			scannedAt: evidence.scannedAt,
			scannedVia: via[Math.floor(Math.random() * via.length)],
			faceMatchScore: evidence.faceMatchScore,
		};
	}
	return {
		id: Math.floor(Math.random() * 10000) + 1,
		sessionId: evidence.sessionId,
		studentId: evidence.studentId,
		status: 'present' as const,
		scannedAt: evidence.scannedAt,
		scannedVia: 'qr' as const,
		faceMatchScore: evidence.faceMatchScore,
	};
};

// List attendance records (professor view)
export const listRecords = async (_params?: {
	sessionId?: number;
	status?: string;
	from?: string;
	to?: string;
}) => {
	if (MOCK) {
		return {
			items: [
				{
					id: 1,
					sessionId: 1,
					studentId: 'student-1',
					studentNumber: 'STU-001',
					status: 'present' as const,
					originalStatus: undefined,
					scannedAt: new Date(Date.now() - 86400000).toISOString(),
					scannedVia: 'qr' as const,
					faceMatchScore: 98.5,
					excuseReason: undefined,
				},
			],
			total: 1,
			page: 1,
			size: 20,
		};
	}
	return { items: [], total: 0, page: 1, size: 20 };
};
