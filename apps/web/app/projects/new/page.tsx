"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ProjectUpload } from "../../../features/projects/project-upload";
import { useProjectWorkbench } from "../../../features/projects/use-project-workbench";

export default function NewProjectPage() {
  const workbench = useProjectWorkbench();
  const router = useRouter();
  return (
    <main className="page narrow-page">
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <span>/</span>
        <span>New project</span>
      </div>
      <div className="topbar compact">
        <div>
          <span className="eyebrow">CREATE</span>
          <h1>New project</h1>
          <p>
            Bring in a local file or a public video URL you are authorized to
            use.
          </p>
        </div>
      </div>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <ProjectUpload
        busy={workbench.busy}
        onUpload={workbench.upload}
        onImportUrl={workbench.importUrl}
        onCreated={(project) => router.push(`/projects/${project.id}`)}
        error={workbench.error}
      />
    </main>
  );
}
