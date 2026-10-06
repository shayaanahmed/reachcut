import { ClipStudio } from "../../../../../features/clips/clip-studio";

export default async function ClipStudioPage({
  params,
}: {
  params: Promise<{ projectId: string; clipId: string }>;
}) {
  const { projectId, clipId } = await params;
  return <ClipStudio projectId={projectId} clipId={clipId} />;
}
