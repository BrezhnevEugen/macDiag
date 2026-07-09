import { createRoot } from "react-dom/client";
import "./app/styles.css";
import "./app/theme.css";
import ModernApp from "./app/app.jsx";

createRoot(document.getElementById("root")).render(<ModernApp />);
