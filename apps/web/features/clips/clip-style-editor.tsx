import { type FormEvent } from "react";

import type { Project } from "../../lib/contracts";

type Clip = Project["clips"][number];

export function ClipStyleEditor({
  clip,
  busy,
  onSave,
}: {
  clip: Clip;
  busy: boolean;
  onSave: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
}) {
  const config = clip.plan.caption_config;
  return (
    <details className="style-editor">
      <summary>Customize captions & framing</summary>
      <form
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          void onSave(clip.id, event.currentTarget);
        }}
      >
        <label className="caption-toggle wide">
          <input
            name="captions_enabled"
            type="checkbox"
            value="true"
            defaultChecked={config.enabled}
          />
          <span>
            Burn subtitles into this clip
            <small>
              Turn off for a clean video; caption files stay available.
            </small>
          </span>
        </label>
        <label>
          Framing
          <select name="frame_style" defaultValue={clip.plan.frame_style}>
            <option value="blurred_background">
              Full frame + soft background
            </option>
            <option value="center_crop">Fill screen (center crop)</option>
          </select>
        </label>
        <label>
          Position
          <select name="position" defaultValue={config.position}>
            <option value="bottom">Bottom</option>
            <option value="middle">Middle</option>
            <option value="top">Top</option>
          </select>
        </label>
        <label>
          Animation
          <select name="animation" defaultValue={config.animation}>
            <option value="pop">Active-word pop</option>
            <option value="karaoke">Karaoke sweep</option>
            <option value="none">None</option>
          </select>
        </label>
        <label>
          Font
          <input
            name="font_family"
            defaultValue={config.font_family}
            maxLength={80}
          />
        </label>
        <label>
          Size
          <input
            name="font_size"
            type="number"
            min={28}
            max={96}
            defaultValue={config.font_size}
          />
        </label>
        <label>
          Words per line
          <input
            name="max_words_per_line"
            type="number"
            min={2}
            max={8}
            defaultValue={config.max_words_per_line}
          />
        </label>
        <label>
          Text color
          <input
            name="text_color"
            type="color"
            defaultValue={config.text_color}
          />
        </label>
        <label>
          Highlight color
          <input
            name="highlight_color"
            type="color"
            defaultValue={config.highlight_color}
          />
        </label>
        <label>
          Outline color
          <input
            name="outline_color"
            type="color"
            defaultValue={config.outline_color}
          />
        </label>
        <label className="wide">
          Always-highlighted words
          <input
            name="highlighted_words"
            defaultValue={config.highlighted_words.join(", ")}
            placeholder="important, offer, key phrase"
          />
        </label>
        <button disabled={busy}>
          {busy ? "Rendering preview…" : "Apply & preview"}
        </button>
      </form>
      <small>
        When enabled, Unicode/RTL text is rendered through libass with Noto font
        fallback. Highlighted words are comma-separated.
      </small>
    </details>
  );
}
