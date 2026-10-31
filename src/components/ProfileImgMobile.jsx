import cls from '../../src/pages/ProfilePage/styles/profile.module.scss'
import {useProfile} from "../store/useProfile.js";
export const ProfileImgMobile = () => {

    const { profileUrlImg } = useProfile()

    return (
        <div className={cls.profile_mobile}    style={{ backgroundImage: `url(${profileUrlImg})`                        }}>

        </div>
    )
}