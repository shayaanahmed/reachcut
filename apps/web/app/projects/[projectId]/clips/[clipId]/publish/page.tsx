import { ClipPublishingWorkspace } from "../../../../../../features/publishing/clip-publishing-workspace";

export default async function ClipPublishingPage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string; clipId: string }>;
  searchParams: Promise<{ destinations?: string | string[] }>;
}) {
  const { projectId, clipId } = await params;
  const preferred = (await searchParams).destinations;
  const destinations =
    typeof preferred === "string" ? preferred.split(",").filter(Boolean) : [];
  return (
    <ClipPublishingWorkspace
      projectId={projectId}
      clipId={clipId}
      preferredAccountIds={destinations}
    />
  );
}
