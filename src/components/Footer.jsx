import { useRef } from 'react';
import cls from '../components/footer.module.scss';
import { api } from '../api/client.js';
import { showAchievementToast } from './AchievementToast.jsx';

export const Footer = () => {
    const clickCountRef = useRef(0);
    const timerRef = useRef(null);
    const claimingRef = useRef(false);

    const handleSecretTrigger = async () => {
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
                        customMessage: 'Пасхалка уже открыта вами ранее — ачивка «Любопытный хакер» в вашей коллекции!',
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

    return (
        <div className={cls.footer}>
            <p style={{ userSelect: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <span
                    onClick={handleSecretTrigger}
                    title="MertsPlatform Terminal Node"
                    style={{
                        display: 'inline-block',
                        width: 7,
                        height: 7,
                        borderRadius: '50%',
                        backgroundColor: '#3f3f46',
                        cursor: 'pointer',
                        transition: 'background-color 0.2s ease',
                    }}
                />
                <span onClick={handleSecretTrigger} style={{ cursor: 'pointer' }}>
                    © 2026 MertsPlatform.
                </span>{' '}
                All rights reserved. Designed and developed by Ular.
            </p>
        </div>
    );
};
