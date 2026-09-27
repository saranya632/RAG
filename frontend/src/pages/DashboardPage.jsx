import Chat from "../components/Chat";
import FileUpload from "../components/FileUpload";
import Navbar from "../components/Navbar";

export default function DashboardPage() {
  return (
    <div className="dashboard">
      <Navbar />
      <main className="dashboard-main">
        <FileUpload />
        <Chat />
      </main>
    </div>
  );
}
