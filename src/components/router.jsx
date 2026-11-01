import {createBrowserRouter, Navigate} from "react-router-dom";
import {Layout} from "./Layout.jsx";
import {NotFound} from "./NotFound.jsx";
import {Login} from "../pages/LoginPage/ ui/Login.jsx";
import {Register} from "../pages/LoginPage/ui/Register.jsx";
import {ProtectedRoute} from "./ProtectedRoute.jsx";
import {AdminRoute} from "./AdminRoute.jsx";
import {AdminDashboard} from "../pages/AdminPage/ui/AdminDashboard.jsx";
import {MainList} from "../pages/MainPage/ui/MainList.jsx";
import {ProfilePage} from "../pages/ProfilePage/ui/ProfilePage.jsx";
import {AchievementsPage} from "../pages/AchievementsPage/ui/AchievementsPage.jsx";
import {LessonsPage} from "../pages/LessonsPage/ui/LessonsPage.jsx";
import {TasksList} from "../pages/TasksPge/ui/TasksList.jsx";
import {LeaderboardPage} from "../pages/LeaderboardPage/ui/LeaderboardPage.jsx";
import {AboutMeList} from "../pages/AboutMePage/ui/AboutMeList.jsx";
import {Nothing} from "./Nothing.jsx";

export const router = createBrowserRouter([
    {
        path: "/",
        element: <Navigate to="/auth" replace />
    },
    {
        path: "/auth",
        element: <Login />
    },
    {
        path: "/login",
        element: <Login />
    },
    {
        path: "/register",
        element: <Register />
    },
    {
        path: "/",
        element: <Layout />,
        children: [
            {
                element: <ProtectedRoute />,
                children: [
                    {
                        path: "events",
                        element: <h1>Events</h1>
                    },
                    {
                        path: 'main',
                        element: <MainList />
                    },
                    {
                        path: 'lessons',
                        element: <LessonsPage />
                    },
                    {
                        path: 'results',
                        element: <LeaderboardPage />
                    },
                    {
                        path: 'leaderboard',
                        element: <LeaderboardPage />
                    },
                    {
                        path: 'tasks',
                        element: <TasksList />
                    },
                    {
                        path: 'profile',
                        element: <ProfilePage />
                    },
                    {
                        path: 'achievements',
                        element: <AchievementsPage />
                    },
                    {
                        path: 'about',
                        element: <AboutMeList />
                    }
                ]
            },
            {
                element: <AdminRoute />,
                children: [
                    {
                        path: "admin",
                        element: <AdminDashboard />
                    },
                    {
                        path: "admin/:tab",
                        element: <AdminDashboard />
                    }
                ]
            }
        ]
    },
    {
        path: "*",
        element: <NotFound />
    }
]);
