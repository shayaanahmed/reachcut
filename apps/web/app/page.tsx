"use client";

import { ProjectList } from "../features/projects/project-list";
import { ProjectUpload } from "../features/projects/project-upload";
import { useProjectWorkbench } from "../features/projects/use-project-workbench";

export default function Home() {
  const workbench = useProjectWorkbench();

  return (
    <main>
      <header>
        <span className="eyebrow">LOCAL VIDEO WORKBENCH</span>
        <h1>
          Find the moment.
          <br />
          Keep the meaning.
        </h1>
        <p>
          Private transcription and editorial selection, with you making the
          final call.
        </p>
      </header>
      <ProjectUpload busy={workbench.busy} onUpload={workbench.upload} />
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <ProjectList
        projects={workbench.projects}
        busy={workbench.busy}
        languages={workbench.languages}
        setLanguages={workbench.setLanguages}
        onProcess={workbench.process}
        onApprove={workbench.approve}
        onRender={workbench.render}
        onSaveStyle={workbench.saveStyle}
      />
    </main>
  );
}
