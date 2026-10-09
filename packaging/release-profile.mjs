const profiles = {
  stable: {
    channel: "stable",
    displayName: "ReachCut",
    artifactName: "ReachCut",
    slug: "reachcut",
    bundleId: "com.reachcut.desktop",
    agentId: "com.reachcut.agent",
    windowsAppId: "{{E60CCBB7-0773-4A8F-86C1-B4BEC4446E61}",
    localHostname: "studio.reachcut.localhost",
    localPort: 47_321,
    internalApiPort: 48_100,
    internalWebPort: 48_101,
    desktopDataDirectory: "ReachCut",
    linuxDataDirectory: "reachcut",
  },
  personal: {
    channel: "personal",
    displayName: "ReachCut Personal",
    artifactName: "ReachCut-Personal",
    slug: "reachcut-personal",
    bundleId: "com.reachcut.personal",
    agentId: "com.reachcut.personal.agent",
    windowsAppId: "{{4917C713-E5A0-4647-A594-4F97A562FBFF}",
    localHostname: "studio.personal.reachcut.localhost",
    localPort: 47_331,
    internalApiPort: 48_110,
    internalWebPort: 48_111,
    desktopDataDirectory: "ReachCut Personal",
    linuxDataDirectory: "reachcut-personal",
  },
};

export function releaseProfile(channel = "stable") {
  const profile = profiles[channel];
  if (!profile) {
    throw new Error("--channel must be either personal or stable");
  }
  return Object.freeze({ ...profile });
}

export function profileDataDirectory(profile, platform) {
  return platform === "linux"
    ? profile.linuxDataDirectory
    : profile.desktopDataDirectory;
}
