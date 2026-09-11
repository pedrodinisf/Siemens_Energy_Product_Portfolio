import { createRootRoute, HeadContent, Outlet, Scripts } from "@tanstack/react-router";
import { PreviewHostBridge } from "@/components/preview-host-bridge";
import { Shell } from "@/components/shell";
import appCss from "../styles.css?url";

const APP_NAME = "Fieldbook";
const BASE = import.meta.env.BASE_URL;

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: APP_NAME },
      {
        name: "description",
        content:
          "Searchable library of Siemens Energy products, specifications, brochures, and white papers.",
      },
      { name: "theme-color", content: "#081018" },
    ],
    links: [
      { rel: "icon", type: "image/svg+xml", href: `${BASE}favicon.svg` },
      { rel: "stylesheet", href: appCss },
      { rel: "manifest", href: `${BASE}__grok/manifest.webmanifest` },
      { rel: "apple-touch-icon", href: `${BASE}__grok/icon-180.png` },
    ],
  }),
  component: Root,
});

function Root() {
  return (
    <html lang="en" className="antialiased" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body className="bg-bg text-fg">
        <PreviewHostBridge />
        <Shell>
          <Outlet />
        </Shell>
        <Scripts />
      </body>
    </html>
  );
}
