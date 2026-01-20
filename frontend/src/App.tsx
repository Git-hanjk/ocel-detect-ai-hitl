import React from "react";
import { Route, Routes } from "react-router-dom";
import Queue from "./pages/Queue";
import CaseDetail from "./pages/CaseDetail";
import Stats from "./pages/Stats";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Queue />} />
      <Route path="/cases/:candidateId" element={<CaseDetail />} />
      <Route path="/stats" element={<Stats />} />
    </Routes>
  );
}
