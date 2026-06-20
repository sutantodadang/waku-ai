import { RouterProvider } from "@tanstack/react-router";
import { useAuth } from "./lib/auth";
import { router } from "./router";
import AuthPage from "./pages/AuthPage";

export default function App() {
  const { token } = useAuth();
  if (!token) return <AuthPage />;
  return <RouterProvider router={router} />;
}
