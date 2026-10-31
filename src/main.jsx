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
createRoot(document.getElementById('root')).render(
    <QueryClientProvider client={queryClient}>
        <RouterProvider router={router}/>
    </QueryClientProvider>

)
