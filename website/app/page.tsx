import dynamic from "next/dynamic";
const EvolutionExperience = dynamic(() => import("@/components/EvolutionExperience"), { ssr: false, loading: () => <div className="scene-loading"><div className="loading-mark">N</div><span>Preparing the evolution experience</span></div> });
export default function Home() { return <main><EvolutionExperience /></main>; }
