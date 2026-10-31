import cls from '../../../../src/pages/MainPage/styles/main.module.scss'
import img from '../../../images/mainpageImg.webp'
import imgs from '../../../images/ularsImg.webp'
import {FaArrowRight, FaBook} from "react-icons/fa";
import {useFindUser} from "../../../store/userStore.js";
import {useNavigate} from "react-router-dom";


export const MainStudyInfo = () => {

    const {userInfo} = useFindUser()

    const navigate = useNavigate();
    return (
        <>
            <div className={cls.mainStudyInfo}>
                <div className={cls.mainStudyInfo_items}>
                    <div  className={cls.continue}  style={{backgroundImage: `url(${img})`}}>
                        <div className={cls.continue_content} >
                            <div className={cls.continue_title}>
                                <h2>Дорогой <span>{userInfo?.login}</span>!</h2>
                                <p>Добро пожаловать в MertsPlatform</p>
                            </div>
                            <div className={cls.continue_footer}>
                                <p>Обязательно ознакомьтесь с инструкцией перед началом обучения, чтобы всё было максимально понятно и эффективно.</p>
                                <a href="/MertsPlatform_Instruction.pdf" download>
                                    <button><FaBook /> Ознакомиться с инструкцией <FaArrowRight /></button>
                                </a>
                            </div>
                        </div>
                    </div>

                    <div className={cls.team} >
                        <div className={cls.team_content}>
                            <div className={cls.team_title}>
                                <span className={cls.s}>Основатель</span>
                                <h2>Кто работал над сайтом</h2>
                                <p>Благодаря ему MertsPlatform стал тем местом, где ты сейчас развиваешься</p>
                            </div>
                            <button onClick={() => navigate('/about')}>Подробнее</button>
                        </div>
                        <div className={cls.imgUlars} style={{backgroundImage: `url(${imgs})`}}></div>
                    </div>

                </div>
            </div>
        </>
    )
}