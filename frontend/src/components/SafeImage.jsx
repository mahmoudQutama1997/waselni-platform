import { useEffect, useState } from 'react';
import { mediaUrl } from '../api';

/**
 * Renders a backend image and keeps failures visible instead of showing a
 * silent broken-image glyph. The backend URL is shown in the tooltip.
 *
 * Failure detection stays on the <img> element on purpose: probing the media
 * URL with fetch() turns every broken image into a cross-origin CORS/ORB
 * console error, because media hosts do not send Access-Control-Allow-Origin.
 */
export default function SafeImage({ src, alt = '', className = '', loading = 'lazy', decoding = 'async', ...rest }) {
  const resolved = mediaUrl(src);
  const [failed, setFailed] = useState('');

  useEffect(() => {
    setFailed('');
  }, [resolved]);

  function reportFailure() {
    console.warn('[waselni:image] failed to load', resolved);
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
        <small>IMG</small>
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
