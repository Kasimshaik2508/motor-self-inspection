/*
  App.jsx - the shell: a header and three tabs.
    Inspect my car  - the CUSTOMER app (Capture.jsx): photos -> on-phone checks -> AI -> decision
    Reviewer        - the REVIEWER console (Reviewer.jsx): confirm or override, with a reason
    Evaluation      - the 420 gold cases from the challenge pack (CaseExplorer.jsx)
  The tab lives in the address (#inspect, #reviewer, #evaluation) so each one can be shared as a link.
*/
import { useEffect, useState } from "react";
import Capture from "./Capture";
import Reviewer from "./Reviewer";
import CaseExplorer from "./CaseExplorer";

const TABS = [["inspect", "Inspect my car"], ["reviewer", "Reviewer"], ["evaluation", "Evaluation (420 cases)"]];
const fromHash = () => { const h = window.location.hash.replace("#", ""); return TABS.some(([k]) => k === h) ? h : "inspect"; };

export default function App() {
  const [tab, setTab] = useState(fromHash);
  useEffect(() => {
    const on = () => setTab(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  return (
    <>
      <header>
        <h1>Motor Self-Inspection AI</h1>
        <p>PolicyNest · PS-03 MVP · photograph a car, the AI finds damage and applies the inspection rules.</p>
        <nav className="tabs">
          {TABS.map(([k, label]) => (
            <a key={k} href={"#" + k} className={tab === k ? "active" : ""}>{label}</a>
          ))}
        </nav>
      </header>
      <main>
        {tab === "inspect" && <Capture />}
        {tab === "reviewer" && <Reviewer />}
        {tab === "evaluation" && <CaseExplorer />}
      </main>
    </>
  );
}
