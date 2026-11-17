let token = null;
export const getAccessToken = () => token;
export const setAccessToken = value => { token = value || null; };
// Remove tokens persisted by older versions.
for (const key of ['accessToken', 'token', 'user-merts-chat']) localStorage.removeItem(key);
sessionStorage.removeItem('accessToken');
