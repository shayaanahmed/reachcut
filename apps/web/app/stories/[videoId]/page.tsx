import { StoryWorkspace } from "../../../features/generation/story-workspace";

export default async function StoryPage({
  params,
}: {
  params: Promise<{ videoId: string }>;
}) {
  const { videoId } = await params;
  return <StoryWorkspace videoId={videoId} />;
}
