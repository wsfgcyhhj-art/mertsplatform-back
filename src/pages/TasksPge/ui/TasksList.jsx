import cls from '../styles/task.module.scss'
import {TaskS} from "./Tasks.jsx";

export const TasksList = () => {
    return (
        <>

            <div className={cls.task}>
                <div className={cls.task_content}>
                    <TaskS/>
                </div>
            </div>


        </>
    )
}