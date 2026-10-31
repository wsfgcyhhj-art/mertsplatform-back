import { useRef } from 'react';
import cls from '../../src/components/header.module.scss';
import { FaHome, FaNewspaper, FaTasks, FaTrophy, FaAward, FaTerminal } from "react-icons/fa";
import { FaBookOpenReader, FaRegMessage } from "react-icons/fa6";
import { MdAdminPanelSettings } from "react-icons/md";
import { useNavigate } from "react-router-dom";
import { IoMdExit } from "react-icons/io";
import { ProfileImgMobile } from "./ProfileImgMobile.jsx";
import { HiMiniQuestionMarkCircle } from "react-icons/hi2";
import { useFindUser } from "../store/userStore.js";
import { api } from "../api/client.js";
import { showAchievementToast } from "./AchievementToast.jsx";

export const Header = () => {
    const { userInfo, removeUser } = useFindUser();
    const navigate = useNavigate();

    const clickCountRef = useRef(0);
    const timerRef = useRef(null);
    const claimingRef = useRef(false);

    const handleLogoEasterEgg = async () => {
        if (claimingRef.current) return;
        clickCountRef.current += 1;
        if (timerRef.current) clearTimeout(timerRef.current);

        timerRef.current = setTimeout(() => {
            clickCountRef.current = 0;
        }, 2500);

        if (clickCountRef.current >= 5) {
            clickCountRef.current = 0;
            claimingRef.current = true;
            try {
                const res = await api.post('/me/claim-easter-egg');
                if (res.data?.achievement) {
                    showAchievementToast({
                        title: 'Любопытный хакер',
                        customMessage: '🎉 Вы нашли секретную пасхалку! Получена ачивка "Любопытный хакер" (+20 очков)',
                        description: res.data.achievement.description,
                        points: 20,
                        iconUrl: 'Terminal',
                    });
                    window.dispatchEvent(new CustomEvent('merts:refresh-achievements'));
                } else if (res.data?.alreadyUnlocked) {
                    showAchievementToast({
                        title: 'Любопытный хакер',
                        customMessage: 'Пасхалка уже активирована — ачивка «Любопытный хакер» получена!',
                        iconUrl: 'Terminal',
                    });
                }
            } catch (err) {
                console.error('Easter egg claim error', err);
            } finally {
                claimingRef.current = false;
            }
        }
    };

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
            id: 9,
            name: 'Ачивки',
            img: FaAward,
            path: 'achievements'
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
        <div className={cls.header}>
            <div className={cls.header_items}>
                <div className={cls.feuters}>
                    <div
                        onClick={handleLogoEasterEgg}
                        title="MertsPlatform"
                        style={{
                            width: 40,
                            height: 40,
                            margin: '16px auto -36px auto',
                            borderRadius: 10,
                            background: '#18181b',
                            border: '1px solid rgba(245, 158, 11, 0.3)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#fbbf24',
                            cursor: 'pointer',
                            userSelect: 'none',
                            fontWeight: 800,
                            fontSize: 16,
                        }}
                    >
                        <FaTerminal size={16} />
                    </div>

                    <div className={cls.feut_items}>
                        {feutersItems?.map((i) => (
                            <div key={i?.id} className={cls.feut_item} onClick={() => navigate(`/${i.path}`)}>
                                <div className={cls.imgs}>
                                    <i.img />
                                </div>
                                <h4>{i?.name}</h4>
                            </div>
                        ))}
                        <div className={cls.feut_item}>
                            <div className={cls.imgs}>
                                <HiMiniQuestionMarkCircle className={cls.l} />
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
    );
};
