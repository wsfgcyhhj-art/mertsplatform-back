import {persist} from "zustand/middleware";
import {create} from "zustand";

export const useFindUser = create(persist((set) => ({
    userInfo: null,
    accessToken: null,
    addUser: (user, token = null) => set((state) => {
        const resolvedToken =
            token ||
            user?.accessToken ||
            state.accessToken ||
            localStorage.getItem('accessToken') ||
            localStorage.getItem('token') ||
            sessionStorage.getItem('accessToken') ||
            null;

        if (resolvedToken) {
            localStorage.setItem('accessToken', resolvedToken);
        }

        return {
            userInfo: user ? { ...user, accessToken: resolvedToken } : null,
            accessToken: resolvedToken,
        };
    }),
    removeUser: () => {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('token');
        sessionStorage.removeItem('accessToken');
        set({userInfo: null, accessToken: null});
    },
}), {name: 'user-merts-chat'}));
