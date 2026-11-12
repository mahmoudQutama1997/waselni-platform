import { useEffect, useState } from 'react';
import { mediaUrl } from '../api';

/**
 * Renders a backend image and keeps failures visible instead of showing a
 * silent broken-image glyph. The backend URL is shown in the tooltip and the
 * HTTP status is surfaced when it can be checked.
 */
export default function SafeImage({ src, alt = '', className = '', loading = 'lazy', decoding = 'async', ...rest }) {
  const resolved = mediaUrl(src);
  const [failed, setFailed] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    setFailed('');
    setStatus('');
  }, [resolved]);

  async function reportFailure() {
    let code = '';
    if (/^https?:/i.test(resolved)) {
      try {
        const response = await fetch(resolved, { method: 'HEAD' });
        code = String(response.status);
      } catch {
        code = 'NET';
      }
    } else {
      code = 'ERR';
    }
    console.warn('[waselni:image] failed to load', resolved, code);
    setStatus(code);
    setFailed(resolved);
  }

  if (!resolved) {
    return (
      <span className={`image-missing ${className}`.trim()} role="img" aria-label={alt} title="لا توجد صورة محفوظة لهذا العنصر">
        <b>—</b>
      </span>
    );
  }

  if (failed) {
    return (
      <span className={`image-missing ${className}`.trim()} role="img" aria-label={alt} title={`تعذر تحميل الصورة: ${failed}`}>
        <b>!</b>
        <small>{status || 'IMG'}</small>
      </span>
    );
  }

  return (
    <img
      {...rest}
      src={resolved}
      alt={alt}
      className={className}
      loading={loading}
      decoding={decoding}
      onError={reportFailure}
    />
  );
}
