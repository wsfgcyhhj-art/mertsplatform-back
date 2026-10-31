import cls from '../styles/aboutHistory.module.scss'
import { FaCalendarAlt, FaRegUser, FaTelegramPlane, FaUserAlt} from "react-icons/fa";
import {useHistory} from "../../../store/historyStore.js";
import {useState} from "react";

export const AboutMertsHistory =  ({ history, approach }) => {

    const { historys } = useHistory();

    const [hover , setHover] = useState(false)


    return (
        <>
            <div className={cls.about_history}>
               <div className={cls.about_history_items}>
                   {
                       history.map((h) => (
                           <section key={h?.id} id="history" className={`${cls.about_history_left} ${historys ? cls.active : ''}`}>
                                <div className={cls.title}>
                                    <h1><span><FaRegUser /></span>{h?.title} </h1>
                                </div>
                               <div className={cls.hr}>
                                   <hr />
                               </div>
                               <div className={cls.info}>
                                    <p>
                                        {h?.description}
                                    </p>
                                    <p className={cls.footer_desc}>
                                        {h?.footerDescription}
                                    </p>
                               </div>
                                   <div className={cls.buttons}>
                                       <div> <FaCalendarAlt /> 2026 Год основания </div>
                                       <div>Связаться Со мной <FaTelegramPlane /> </div>
                                   </div>
                           </section>
                       ))
                   }
                <div className={cls.about_history_right} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} >
                    <h1><span></span>Мой подход</h1>
                    <hr/>
                   {
                       approach.map((h,index) => (
                                <div key={h?.id} className={cls.items}>
                                    <div className={cls.item}>
                                        <div className={`${cls.imgs} ${ hover  ? cls.active : ''}`}
                                             style={{
                                            animationDelay: `${index * 1}s`,
                                        }}>
                                        <h.imgs/>
                                        </div>
                                        <p className={hover ? cls.actives : ''} style={{
                                            animationDelay: `${index * 1}s`,
                                        }}>{h?.text}</p>
                                        </div>
                                        <hr/>
                                </div>
                           ))
                   }
                </div>
               </div>
            </div>
        </>
    )
}