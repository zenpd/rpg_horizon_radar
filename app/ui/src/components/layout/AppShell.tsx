import { Outlet } from "react-router-dom";

import { PageMetaProvider } from "../../context/PageMetaContext";
import Sidebar from "./Sidebar";
import Header from "./Header";
import Footer from "./Footer";
import RestrictedBanner from "../RestrictedBanner";

export default function AppShell() {
  return (
    <PageMetaProvider>
      <div className="min-h-screen bg-gray-50">
        <Sidebar />
        <Header />
        <RestrictedBanner />
        <main className="ml-[240px] mt-[100px] mb-[44px] min-h-[calc(100vh-144px)] overflow-y-auto">
          <div className="p-6 animate-fade-in">
            <Outlet />
          </div>
        </main>
        <Footer />
      </div>
    </PageMetaProvider>
  );
}
