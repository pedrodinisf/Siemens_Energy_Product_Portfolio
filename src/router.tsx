import { createRouter } from "@tanstack/react-router";
import { AppErrorComponent } from "@/lib/error-component";
import { routeTree } from "./routeTree.gen";

export function getRouter() {
  return createRouter({
    routeTree,
    defaultErrorComponent: AppErrorComponent,
    // "/" on dev/Vercel; "/Siemens_Energy_Product_Portfolio/" on the GitHub
    // Pages build. Vite injects the matching base already.
    basepath: import.meta.env.BASE_URL,
  });
}
