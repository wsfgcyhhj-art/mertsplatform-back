import { useFindUser } from "../store/userStore.js";
import { Navigate, Outlet } from "react-router-dom";

export const AdminRoute = () => {
  const { userInfo } = useFindUser();

  if (!userInfo) {
    return <Navigate to="/auth" replace />;
  }

  if (userInfo.role !== 'ADMIN') {
    return <Navigate to="/lessons" replace />;
  }

  return <Outlet />;
};
