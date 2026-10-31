import {Header} from "./Header.jsx";
import {Outlet} from "react-router-dom";
import {ScrollToTop} from "./ScrollToTop.jsx";
import {Footer} from "./Footer.jsx";

export const Layout = () => {
    return (
        <>
            <ScrollToTop/>
            <div style={{ display: "flex", minHeight: "100vh", width: "100%" }}>
                <Header />
                <div style={{ marginLeft: "61px", flex: 1, width: "calc(100% - 61px)", minWidth: 0 }}>
                    <Outlet/>
                </div>
            </div>
            <Footer/>
        </>
    )
}
