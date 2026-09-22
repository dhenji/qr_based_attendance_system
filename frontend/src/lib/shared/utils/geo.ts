// geo.ts
// Geofence math: Haversine distance between two coordinates, then a radius check.

// Great-circle distance between (lat1, lng1) and (lat2, lng2) in km.
export const calculateDistance = (
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number => {
  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c; // Returns km
};

// True when the student's position is within the classroom's radius (metres).
export const isWithinGeofence = (
  studentLat: number,
  studentLng: number,
  centerLat: number,
  centerLng: number,
  radiusMetres: number
): boolean => {
  const distanceKm = calculateDistance(studentLat, studentLng, centerLat, centerLng);
  const distanceMetres = distanceKm * 1000;
  return distanceMetres <= radiusMetres;
};