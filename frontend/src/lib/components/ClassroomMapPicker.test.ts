import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import ClassroomMapPicker from './ClassroomMapPicker.svelte';

vi.mock('leaflet', () => {
	const mapObj = {
		setView: vi.fn().mockReturnThis(),
		on: vi.fn(),
		invalidateSize: vi.fn(),
		remove: vi.fn(),
		getCenter: vi.fn(() => ({ lat: 1, lng: 2 })),
		getZoom: vi.fn(() => 16)
	};
	return {
		default: {
			map: vi.fn(() => mapObj),
			tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
			marker: vi.fn(() => {
				const m = { setLatLng: vi.fn(), getLatLng: () => ({ lat: 1, lng: 2 }), on: vi.fn(), remove: vi.fn(), addTo: vi.fn() };
				m.addTo.mockReturnValue(m);
				return m;
			}),
			circle: vi.fn(() => ({ remove: vi.fn(), addTo: vi.fn(() => ({})) })),
			divIcon: vi.fn(() => ({})),
			Icon: { Default: { prototype: {}, mergeOptions: vi.fn() } }
		}
	};
});

vi.mock('$lib/shared/utils/geo', () => ({
	searchLocation: vi.fn(async () => []),
	requestBestPosition: vi.fn(),
	reverseGeocode: vi.fn(async () => null),
	GPS_HARD_FLOOR_METERS: 1000
}));

import { requestBestPosition } from '$lib/shared/utils/geo';

describe('ClassroomMapPicker', () => {
	beforeEach(() => {
		vi.mocked(requestBestPosition).mockReset();
	});

	it('shows error when locate clicked before map mounts', async () => {
		const onChange = vi.fn();
		render(ClassroomMapPicker, { props: { lat: null, lng: null, onChange } });
		// click before onMount flushes (map/leaflet null)
		const btn = screen.getByRole('button', { name: /use my location/i });
		await fireEvent.click(btn);
		expect(screen.getByRole('alert')).toHaveTextContent(/map is still loading/i);
		expect(onChange).not.toHaveBeenCalled();
	});

	it('sets gpsError and leaves coords unchanged on coarse rejection', async () => {
		const onChange = vi.fn();
		const err = new Error('too low');
		(err as any).message = 'Unable to get a sufficiently accurate location.';
		vi.mocked(requestBestPosition).mockRejectedValue(err);
		render(ClassroomMapPicker, { props: { lat: 5, lng: 6, onChange } });
		// wait for mount
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		const btn = screen.getByRole('button', { name: /use my location/i });
		await fireEvent.click(btn);
		await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
		expect(onChange).not.toHaveBeenCalled();
	});

	it('updates lat/lng and calls onChange on success', async () => {
		const onChange = vi.fn();
		vi.mocked(requestBestPosition).mockResolvedValue({ lat: 10, lng: 20, accuracy: 30, timestamp: 1 });
		render(ClassroomMapPicker, { props: { lat: null, lng: null, onChange } });
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		await new Promise((r) => setTimeout(r, 0));
		const btn = screen.getByRole('button', { name: /use my location/i });
		await fireEvent.click(btn);
		await waitFor(() => expect(onChange).toHaveBeenCalledWith(10, 20));
	});
});