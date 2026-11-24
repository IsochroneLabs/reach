import { useFit } from '../remote/fit'
import { useRefs } from '../remote/refs'
import { useI18n } from '../i18n/i18n'

/** Errors are shown, never hidden (docs/app_screens.md §1.5). */
export function StatusBanner() {
  const { t } = useI18n()
  const refs = useRefs()
  const fit = useFit()

  let text: string | null = null
  let retry: (() => void) | null = null
  if (refs.kind === 'error') {
    text = t('error.serverNoResult')
    retry = refs.retry
  } else if (fit.error?.kind === 'rate') {
    text = t('error.rateLimit', { s: fit.error.retryInS })
  } else if (fit.error?.kind === 'invalid') {
    text = t('error.invalidProfile')
  } else if (fit.error?.kind === 'server') {
    text = fit.data ? t('error.server') : t('error.serverNoResult')
    retry = fit.retry
  }
  if (!text) return null
  return (
    <div className="banner" role="alert" data-testid="status-banner">
      <span>{text}</span>
      {retry && (
        <button type="button" className="btn btn-small" onClick={retry}>
          {t('error.retry')}
        </button>
      )}
    </div>
  )
}
