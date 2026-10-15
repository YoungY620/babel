import "@fontsource/onest/latin-400.css";
import "@fontsource/onest/latin-500.css";
import "@fontsource/onest/latin-600.css";
import { createRoot } from "react-dom/client";
import "./i18n";
import App from "./App";
import "./styles.css";
createRoot(document.getElementById("root")!).render(<App />);
