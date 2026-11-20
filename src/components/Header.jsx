import { useRef, useEffect, useState } from 'react';
import cls from './header.module.scss';
import { FaHome, FaNewspaper, FaTasks, FaTrophy, FaAward, FaShoppingBag } from "react-icons/fa";
import { FaBookOpenReader, FaRegMessage } from "react-icons/fa6";
import { MdAdminPanelSettings } from "react-icons/md";
import { useNavigate } from "react-router-dom";
import { IoMdExit } from "react-icons/io";
import { ProfileImgMobile } from "./ProfileImgMobile.jsx";
import { HiMiniQuestionMarkCircle } from "react-icons/hi2";
import { useFindUser } from "../store/userStore.js";
import { useProfile } from "../store/useProfile.js";
import { api, extractAuthToken, resetCsrfToken } from "../api/client.js";
import { claimEasterEgg } from "../utils/achievements.js";

function getStreakWord(count) {
    const abs = Math.abs(count) % 100;
    const num = abs % 10;
    if (abs > 10 && abs < 20) return 'дней';
    if (num > 1 && num < 5) return 'дня';
    if (num === 1) return 'день';
    return 'дней';
}

export const Header = () => {
    const { userInfo, removeUser } = useFindUser();
    const navigate = useNavigate();
    const [expanded, setExpanded] = useState(false);

    const clickCountRef = useRef(0);
    const timerRef = useRef(null);
    const claimingRef = useRef(false);

    useEffect(() => {
        let isMounted = true;
        const fetchMe = async () => {
            try {
                const res = await api.get('/users/me');
                if (isMounted && res.data?.user) {
                    const resolvedStreak = res.data?.stats?.streakCount ?? res.data?.user?.streakCount ?? 0;
                    const { userInfo: currentUser, addUser } = useFindUser.getState();
                    addUser({
                        ...(currentUser || {}),
                        ...res.data.user,
                        streakCount: resolvedStreak,
                    });
                }
            } catch {
                // Игнорируем сетевые ошибки фоновой синхронизации
            }
        };

        if (extractAuthToken()) {
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
                await claimEasterEgg();
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
        { id: 10, name: 'Магазин', img: FaShoppingBag, path: 'shop' },
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

    const handleNavigate = (path) => {
        setExpanded(false);
        navigate(path);
    };

    const exit = async () => {
        setExpanded(false);
        try {
            await api.post('/auth/logout');
        } catch {
            // Завершаем локальную сессию даже если сервер недоступен или сессия уже истекла
        } finally {
            resetCsrfToken();
            removeUser();
            useProfile.getState().resetProfile();
            localStorage.removeItem('user-merts-chat');
            localStorage.removeItem('profile-user-merts-chat');
            navigate('/auth', { replace: true });
        }
    };

    const streakCount = userInfo?.streakCount || 0;

    return (
        <nav
            aria-label="Навигация"
            className={`${cls.header} ${expanded ? cls.expanded : ''}`}
            onMouseEnter={() => setExpanded(true)}
            onMouseLeave={() => setExpanded(false)}
        >
            <div className={cls.header_items}>
                <div className={cls.feuters}>
                    <div
                        onClick={handleLogoEasterEgg}
                        title="MertsPlatform"
                        className={cls.brand_logo}
                    >
                        <img
                            src="/logo.png"
                            alt="MertsPlatform"
                            className={cls.brand_logo_img}
                        />
                    </div>

                    {userInfo && (
                        <button
                            type="button"
                            title="Дней подряд в платформе"
                            onClick={() => handleNavigate('/profile')}
                            className={cls.streak_badge}
                        >
                            <span style={{ fontSize: '14px', lineHeight: 1 }}>🔥</span>
                            <span>{streakCount}</span>
                            {expanded && (
                                <span style={{ fontSize: '11px', color: '#fed7aa', fontWeight: 600 }}>
                                    {getStreakWord(streakCount)}
                                </span>
                            )}
                        </button>
                    )}

                    <div className={cls.feut_items}>
                        {feutersItems?.map((i) => (
                            <button
                                key={i?.id}
                                type="button"
                                className={cls.feut_item}
                                onClick={() => handleNavigate(`/${i.path}`)}
                                title={i?.name}
                            >
                                <span className={cls.imgs}>
                                    <i.img />
                                </span>
                                <span className={cls.nav_label}>{i?.name}</span>
                            </button>
                        ))}
                        <a
                            href="/MertsPlatform_Instruction.pdf"
                            download
                            className={cls.feut_item}
                            onClick={() => setExpanded(false)}
                            title="Инструкция"
                        >
                            <span className={cls.imgs}>
                                <HiMiniQuestionMarkCircle />
                            </span>
                            <span className={cls.nav_label}>Инструкция</span>
                        </a>
                    </div>
                </div>

                <div className={cls.header_footer}>
                    <a
                        href="https://t.me/Merts228"
                        target="_blank"
                        rel="noopener noreferrer"
                        className={cls.feut_item}
                        onClick={() => setExpanded(false)}
                        title="Нужна помощь?"
                    >
                        <span className={cls.imgs}>
                            <FaRegMessage />
                        </span>
                        <span className={cls.nav_label}>Нужна помощь?</span>
                    </a>
                    <button
                        type="button"
                        className={`${cls.feut_item} ${cls.exit_item}`}
                        onClick={exit}
                        title="Выйти"
                    >
                        <span className={cls.imgs}>
                            <IoMdExit />
                        </span>
                        <span className={cls.nav_label}>Выйти</span>
                    </button>
                </div>
            </div>
        </nav>
    );
};
