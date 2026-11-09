import { useRef, useEffect } from 'react';
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

function getStreakWord(count) {
    const abs = Math.abs(count) % 100;
    const num = abs % 10;
    if (abs > 10 && abs < 20) return 'дней';
    if (num > 1 && num < 5) return 'дня';
    if (num === 1) return 'день';
    return 'дней';
}

export const Header = () => {
    const { userInfo, addUser, removeUser } = useFindUser();
    const navigate = useNavigate();

    const clickCountRef = useRef(0);
    const timerRef = useRef(null);
    const claimingRef = useRef(false);

    useEffect(() => {
        let isMounted = true;
        const fetchMe = async () => {
            try {
                const res = await api.get('/me');
                if (isMounted && res.data?.user) {
                    const resolvedStreak = res.data?.stats?.streakCount ?? res.data?.user?.streakCount ?? 0;
                    addUser({
                        ...(userInfo || {}),
                        ...res.data.user,
                        streakCount: resolvedStreak,
                    });
                }
            } catch {
                // Игнорируем сетевые ошибки фоновой синхронизации
            }
        };

        const token = localStorage.getItem('accessToken');
        if (token) {
            fetchMe();
        }

        return () => {
            isMounted = false;
        };
    }, []);

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
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            margin: '14px auto -36px auto',
                            padding: '4px',
                            cursor: 'pointer',
                            userSelect: 'none',
                            width: '100%',
                            maxHeight: '44px',
                            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                        }}
                    >
                        <img
                            src="/logo.png"
                            alt="MertsPlatform"
                            style={{
                                height: '36px',
                                maxWidth: '90%',
                                objectFit: 'contain',
                                filter: 'drop-shadow(0 2px 6px rgba(0, 0, 0, 0.3))',
                                transition: 'transform 0.25s ease, filter 0.25s ease',
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.transform = 'scale(1.06)';
                                e.currentTarget.style.filter = 'drop-shadow(0 4px 12px rgba(245, 158, 11, 0.4))';
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.transform = 'scale(1)';
                                e.currentTarget.style.filter = 'drop-shadow(0 2px 6px rgba(0, 0, 0, 0.3))';
                            }}
                        />
                    </div>

                    {userInfo && (
                        <div
                            title="Дней подряд в платформе"
                            onClick={() => navigate('/profile')}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                margin: '46px auto -52px auto',
                                padding: '5px 10px',
                                borderRadius: '20px',
                                background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(245, 158, 11, 0.15))',
                                border: '1px solid rgba(245, 158, 11, 0.35)',
                                color: '#fbbf24',
                                cursor: 'pointer',
                                userSelect: 'none',
                                fontSize: '13px',
                                fontWeight: 700,
                                transition: 'all 0.3s ease',
                                width: 'fit-content',
                                maxWidth: '220px',
                                whiteSpace: 'nowrap',
                                boxShadow: '0 2px 8px rgba(245, 158, 11, 0.15)',
                            }}
                        >
                            <span style={{ fontSize: '15px', lineHeight: 1 }}>🔥</span>
                            <span>{userInfo?.streakCount || 0}</span>
                            <span style={{ fontSize: '11px', color: '#fed7aa', fontWeight: 600 }}>
                                {getStreakWord(userInfo?.streakCount || 0)}
                            </span>
                        </div>
                    )}

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
