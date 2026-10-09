import { Toaster } from "react-hot-toast";
import { Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import { AdminRoute, ProtectedRoute } from "./components/ProtectedRoute";
import RadarApp from "./radar/RadarApp";

import Login from "./pages/Login";
import ExecutiveDashboard from "./pages/ExecutiveDashboard";
import AnalysisWorkspace from "./pages/AnalysisWorkspace";
import Dashboard from "./pages/Dashboard";
import SignalDetail from "./pages/SignalDetail";
import DigestArchive, { DigestDetail } from "./pages/DigestArchive";
import Admin from "./pages/Admin";

// The radar shell (src/radar) is the app: "/" shows its screens (SWOT home, deep-dive book,
// follow-up, explore, radar settings). The restricted M&A desk screens render inside it.
export default function App() {
  return (
    <AuthProvider>
      <Toaster position="top-right" toastOptions={{ style: { fontSize: "13px" } }} />
      <Routes>
        <Route path="/login" element={<div className="tw"><Login /></div>} />

        <Route
          element={
            <ProtectedRoute>
              <RadarApp />
            </ProtectedRoute>
          }
        >
          <Route index element={null} />
          <Route path="dashboard" element={<ExecutiveDashboard />} />
          <Route path="analyze/:company" element={<AnalysisWorkspace />} />
          <Route path="board" element={<Dashboard />} />
          <Route path="signals/:id" element={<SignalDetail />} />
          <Route path="digests" element={<DigestArchive />} />
          <Route path="digests/:id" element={<DigestDetail />} />
          <Route
            path="admin"
            element={
              <AdminRoute>
                <Admin />
              </AdminRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
