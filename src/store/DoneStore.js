import {create} from "zustand";
import {persist} from "zustand/middleware";

export const useDone = create(persist((set) => ({
    doneTask: [],
    addDone: (id) => set((state) => ({
        doneTask: state.doneTask.includes(id) ? state.doneTask.filter(t => t.id !== id) : [...state.doneTask, id]
    }))
}), {name: 'doneTask'}))