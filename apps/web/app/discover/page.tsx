"use client";

import { useRouter } from "next/navigation";

import { TrendDiscovery } from "../../features/discovery/trend-discovery";

export default function DiscoverPage() {
  const router = useRouter();
  return (
    <main className="page">
      <div className="topbar">
        <div>
          <span className="eyebrow">OPPORTUNITY DISCOVERY</span>
          <h1>Find your next clip</h1>
          <p>
            Search any topic or browse fresh ideas across news, entertainment,
            sports, technology, podcasts, and gaming.
          </p>
        </div>
      </div>
      <TrendDiscovery
        onCreated={(project) => router.push(`/projects/${project.id}`)}
      />
    </main>
  );
}
