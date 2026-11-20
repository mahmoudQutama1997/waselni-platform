import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * Catches render/lifecycle errors so one broken screen shows a readable message
 * instead of unmounting the whole React tree (the "white screen").
 *
 * `resetKey` (usually the current pathname) clears the trapped error when the
 * user navigates somewhere else, so a single failing page never locks the app.
 *
 * The fallback never claims that the user's data is intact: the boundary cannot
 * verify that, so it only states what happened and what the user can do next.
 */
type Props = {
  children: ReactNode
  lang?: string
  resetKey?: string
  /** Full-page fallback for the root boundary (no sidebar/header around it). */
  fullPage?: boolean
}

type State = { error: Error | null }

const COPY: Record<'ar' | 'he' | 'en', {
  title: string
  body: string
  retry: string
  reload: string
  details: string
}> = {
  ar: {
    title: 'تعذّر عرض هذه الصفحة',
    body: 'حدث خطأ غير متوقع أثناء عرض هذه الشاشة. جرّب إعادة المحاولة، وإن استمرت المشكلة أعد تحميل الصفحة أو عُد إلى بقية الخدمات. التفاصيل التقنية مسجّلة في وحدة تحكم المتصفح.',
    retry: 'إعادة المحاولة',
    reload: 'إعادة تحميل الصفحة',
    details: 'تفاصيل تقنية',
  },
  he: {
    title: 'לא ניתן להציג את המסך הזה',
    body: 'אירעה שגיאה בלתי צפויה בזמן הצגת המסך. נסו שוב, ואם הבעיה נמשכת רעננו את הדף או חזרו לשאר השירותים. הפרטים הטכניים נרשמו בקונסולת הדפדפן.',
    retry: 'נסה שוב',
    reload: 'טעינת הדף מחדש',
    details: 'פרטים טכניים',
  },
  en: {
    title: 'This screen could not be shown',
    body: 'Something unexpected went wrong while rendering this screen. Try again, and if the problem persists reload the page or go back to the other services. Technical details are logged in the browser console.',
    retry: 'Try again',
    reload: 'Reload page',
    details: 'Technical details',
  },
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidUpdate(previous: Props) {
    // A different route means a different screen: stop showing the old failure.
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep a real diagnostic trail in the console instead of failing silently.
    console.error('Waselni UI error:', error, info.componentStack)
  }

  private retry = () => this.setState({ error: null })

  private reload = () => window.location.reload()

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const lang = this.props.lang === 'he' || this.props.lang === 'en' ? this.props.lang : 'ar'
    const copy = COPY[lang]
    const dir = lang === 'ar' || lang === 'he' ? 'rtl' : 'ltr'

    return (
      <div className={`ui-error ${this.props.fullPage ? 'ui-error--page' : ''}`} dir={dir} role="alert">
        <div className="ui-error-card">
          <span className="ui-error-mark" aria-hidden="true">!</span>
          <h2>{copy.title}</h2>
          <p>{copy.body}</p>
          <div className="ui-error-actions">
            <button type="button" onClick={this.retry}>{copy.retry}</button>
            <button type="button" className="secondary" onClick={this.reload}>{copy.reload}</button>
          </div>
          <details className="ui-error-detail">
            <summary>{copy.details}</summary>
            <code>{error.message || String(error)}</code>
          </details>
        </div>
      </div>
    )
  }
}
