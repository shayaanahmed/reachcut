import { SocialPostBoard } from "../../../features/publishing/social-post-board";
export default async function SocialPostsPage({
  searchParams,
}: {
  searchParams: Promise<{ clip?: string }>;
}) {
  const params = await searchParams;
  return <SocialPostBoard initialClipId={params.clip ?? ""} />;
}
