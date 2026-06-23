import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import Layout from "./components/Layout";
import Beranda from "./pages/Beranda";
import Orders from "./pages/Orders";
import Bookings from "./pages/Bookings";
import Catalog from "./pages/Catalog";
import Customers from "./pages/Customers";
import Settings from "./pages/Settings";
import Whatsapp from "./pages/Whatsapp";

const rootRoute = createRootRoute({ component: Layout });

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: Beranda });
const ordersRoute = createRoute({ getParentRoute: () => rootRoute, path: "/orders", component: Orders });
const bookingsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/bookings", component: Bookings });
const catalogRoute = createRoute({ getParentRoute: () => rootRoute, path: "/catalog", component: Catalog });
const customersRoute = createRoute({ getParentRoute: () => rootRoute, path: "/customers", component: Customers });
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/settings", component: Settings });
const whatsappRoute = createRoute({ getParentRoute: () => rootRoute, path: "/whatsapp", component: Whatsapp });

const routeTree = rootRoute.addChildren([indexRoute, ordersRoute, bookingsRoute, customersRoute, catalogRoute, settingsRoute, whatsappRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
