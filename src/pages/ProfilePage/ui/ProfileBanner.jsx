import { useState, useEffect } from 'react';
import { Modal, message } from 'antd';
import cls from '../styles/profile.module.scss';
import { useProfile } from '../../../store/useProfile.js';
import { useFindUser } from '../../../store/userStore.js';
import { api, resolveMediaUrl, extractAuthToken } from '../../../api/client.js';

const DEFAULT_BANNER_PATH = '/api/v1/media/presets/banners/linear-graphite.svg';

export const ProfileBanner = () => {
    const { bannerUrlImg, addBannerUrlImg } = useProfile();
    const { userInfo, addUser } = useFindUser();
    const [presetsModalOpen, setPresetsModalOpen] = useState(false);
    const [bannerPresets, setBannerPresets] = useState([]);
    const [uploading, setUploading] = useState(false);

    useEffect(() => {
        if (userInfo?.bannerUrl && userInfo.bannerUrl !== bannerUrlImg) {
            addBannerUrlImg(userInfo.bannerUrl);
        }
    }, [userInfo?.bannerUrl, bannerUrlImg, addBannerUrlImg]);

    const loadPresets = async () => {
        try {
            const res = await api.get('/media/presets');
            if (Array.isArray(res.data?.banners)) {
                setBannerPresets(res.data.banners);
            }
        } catch (err) {
            console.error('Failed to load banner presets', err);
        }
    };

    const handleOpenPresets = () => {
        setPresetsModalOpen(true);
        if (bannerPresets.length === 0) {
            loadPresets();
        }
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            setUploading(true);
            const formData = new FormData();
            formData.append('file', file);

            const token = extractAuthToken();
            const res = await api.post('/users/me/banner', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
            });

            const nextBanner = res.data?.user?.bannerUrl ?? res.data?.bannerUrl;
            if (res.data?.user) {
                addUser(res.data.user, token);
            } else if (nextBanner && userInfo) {
                addUser({ ...userInfo, bannerUrl: nextBanner }, token);
            }
            if (nextBanner) {
                addBannerUrlImg(nextBanner);
                message.success('Обложка профиля обновлена!');
            }
        } catch (err) {
            message.error(err.response?.data?.message || 'Не удалось загрузить обложку');
        } finally {
            setUploading(false);
            e.target.value = '';
        }
    };

    const handleSelectPreset = async (presetUrl) => {
        try {
            setUploading(true);
            const token = extractAuthToken();
            const res = await api.patch('/users/me', { bannerUrl: presetUrl });
            if (res.data?.user) {
                addUser(res.data.user, token);
                addBannerUrlImg(res.data.user.bannerUrl || '');
                message.success('Фирменная обложка установлена!');
                setPresetsModalOpen(false);
            }
        } catch (err) {
            message.error(err.response?.data?.message || 'Не удалось выбрать обложку');
        } finally {
            setUploading(false);
        }
    };

    const activeBannerRaw = userInfo?.bannerUrl || bannerUrlImg || DEFAULT_BANNER_PATH;
    const resolvedBannerUrl = resolveMediaUrl(activeBannerRaw, DEFAULT_BANNER_PATH);

    return (
        <>
            <div
                className={cls.banner}
                data-aos="zoom-in"
                style={{
                    backgroundImage: resolvedBannerUrl ? `url("${resolvedBannerUrl}")` : 'none',
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                }}
            >
                <div
                    style={{
                        position: 'absolute',
                        top: 14,
                        right: 20,
                        display: 'flex',
                        gap: 10,
                        flexWrap: 'wrap',
                        zIndex: 3,
                    }}
                >
                    <button
                        type="button"
                        onClick={handleOpenPresets}
                        disabled={uploading}
                        style={{
                            padding: '8px 14px',
                            border: '1px solid rgba(245, 158, 11, 0.4)',
                            background: 'rgba(9, 9, 11, 0.85)',
                            borderRadius: 10,
                            color: '#fbbf24',
                            fontSize: 13,
                            fontWeight: 600,
                            cursor: 'pointer',
                        }}
                    >
                        Галерея обложек
                    </button>

                    <label
                        className={cls.banner_btn}
                        style={{
                            position: 'static',
                            opacity: uploading ? 0.7 : 1,
                        }}
                    >
                        {uploading ? 'Загрузка...' : 'Загрузить обложку'}
                        <input
                            type="file"
                            accept="image/jpeg,image/png,image/webp,image/gif,image/svg+xml"
                            onChange={handleFileUpload}
                            disabled={uploading}
                        />
                    </label>
                </div>
            </div>

            <Modal
                title="Фирменные обложки MertsPlatform"
                open={presetsModalOpen}
                onCancel={() => setPresetsModalOpen(false)}
                footer={null}
                width={680}
                centered
            >
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                        gap: 14,
                        marginTop: 14,
                    }}
                >
                    {bannerPresets.map((preset) => {
                        const isSelected = activeBannerRaw === preset.url;
                        const previewSrc = resolveMediaUrl(preset.url);
                        return (
                            <button
                                key={preset.slug}
                                type="button"
                                onClick={() => handleSelectPreset(preset.url)}
                                disabled={uploading}
                                style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: 8,
                                    padding: 10,
                                    borderRadius: 12,
                                    background: '#18181b',
                                    border: isSelected ? '2px solid #f59e0b' : '1px solid #27272a',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                    color: '#f4f4f5',
                                }}
                            >
                                <div
                                    style={{
                                        width: '100%',
                                        height: 76,
                                        borderRadius: 8,
                                        backgroundImage: `url("${previewSrc}")`,
                                        backgroundSize: 'cover',
                                        backgroundPosition: 'center',
                                        border: '1px solid #27272a',
                                    }}
                                />
                                <div style={{ fontSize: 13, fontWeight: 600, color: isSelected ? '#fbbf24' : '#f4f4f5' }}>
                                    {preset.title}
                                </div>
                            </button>
                        );
                    })}
                </div>
            </Modal>
        </>
    );
};
