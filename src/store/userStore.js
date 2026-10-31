import {persist} from "zustand/middleware";
import {create} from "zustand";

export const useFindUser = create(persist((set) => ({
    userInfo: null,
    accessToken: null,
    addUser: (user, token = null) => set({
        userInfo: user,
        accessToken: token || user?.accessToken || null
    }),
    removeUser: () => set({userInfo: null, accessToken: null}),
}), {name: 'user-merts-chat'}));
