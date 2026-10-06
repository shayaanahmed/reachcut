"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ProjectUpload } from "../../../features/projects/project-upload";
import { useProjectWorkbench } from "../../../features/projects/use-project-workbench";

export default function NewProjectPage() {
  const workbench = useProjectWorkbench(undefined, { loadProjects: false });
  const router = useRouter();
  return (
    <main className="page create-project-page">
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <span>/</span>
        <span>New project</span>
      </div>
      <div className="topbar compact">
        <div>
          <span className="eyebrow">NEW PRODUCTION</span>
          <h1>Turn one video into a clip campaign</h1>
          <p>
            Add a source you can repurpose. Clipper will analyze it locally and
            prepare reviewable views and revenue cuts.
          </p>
        </div>
      </div>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <ProjectUpload
        busy={workbench.isPending("project:create")}
        onUpload={workbench.upload}
        onImportUrl={workbench.importUrl}
        onCreated={(project) => router.push(`/projects/${project.id}`)}
        error={workbench.error}
      />
    </main>
  );
}
