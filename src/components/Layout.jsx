import {Header} from "./Header.jsx";
import {Outlet} from "react-router-dom";
import {ScrollToTop} from "./ScrollToTop.jsx";
import {Footer} from "./Footer.jsx";
import {AchievementToastHost} from "./AchievementToast.jsx";

export const Layout = () => {
    return (
        <>
            <ScrollToTop/>
            <AchievementToastHost/>
            <div style={{ display: "flex", minHeight: "100vh", width: "100%" }}>
                <Header />
                <main style={{ marginLeft: "64px", flex: 1, width: "calc(100% - 64px)", minWidth: 0 }}>
                    <Outlet/>
                </main>
            </div>
            <Footer/>
        </>
    )
}
