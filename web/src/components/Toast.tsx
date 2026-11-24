import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { useI18n } from '../i18n/i18n'

interface ToastMsg {
  id: number
  text: string
  action?: { label: string; run: () => void }
}

const Ctx = createContext<(text: string, action?: ToastMsg['action']) => void>(() => {})

/** One message at a time, announced politely; disappears after 8 s or on dismiss. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  const [msg, setMsg] = useState<ToastMsg | null>(null)
  const show = useCallback((text: string, action?: ToastMsg['action']) => {
    setMsg({ id: Date.now(), text, action })
  }, [])

  useEffect(() => {
    if (!msg) return
    const h = setTimeout(() => setMsg(null), 8000)
    return () => clearTimeout(h)
  }, [msg])

  const value = useMemo(() => show, [show])
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {msg && (
          <div className="toast" key={msg.id}>
            <span>{msg.text}</span>
            {msg.action && (
              <button
                type="button"
                className="btn btn-link"
                onClick={() => {
                  msg.action?.run()
                  setMsg(null)
                }}
              >
                {msg.action.label}
              </button>
            )}
            <button type="button" className="btn-icon" aria-label={t('toast.close')} onClick={() => setMsg(null)}>
              ×
            </button>
          </div>
        )}
      </div>
    </Ctx.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  return useContext(Ctx)
}
