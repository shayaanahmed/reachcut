"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { PublishingVideoUpload } from "../../features/publishing/video-upload";
import { useProjectWorkbench } from "../../features/projects/use-project-workbench";

export default function StudioPage() {
  const router = useRouter();
  const workbench = useProjectWorkbench();
  return (
    <main className="page">
      <header className="topbar">
        <div>
          <span className="eyebrow">VIDEO EDITOR</span>
          <h1>Studio</h1>
          <p>
            Edit your clips, preview the result, and publish from one workspace.
          </p>
        </div>
        <Link href="/publishing">Open publishing →</Link>
      </header>
      {workbench.error && (
        <p className="error" role="alert">
          {workbench.error}
        </p>
      )}
      <PublishingVideoUpload
        destination="studio"
        busy={workbench.isPending("project:publishing-upload")}
        onUpload={workbench.uploadForPublishing}
        onCreated={(project) =>
          router.push(`/projects/${project.id}/clips/${project.clips[0].id}`)
        }
      />
      <section className="section-block">
        <h2>Continue editing</h2>
        {workbench.loading ? (
          <p>Loading clips…</p>
        ) : (
          <div className="distribution-posts">
            {workbench.projects.flatMap((project) =>
              project.clips.map((clip) => (
                <article key={clip.id}>
                  <div>
                    <strong>
                      {clip.plan.suggested_title ?? project.title}
                    </strong>
                    <small>{project.title}</small>
                  </div>
                  <Link href={`/projects/${project.id}/clips/${clip.id}`}>
                    Edit in Studio →
                  </Link>
                </article>
              )),
            )}
            {!workbench.projects.some((project) => project.clips.length) && (
              <p>Upload your first clip above to start editing.</p>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
