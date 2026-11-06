/**
 * Вычисляет SHA-256 хеш строки пароля на стороне клиента через нативный Web Crypto API.
 * Возвращает 64-символьную hex-строку.
 * 
 * @param {string} password 
 * @returns {Promise<string>}
 */
export async function hashPasswordClient(password) {
  if (!password || typeof password !== 'string') {
    return '';
  }

  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}
