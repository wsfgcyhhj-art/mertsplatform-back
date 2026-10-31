import {persist} from "zustand/middleware";
import {create} from "zustand";

export const useProfile = create(persist((set) => ({
    bannerUrlImg: '',
    addBannerUrlImg: (url) => set({ bannerUrlImg: url }),
    profileUrlImg: '',
    addProfileUrlImg: (url) => set({ profileUrlImg: url }),
    profileCustomInfo: {
        name: 'пусто',
        tg: 'пусто',
        group: 'пусто'
    },
    customProfileCustomInfo: (name,tg,group) => set({
        profileCustomInfo: {
            name: name,
            tg: tg,
            group: group,
        }
    })
}), {name: 'profile-user-merts-chat'}));