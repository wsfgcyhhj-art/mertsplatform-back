import cls from  '../styles/about.module.scss'
import {FiUser} from "react-icons/fi";
import {FaArrowRight, FaTelegramPlane} from "react-icons/fa";
import {useHistory} from "../../../store/historyStore.js";
import imgs from '../../../images/imgss.webp'


export const AboutMeHeader = () => {

    const {  toggleHistory } = useHistory()

    const goToHistory = () => {
        document.getElementById("history").scrollIntoView({behavior: "smooth"});
        toggleHistory(true)
        setTimeout(() => {
            toggleHistory(false)
        }, 2000)
    }

    return (
        <>
            <div className={cls.header} data-aos="fade-up" data-aos-duration="1000">
                <div className={cls.header_items}>
                    <div className={cls.left_header_item} data-aos="fade-right" data-aos-duration="1200">
                        <span className={cls.s}> <FiUser /> Основатель MertsPlatform</span>
                        <div className={cls.title}>
                            <h1>Привет! Я <span>Улар</span> </h1>
                            <p>Front-end Developer & Mentor</p>
                        </div>
                        <div className={cls.left_about}>
                            <p>
                                Я создал MertsPlatform, чтобы объединить обучение, практику и развитие в одном удобном пространстве для студентов. Платформа постоянно развивается и становится лучше, чтобы помогать студентам совершенствовать свои навыки.
                            </p>
                        </div>
                        <div className={cls.buttons}>
                            <button onClick={goToHistory}>Моя история <FaArrowRight /> </button>
                            <button>Связаться Со мной <FaTelegramPlane /> </button>
                        </div>
                    </div>
                    <div data-aos="fade-left" style={{backgroundImage: `url(${imgs})`}} className={cls.right_header_item} data-aos-duration="1200">

                    </div>
                </div>
            </div>
        </>
    )
}