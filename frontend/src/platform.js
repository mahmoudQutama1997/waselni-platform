export function isNativePlatform(){
  if (typeof window === 'undefined') return false;
  const protocol = window.location.protocol;
  return protocol === 'capacitor:' || protocol === 'ionic:' || Boolean(window.Capacitor?.isNativePlatform?.());
}
