import cls from '../../src/components/header.module.scss'
import {FaHome, FaNewspaper, FaTasks, FaTrophy} from "react-icons/fa";
import {FaBookOpenReader} from "react-icons/fa6";
import { FaRegMessage } from "react-icons/fa6";
import { MdAdminPanelSettings } from "react-icons/md";
import {useNavigate} from "react-router-dom";
import {IoMdExit} from "react-icons/io";
import {ProfileImgMobile} from "./ProfileImgMobile.jsx";
import {HiMiniQuestionMarkCircle} from "react-icons/hi2";
import { useFindUser } from "../store/userStore.js";


export const Header = () => {
    const { userInfo, removeUser } = useFindUser();
    const navigate = useNavigate();

    const feutersItems = [
        {
            id: 2,
            name: 'Главная',
            img: FaHome,
            path: 'main'
        },
        {
            id: 3,
            name: 'Мои уроки',
            img: FaBookOpenReader,
            path: 'lessons'
        },
        {
            id: 4,
            name: 'Задания',
            img: FaTasks,
            path: 'tasks'
        },
        {
            id: 8,
            name: 'Рейтинг',
            img: FaTrophy,
            path: 'leaderboard'
        },
        {
            id: 5,
            name: 'События',
            img: FaNewspaper,
            path: 'events'
        },
        {
            id: 6,
            name: 'Профиль',
            img: ProfileImgMobile,
            path: 'profile'
        },
    ];

    if (userInfo?.role === 'ADMIN') {
        feutersItems.push({
            id: 7,
            name: 'Админка',
            img: MdAdminPanelSettings,
            path: 'admin'
        });
    }

    const exit = () => {
        removeUser();
        localStorage.removeItem('user-merts-chat');
        navigate('/auth');
    };

    return (
        <>
            <div className={cls.header}>
                <div className={cls.header_items}>
                    <div className={cls.feuters}>
                       <div className={cls.feut_items}>
                           {
                               feutersItems?.map((i) => (
                                   <div key={i?.id} className={cls.feut_item} onClick={() => navigate(`/${i.path}`)}>
                                       <div className={cls.imgs}>
                                           <i.img/>
                                       </div>
                                       <h4>{i?.name}</h4>
                                   </div>
                               ))
                           }
                           <div className={cls.feut_item}>
                               <div className={cls.imgs}>
                                   <HiMiniQuestionMarkCircle className={cls.l}/>
                               </div>
                               <h4><a href="/MertsPlatform_Instruction.pdf" download>Инструкция</a></h4>
                           </div>
                       </div>
                        <div className={cls.header_footer}>
                           <div className={cls.support}>
                               <FaRegMessage className={cls.supp_img} />
                               <h4 onClick={() => window.location.href = 'https://t.me/Merts228'}>Нужна помощь?</h4>
                           </div>
                           <div className={cls.exit}>
                               <div className={cls.exit_item} onClick={exit}>
                                   <IoMdExit className={cls.supp_img} />
                                   Выйти
                               </div>
                           </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    )
}
