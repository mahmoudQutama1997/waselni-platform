import mark from '../assets/waselni-mark.svg'
import monoMark from '../assets/waselni-mark-mono.svg'

type Props = {
  /** Wordmark text. Pass an empty string for the mark alone. */
  name?: string
  /** `mono` keeps the transparent glyph for dark surfaces. */
  tone?: 'color' | 'mono'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

/**
 * The single Waselni logo used by every portal: one vector mark plus the
 * localized wordmark, so no screen falls back to a bare letter.
 */
export default function Brand({ name = 'وصلني', tone = 'color', size = 'md', className = '' }: Props) {
  const source = tone === 'mono' ? monoMark : mark
  return (
    <span className={`brand-logo brand-logo--${size} ${className}`.trim()}>
      <img src={source} alt="" aria-hidden="true" decoding="async" width="48" height="48" />
      {name ? <b>{name}</b> : null}
    </span>
  )
}
