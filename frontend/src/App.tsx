import { BrowserRouter, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { ExplorerPage } from "./pages/ExplorerPage";
import { ThemeProvider } from "./theme";

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/explore" element={<ExplorerPage />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
