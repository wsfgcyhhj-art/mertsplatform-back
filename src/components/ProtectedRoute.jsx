import {useFindUser} from "../store/userStore.js";
import {Navigate, Outlet, useLocation} from "react-router-dom";

export const ProtectedRoute = () => {

    const { userInfo } = useFindUser();
    const { pathname, search, hash } = useLocation();
    const returnTo = ['/lessons', '/tasks'].includes(pathname) ? { pathname, search, hash } : null;

    return !userInfo ? <Navigate to="/auth" state={{ returnTo }} replace /> : <Outlet />;
}
