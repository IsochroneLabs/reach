import { useI18n } from '../i18n/i18n'

/** Map slot (S2.2: plain background; the MapLibre map follows in S2.4). */
export function MapArea() {
  const { t } = useI18n()
  return <div className="map-placeholder" role="img" aria-label={t('map.label')} />
}
