import { USE_FIXTURES } from '../config'
import { useI18n } from '../i18n/i18n'
import { useRefs } from '../remote/refs'

/** Data date and sources under every result block (product: every number can be explained). */
export function DataNote() {
  const { t, date } = useI18n()
  const refs = useRefs()
  if (refs.kind !== 'ok') return null
  const s = refs.refs.meta.sources
  const osm = s.find((x) => x.source === 'osm')
  const gtfs = s.find((x) => x.source === 'gtfs')
  return (
    <p className="data-note" data-testid="data-note">
      {t('data.note', {
        osmDate: osm ? date(osm.date) : '–',
        gtfsTo: gtfs ? date(gtfs.valid_to ?? gtfs.date) : '–',
      })}
      {USE_FIXTURES && <> · <strong>{t('data.demo')}</strong></>}
    </p>
  )
}
