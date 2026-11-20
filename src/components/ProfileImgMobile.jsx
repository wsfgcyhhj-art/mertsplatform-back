import { FaUser } from "react-icons/fa";
import cls from "../pages/ProfilePage/styles/profile.module.scss";
import { useProfile } from "../store/useProfile.js";
import { useFindUser } from "../store/userStore.js";
import { resolveMediaUrl } from "../api/client.js";

export const ProfileImgMobile = () => {
    const { profileUrlImg } = useProfile();
    const { userInfo } = useFindUser();
    const avatarSrc = resolveMediaUrl(userInfo?.avatarUrl || profileUrlImg);

    if (!avatarSrc) {
        return <FaUser size={18} aria-hidden="true" />;
    }

    return (
        <span
            className={cls.profile_mobile}
            style={{ width: '24px', height: '24px', display: 'inline-block', backgroundImage: `url("${avatarSrc}")` }}
            aria-hidden="true"
        />
    );
};