import { Route, Routes } from "react-router-dom";
import ProjectListPage from "./pages/ProjectListPage";
import ProjectEditorPage from "./pages/ProjectEditorPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectListPage />} />
      <Route path="/projects/:projectId" element={<ProjectEditorPage />} />
    </Routes>
  );
}
