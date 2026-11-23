/**
 * Marcador de carga con la forma del contenido (skeleton screen, NN/g): solo en la PRIMERA
 * carga de un panel; después los datos se actualizan en su sitio sin parpadeo.
 */
export function Skeleton({ rows = 3, height = 36 }: { rows?: number; height?: number }) {
  return (
    <div className="skeleton-list" role="status" aria-label="Cargando">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}
