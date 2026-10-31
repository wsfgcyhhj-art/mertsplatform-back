import {useFindUser} from "../store/userStore.js";
import {Navigate, Outlet} from "react-router-dom";

export const ProtectedRoute = () => {

    const {  userInfo } = useFindUser();

    return  !userInfo ?  <Navigate to="/auth"/> : <Outlet />
}