export function ProjectUpload({
  busy,
  onUpload,
}: {
  busy: boolean;
  onUpload: (data: FormData) => Promise<void>;
}) {
  return (
    <section className="panel" aria-labelledby="new-project">
      <h2 id="new-project">New project</h2>
      <form action={onUpload}>
        <label>
          Project name
          <input
            name="title"
            required
            maxLength={200}
            placeholder="Founder interview — August"
          />
        </label>
        <label>
          Source video
          <input name="media" type="file" accept="video/*,.mkv" required />
        </label>
        <label className="check">
          <input
            name="authorization_confirmed"
            type="checkbox"
            value="true"
            required
          />
          <span>
            I own, license, or have permission to repurpose this media.
          </span>
        </label>
        <button disabled={busy}>{busy ? "Working…" : "Import locally"}</button>
      </form>
      <p className="notice">
        A public link does not grant publication rights. Files remain in your
        configured local data directory.
      </p>
    </section>
  );
}
