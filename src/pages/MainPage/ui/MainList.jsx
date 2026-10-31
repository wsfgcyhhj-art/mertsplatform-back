import {useFindUser} from "../../../store/userStore.js";
import cls from '../../../../src/pages/MainPage/styles/main.module.scss'
import {MainStudyInfo} from "./MainStudyInfo.jsx";

export const MainList = () => {

    const {  userInfo } = useFindUser()

    return (
        <div className={cls.main}>
            <div className={cls.main_container}>
                <div className={cls.title}>
                    <h1>Здравствуйте, {userInfo?.login}👋</h1>
                </div>
                <div>
                    <MainStudyInfo/>
                </div>
            </div>
        </div>
    )
}
