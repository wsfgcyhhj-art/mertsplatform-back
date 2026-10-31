/**
 * Проверяет, что ссылка является валидным URL на github.com
 * Принимает форматы: https://github.com/user/repo, http://github.com/user/repo/pull/1 и т.д.
 */
export function isValidGithubUrl(input: string): boolean {
  if (!input || typeof input !== 'string') return false;

  try {
    const url = new URL(input.trim());
    const isGithubHost = url.hostname === 'github.com' || url.hostname === 'www.github.com';
    if (!isGithubHost) return false;

    // Путь должен содержать как минимум пользователя и репозиторий: /owner/repo
    const pathParts = url.pathname.split('/').filter(Boolean);
    return pathParts.length >= 2;
  } catch {
    return false;
  }
}
