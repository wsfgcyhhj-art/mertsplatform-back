import {create} from "zustand";

export const useHistory = create((set) => ({
    historys: null,
    toggleHistory: (value) => set({historys: value})
}))