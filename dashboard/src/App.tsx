import { RouterProvider } from "@tanstack/react-router";
import { useAuth } from "./lib/auth";
import { router } from "./router";
import AuthPage from "./pages/AuthPage";
import Toaster from "./components/Toaster";

export default function App() {
  const { token } = useAuth();
  return (
    <>
      {token ? <RouterProvider router={router} /> : <AuthPage />}
      <Toaster />
    </>
  );
}
