import cls from '../../../../src/pages/LessonsPage/styles/lessons.module.scss'
import {LessonVideos} from "./LessonVideos.jsx";


export const LessonsPage = () => {

    return (
        <>

        <div className={cls.lessons}>
            <div className={cls.lessons_container}>
                <LessonVideos />
            </div>
        </div>


        </>
    )

}