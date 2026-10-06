import { ClipPublishingWorkspace } from "../../../../../../features/publishing/clip-publishing-workspace";

export default async function ClipPublishingPage({
  params,
}: {
  params: Promise<{ projectId: string; clipId: string }>;
}) {
  const { projectId, clipId } = await params;
  return <ClipPublishingWorkspace projectId={projectId} clipId={clipId} />;
}
