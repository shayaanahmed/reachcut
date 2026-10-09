import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  const personalBuild = process.env.NEXT_PUBLIC_REACHCUT_CHANNEL === "personal";
  const applicationName = personalBuild ? "ReachCut Personal" : "ReachCut";
  return {
    name: `${applicationName} Local Studio`,
    short_name: applicationName,
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
