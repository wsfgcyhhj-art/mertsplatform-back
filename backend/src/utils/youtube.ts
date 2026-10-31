/**
 * Извлекает 11-значный идентификатор видео YouTube из различных форматов ссылок:
 * - https://www.youtube.com/watch?v=VIDEO_ID
 * - https://youtu.be/VIDEO_ID
 * - https://www.youtube.com/embed/VIDEO_ID
 * - https://www.youtube.com/shorts/VIDEO_ID
 * - Прямой ID
 */
export function extractYoutubeId(input: string): string | null {
  if (!input || typeof input !== 'string') return null;

  const trimmed = input.trim();

  // Если передан напрямую 11-символьный YouTube ID (буквы, цифры, _, -)
  if (/^[a-zA-Z0-9_-]{11}$/.test(trimmed)) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);

    // youtu.be/VIDEO_ID
    if (url.hostname === 'youtu.be' || url.hostname.endsWith('.youtu.be')) {
      const pathname = url.pathname.slice(1);
      const match = pathname.match(/^([a-zA-Z0-9_-]{11})/);
      return match ? match[1] : null;
    }

    // youtube.com / m.youtube.com / music.youtube.com
    if (url.hostname.includes('youtube.com')) {
      // /watch?v=VIDEO_ID
      const vParam = url.searchParams.get('v');
      if (vParam && /^[a-zA-Z0-9_-]{11}$/.test(vParam)) {
        return vParam;
      }

      // /embed/VIDEO_ID или /shorts/VIDEO_ID или /v/VIDEO_ID
      const pathParts = url.pathname.split('/').filter(Boolean);
      const embedIdx = pathParts.findIndex((part) =>
        ['embed', 'shorts', 'v'].includes(part)
      );
      if (embedIdx !== -1 && pathParts[embedIdx + 1]) {
        const potentialId = pathParts[embedIdx + 1];
        if (/^[a-zA-Z0-9_-]{11}$/.test(potentialId)) {
          return potentialId;
        }
      }
    }
  } catch {
    // Если строка не является валидным URL, пробуем regex по паттерну
    const regexMatch = trimmed.match(
      /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/
    );
    if (regexMatch && regexMatch[1]) {
      return regexMatch[1];
    }
  }

  return null;
}
