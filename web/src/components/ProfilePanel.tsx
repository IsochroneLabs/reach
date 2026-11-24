import { useI18n } from '../i18n/i18n'

/** Shell of the profile panel (S2.2); the editable panel follows in S2.3. */
export function ProfilePanel({ onClose }: { onClose?: () => void }) {
  const { t } = useI18n()
  return (
    <section className="panel" aria-labelledby="profile-title">
      <div className="panel-head">
        <h2 id="profile-title">{t('profile.title')}</h2>
        {onClose && (
          <button type="button" className="btn-icon" aria-label={t('profile.close')} onClick={onClose}>
            ×
          </button>
        )}
      </div>
      <p className="muted">{t('status.loading')}</p>
    </section>
  )
}

/** Programme hint above the sheet tabs (S2.3). */
export function ProgrammeHint(_: { compact?: boolean; onOpen?: () => void }) {
  void _
  return null
}
