import cls from '../styles/profile.module.scss'
import {useProfile} from "../../../store/useProfile.js";


export const ProfileBanner = () => {

    const  { bannerUrlImg, addBannerUrlImg } = useProfile();

    return (
        <>

            <div className={cls.banner} data-aos="zoom-in" style={{ backgroundImage: `url(${bannerUrlImg})` }}>
                <label className={cls.banner_btn}>
                    Изменить обложку
                    <input type="file" accept="image/*" onChange={ (e) => {
                        const file = e.target.files[0];
                        const reader = new FileReader()

                        reader.onload = () => {
                            const base64 = reader.result;

                            addBannerUrlImg(base64);
                        };

                        reader.readAsDataURL(file);

                    }}/>
                </label>
            </div>


        </>
    )
}