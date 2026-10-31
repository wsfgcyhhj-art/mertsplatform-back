import cls from '../styles/about.module.scss'
import {AboutMeHeader} from "./AboutMeHeader.jsx";
import {AboutMertsPlatform} from "./AboutMertsPlatform.jsx";
import {AboutMertsHistory} from "./AboutMertsHistory.jsx";
import {FaChalkboardTeacher} from "react-icons/fa";
import {MdSchool} from "react-icons/md";
import {GiLifeSupport} from "react-icons/gi";
import {RiCodeView} from "react-icons/ri";

export const AboutMeList = () => {
     const MyApproach = [
        {
            id: 1,
            text: "Объясняю сложные темы простым и понятным языком.",
            imgs: FaChalkboardTeacher

        },
        {
            id: 2,
            text: "Делаю упор на практику, чтобы знания закреплялись на реальных заданиях.",
            imgs: MdSchool

        },
        {
            id: 3,
            text: "Поддерживаю студентов и помогаю разобраться в сложных моментах.",
            imgs: GiLifeSupport

        },
        {
            id: 4,
            text: "Постоянно развиваю MertsChat, добавляя новые возможности для обучения.",
            imgs: RiCodeView
        }
    ];

    const AboutInfo = [
        {
            id: 1,
            title: "Моя история",
            description: [
                "Я увлёкся программированием, когда понял, что хочу создавать что-то полезное и красивое одновременно.\n\nВо время обучения я заметил, что одной теории недостаточно. Когда я сам был студентом и занимался с ментором, мне не хватало больше практики, реальных задач и возможности применять знания в проектах.\n\nТак появилась идея создать единую платформу — MertsPlatform.\n\nСейчас я продолжаю развивать этот проект, добавляя новые возможности и улучшая его каждый день."
            ],
            footerDescription: "Моя цель — сделать обучение удобнее и помочь студентам постоянно развиваться."
        }
    ];

    return (
        <>

            <div className={cls.about}>
                <div className={cls.about_container}>
                    <AboutMeHeader/>
                    <AboutMertsPlatform/>
                    <AboutMertsHistory history={AboutInfo} approach={MyApproach}/>
                </div>
            </div>

        </>
    )
}