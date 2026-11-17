import { api } from './api/client.js';
import { setAccessToken } from './api/authToken.js';
import { useFindUser } from './store/userStore.js';
import { createRoot } from 'react-dom/client'
import '../src/styles/global.scss'
import {QueryClient, QueryClientProvider} from "@tanstack/react-query";
import {RouterProvider} from "react-router-dom";
import {router} from "./components/router.jsx";
import AOS from "aos";
import "aos/dist/aos.css";


const queryClient = new QueryClient()

AOS.init({})

if ("scrollRestoration" in window.history) {
    window.history.scrollRestoration = "manual";
    window.scrollX = 'behavior';
}
async function start() {
  try {
    const response = await api.post('/auth/refresh');
    setAccessToken(response.data.accessToken);
    const profile = await api.get('/users/me');
    useFindUser.getState().addUser(profile.data.user, response.data.accessToken);
  } catch { /* No authenticated session. */ }
  createRoot(document.getElementById('root')).render(
    <QueryClientProvider client={queryClient}>
        <RouterProvider router={router}/>
    </QueryClientProvider>

)

}
start();
