import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ReachCut Local Studio",
    short_name: "ReachCut",
    description: "A private, local-first workspace for creating vertical clips",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#10130f",
    theme_color: "#d8ff42",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
