import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import LoginScreen from "./LoginScreen";
import { AuthProvider, useAuth } from "./auth";
import { Spinner } from "./ui";
import "./index.css";

function Root() {
  const { ready, session } = useAuth();
  if (!ready) {
    return (
      <div className="grid h-full place-items-center bg-rf-bg">
        <Spinner label="starting…" />
      </div>
    );
  }
  return session ? <App /> : <LoginScreen />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <Root />
    </AuthProvider>
  </React.StrictMode>,
);
